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
    python trance_stream_v3.py --stream               # real-time bar-by-bar playback
    python trance_stream_v3.py --stream --wav /tmp/out.wav  # stream and save simultaneously
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
    parser.add_argument("--wav",     default=None,
                        help="Output WAV path (default: /tmp/trance_v3.wav when not streaming)")
    parser.add_argument("--out-midi", "-o", default=None,
                        help="Output MIDI path (default: /tmp/trance_v3.mid when not streaming)")
    parser.add_argument("--volume",  type=float, default=1.0,
                        help="Master volume 0.0–1.0 (default: 1.0)")
    parser.add_argument("--analyse", action="store_true",
                        help="Run spectral/MIDI analysis after rendering")
    parser.add_argument("--spectrogram", action="store_true",
                        help="Generate spectrogram PNG after rendering")
    parser.add_argument("--play",    action="store_true",
                        help="Play back the WAV after rendering (requires sounddevice)")
    parser.add_argument("--stream",  action="store_true",
                        help="Real-time bar-by-bar playback — render and play simultaneously "
                             "(requires sounddevice). Ctrl-C to stop.")
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

    # Render (or stream)
    from song.renderer import SongRenderer
    renderer = SongRenderer(song)

    # Resolve default paths only when not streaming (stream mode: no files unless requested)
    wav_path  = args.wav  or (None if args.stream else "/tmp/trance_v3.wav")
    midi_path = args.out_midi or (None if args.stream else "/tmp/trance_v3.mid")

    if args.stream:
        buf_l, buf_r = _stream_bars(renderer, args.bars, args.volume, wav_path)
    else:
        print(f"Rendering {args.bars} bars...")
        buf_l, buf_r = renderer.render_bars(args.bars)

        if args.volume != 1.0:
            buf_l *= args.volume
            buf_r *= args.volume

        elapsed = time.time() - t0
        dur_s   = len(buf_l) / song.sr
        print(f"  Rendered {dur_s:.1f}s of audio in {elapsed:.1f}s "
              f"({dur_s/elapsed:.1f}× realtime)")
        print(f"  Peak level: {max(abs(buf_l).max(), abs(buf_r).max()):.4f}")

        print(f"Writing WAV → {wav_path}")
        renderer.write_wav(wav_path)

    # Write MIDI (only if a path is set)
    if midi_path:
        print(f"Writing MIDI → {midi_path}")
        try:
            renderer.write_midi(midi_path)
        except ImportError as e:
            print(f"  (skipped: {e})")

    # Optional analysis
    if args.analyse:
        if not wav_path:
            print("\nAnalysis skipped — no WAV file (use --wav to save one).")
        else:
            print("\nRunning analysis...")
            try:
                sys.path.insert(0, str(REPO_ROOT / "tools"))
                from analyse_audio import analyse_wav, quality_warnings
                from spectrogram import analyse_spectrum
                import wave as _wave
                import numpy as _np

                wav_stats  = analyse_wav(wav_path)
                spec_stats = analyse_spectrum(wav_path)
                print(f"  Crest factor:     {wav_stats['crest_factor_mean']:.2f} "
                      f"(target 3–8)")
                print(f"  Spectral centroid:{spec_stats['mean_centroid_hz']:.0f} Hz "
                      f"(full render avg; SA ref 425–929 Hz at t=90s)")
                print(f"  Brightness:       {spec_stats['brightness_score']:.2%} "
                      f"(full render avg; SA ref 2.3–4.8% at t=90s)")

                with _wave.open(wav_path) as wf:
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
                late_centroid   = float((freqs * pw).sum() / pw.sum()) if pw.sum() > 0 else 0
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
        if not wav_path:
            print("\nSpectrogram skipped — no WAV file (use --wav to save one).")
        else:
            png_path = str(Path(wav_path).with_suffix(".png"))
            print(f"\nGenerating spectrogram → {png_path}")
            try:
                sys.path.insert(0, str(REPO_ROOT / "tools"))
                from spectrogram import generate_spectrogram
                generate_spectrogram(wav_path, png_path,
                                     title=f"trance_stream_v3 — {args.seed} / {args.mood}")
                print(f"  Saved: {png_path}")
            except Exception as e:
                print(f"  Spectrogram failed: {e}")

    # Optional post-render playback (--play, not --stream)
    if args.play and not args.stream:
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


def _stream_bars(renderer: 'SongRenderer', n_bars: int, volume: float,
                 wav_path: str | None) -> tuple:
    """Render and play back bar-by-bar in real time.

    Each bar is rendered (~0.28s at 6× realtime) then written to the audio
    device (1.71s playback at 140 BPM).  The render of bar N+1 happens while
    bar N is playing, so there is ~1.4s of headroom before underrun.

    If wav_path is given, all bars are also written to a WAV file.

    Returns (buf_l, buf_r) of the full accumulated audio.
    """
    import numpy as np
    import wave as _wave

    try:
        import sounddevice as sd
    except ImportError:
        print("sounddevice not installed: pip install sounddevice")
        print("Falling back to render-then-play.")
        buf_l, buf_r = renderer.render_bars(n_bars)
        if volume != 1.0:
            buf_l *= volume
            buf_r *= volume
        return buf_l, buf_r

    sr  = renderer.song.sr
    spb = renderer._spb

    all_l: list[np.ndarray] = []
    all_r: list[np.ndarray] = []

    wav_file = None
    if wav_path:
        wav_file = _wave.open(wav_path, 'wb')
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sr)

    stream = sd.OutputStream(samplerate=sr, channels=2, dtype='float32',
                              blocksize=spb)
    stream.start()
    print(f"Streaming {n_bars} bars in real time — Ctrl-C to stop.")

    try:
        for bar_idx in range(n_bars):
            t_render_start = time.time()
            bar_l, bar_r = renderer._render_bar()

            if volume != 1.0:
                bar_l = bar_l * volume
                bar_r = bar_r * volume

            render_ms = (time.time() - t_render_start) * 1000
            bar_dur_ms = spb / sr * 1000
            print(f"  bar {bar_idx + 1:4d}/{n_bars}  render={render_ms:.0f}ms  "
                  f"budget={bar_dur_ms:.0f}ms  "
                  f"headroom={bar_dur_ms - render_ms:.0f}ms",
                  end='\r')

            stereo = np.column_stack([bar_l, bar_r])
            stream.write(stereo)

            all_l.append(bar_l)
            all_r.append(bar_r)

            if wav_file is not None:
                pcm = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
                wav_file.writeframes(pcm.tobytes())

    except KeyboardInterrupt:
        print(f"\nStopped at bar {len(all_l)}.")
    finally:
        stream.stop()
        stream.close()
        if wav_file is not None:
            wav_file.close()
            print(f"\nWAV saved → {wav_path}")

    print()
    if not all_l:
        return np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32)

    buf_l = np.concatenate(all_l)
    buf_r = np.concatenate(all_r)
    renderer._audio_l = all_l
    renderer._audio_r = all_r
    return buf_l, buf_r


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
