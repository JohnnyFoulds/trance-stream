# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""trance_stream_v3 — procedural trance generator targeting Switch Angel's style.

Architecture: song/theory.py (music knowledge) → song/builder.py (Song assembly)
→ song/renderer.py (SongRenderer) → WAV + MIDI output.

All musical constants cite their source in docs/music_theory/.
All synthesis is numpy-vectorised (no Python sample loops).

Usage::

    python trance_stream_v3.py
    python trance_stream_v3.py --seed sunrise --mood uplifting --bars 128
    python trance_stream_v3.py --seed forest --mood dark --bpm 138 --wav /tmp/out.wav
    python trance_stream_v3.py --bars 32 --out-midi /tmp/out.mid
    python trance_stream_v3.py --analyse     # run spectral analysis on the output
    python trance_stream_v3.py --spectrogram # generate spectrogram PNG

Moods: uplifting (default), dark, acid, dreamy, progressive
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).parent


def main():
    parser = argparse.ArgumentParser(
        description=__doc__.splitlines()[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__.split("Usage::")[-1],
    )
    parser.add_argument("--seed",    "-s", default="sunrise",
                        help="Generation seed (default: sunrise)")
    parser.add_argument("--mood",    "-m", default="uplifting",
                        choices=["uplifting", "dark", "acid", "dreamy", "progressive"],
                        help="Mood/style (default: uplifting)")
    parser.add_argument("--bpm",     type=float, default=140.0,
                        help="Tempo in BPM (default: 140)")
    parser.add_argument("--bars",    type=int,   default=128,
                        help="Number of bars to render (default: 128)")
    parser.add_argument("--wav",     default="/tmp/trance_v3.wav",
                        help="Output WAV path (default: /tmp/trance_v3.wav)")
    parser.add_argument("--out-midi", "-o", default="/tmp/trance_v3.mid",
                        help="Output MIDI path (default: /tmp/trance_v3.mid)")
    parser.add_argument("--volume",  type=float, default=1.0,
                        help="Master volume 0.0–1.0 (default: 1.0)")
    parser.add_argument("--analyse", action="store_true",
                        help="Run spectral/MIDI analysis after rendering")
    parser.add_argument("--spectrogram", action="store_true",
                        help="Generate spectrogram PNG after rendering")
    parser.add_argument("--play",    action="store_true",
                        help="Play back the WAV after rendering (requires sounddevice)")
    args = parser.parse_args()

    print(f"trance_stream_v3  seed={args.seed!r}  mood={args.mood}  "
          f"bpm={args.bpm}  bars={args.bars}")

    # Build song
    print("Building song...")
    t0 = time.time()
    from song.builder import build_song
    song = build_song(args.seed, mood=args.mood, bpm=args.bpm,
                      total_bars=args.bars)
    print(f"  root={_midi_name(song.root_midi)}  "
          f"scale={_scale_name(song.scale)}  "
          f"tracks={[t.instrument_type for t in song.tracks]}")
    print(f"  stage bars: " +
          "  ".join(f"{k}={v}" for k, v in list(song.stage_bars.items())[:6]))

    # Render
    print(f"Rendering {args.bars} bars...")
    from song.renderer import SongRenderer
    renderer = SongRenderer(song)
    buf_l, buf_r = renderer.render_bars(args.bars)

    # Apply master volume
    if args.volume != 1.0:
        buf_l *= args.volume
        buf_r *= args.volume

    elapsed = time.time() - t0
    dur_s   = len(buf_l) / song.sr
    print(f"  Rendered {dur_s:.1f}s of audio in {elapsed:.1f}s "
          f"({dur_s/elapsed:.1f}× realtime)")
    print(f"  Peak level: {max(abs(buf_l).max(), abs(buf_r).max()):.4f}")

    # Write WAV
    print(f"Writing WAV → {args.wav}")
    renderer.write_wav(args.wav)

    # Write MIDI
    print(f"Writing MIDI → {args.out_midi}")
    try:
        renderer.write_midi(args.out_midi)
    except ImportError as e:
        print(f"  (skipped: {e})")

    # Optional analysis
    if args.analyse:
        print("\nRunning analysis...")
        try:
            sys.path.insert(0, str(REPO_ROOT / "tools"))
            from analyse_audio import analyse_wav, quality_warnings
            from spectrogram import analyse_spectrum
            import wave as _wave
            import numpy as _np

            wav_stats  = analyse_wav(args.wav)
            spec_stats = analyse_spectrum(args.wav)
            print(f"  Crest factor:     {wav_stats['crest_factor_mean']:.2f} "
                  f"(target 3–8)")
            print(f"  Spectral centroid:{spec_stats['mean_centroid_hz']:.0f} Hz "
                  f"(full render avg; SA ref 425–929 Hz at t=90s)")
            print(f"  Brightness:       {spec_stats['brightness_score']:.2%} "
                  f"(full render avg; SA ref 2.3–4.8% at t=90s)")

            # Late-bars analysis: last 12 bars (approximately t=90s equivalent)
            with _wave.open(args.wav) as wf:
                sr_wav  = wf.getframerate()
                n_total = wf.getnframes()
                spb_wav = int(sr_wav * 4 * 60 / renderer.song.bpm)
                n_late  = min(12 * spb_wav, n_total // 4)
                wf.setpos(n_total - n_late)
                raw = wf.readframes(n_late)
            samples = _np.frombuffer(raw, dtype=_np.int16).reshape(-1, 2)
            late_l  = samples[:, 0].astype(_np.float32) / 32767.0
            spec    = _np.abs(_np.fft.rfft(late_l * _np.hanning(len(late_l))))
            freqs   = _np.fft.rfftfreq(len(late_l), 1.0 / sr_wav)
            pw      = spec ** 2
            late_centroid  = float((freqs * pw).sum() / pw.sum()) if pw.sum() > 0 else 0
            late_brightness = float(pw[freqs >= 1500].sum() / pw.sum()) if pw.sum() > 0 else 0
            print(f"  Late centroid:    {late_centroid:.0f} Hz "
                  f"(last 12 bars; SA ref 425–929 Hz)")
            print(f"  Late brightness:  {late_brightness:.2%} "
                  f"(last 12 bars; SA ref 2.3–4.8%)")

            warnings = quality_warnings(wav_stats, {})
            for w in warnings:
                print(f"  ⚠  {w}")
        except Exception as e:
            import traceback; traceback.print_exc()
            print(f"  Analysis failed: {e}")

    # Optional spectrogram
    if args.spectrogram:
        png_path = str(Path(args.wav).with_suffix(".png"))
        print(f"\nGenerating spectrogram → {png_path}")
        try:
            sys.path.insert(0, str(REPO_ROOT / "tools"))
            from spectrogram import generate_spectrogram
            generate_spectrogram(args.wav, png_path,
                                  title=f"trance_stream_v3 — {args.seed} / {args.mood}")
            print(f"  Saved: {png_path}")
        except Exception as e:
            print(f"  Spectrogram failed: {e}")

    # Optional playback
    if args.play:
        print("\nPlaying back...")
        try:
            import sounddevice as sd
            import numpy as np
            stereo = np.column_stack([buf_l, buf_r])
            sd.play(stereo, samplerate=song.sr)
            sd.wait()
        except ImportError:
            print("  sounddevice not installed: pip install sounddevice")
        except Exception as e:
            print(f"  Playback failed: {e}")

    print("\nDone.")


def _midi_name(n: int) -> str:
    names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
    return f"{names[n % 12]}{n // 12 - 1}"


def _scale_name(intervals: list) -> str:
    from song.theory import SCALES
    for name, sc in SCALES.items():
        if sc == intervals:
            return name
    return str(intervals)


if __name__ == "__main__":
    main()
