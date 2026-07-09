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
    parser.add_argument("--bars",    type=int,   default=None,
                        help="Number of bars to render (default: infinite when streaming, 128 otherwise)")
    parser.add_argument("--from-bar", type=int, default=0, metavar="BAR",
                        help="Skip silently to BAR before streaming/rendering (default: 0). "
                             "All instrument state (oscillator phases, filter, sidechain) is "
                             "advanced correctly so the audio sounds right from that point.")
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
    parser.add_argument("--viz",     action="store_true",
                        help="Show full-screen text visualiser while streaming. "
                             "Only valid with --stream.")
    parser.add_argument("--ascii-video", default=None, metavar="PATH",
                        help="Pre-rendered ASCII video frame file to use as CA color overlay. "
                             "Press 'v' during streaming to toggle the overlay on/off. "
                             "If omitted, the default asset (bad_apple_frames.txt) is used "
                             "when present. Only active with --viz --stream.")
    parser.add_argument("--solo", nargs="+", metavar="TRACK",
                        help="Solo one or more tracks; all others are muted. "
                             "Track names: kick pad lead bass hihat clap pulse")
    parser.add_argument("--mute", nargs="+", metavar="TRACK",
                        help="Mute one or more tracks. "
                             "Track names: kick pad lead bass hihat clap pulse")
    args = parser.parse_args()

    n_bars = args.bars if args.bars is not None else (None if args.stream else 128)
    print(f"trance_stream_v3  seed={args.seed!r}  mood={args.mood}  "
          f"bpm={args.bpm}  bars={'∞' if n_bars is None else n_bars}")

    # Build song
    print("Building song...")
    t0 = time.time()
    from song.builder import build_song
    song = build_song(args.seed, mood=args.mood, bpm=args.bpm,
                      total_bars=n_bars or 128)
    print(f"  root={_midi_name(song.root_midi)}  "
          f"scale={_scale_name(song.scale)}  "
          f"tracks={[t.instrument_type for t in song.tracks]}")
    print(f"  stage bars: " +
          "  ".join(f"{k}={v}" for k, v in list(song.stage_bars.items())[:6]))

    # Resolve solo/mute into a set of active track names for the renderer.
    all_tracks = [t.instrument_type for t in song.tracks]
    if args.solo:
        active_tracks = set(args.solo)
        print(f"  SOLO: {sorted(active_tracks)}  (muting: {sorted(set(all_tracks) - active_tracks)})")
    elif args.mute:
        active_tracks = set(all_tracks) - set(args.mute)
        print(f"  MUTE: {sorted(args.mute)}  (playing: {sorted(active_tracks)})")
    else:
        active_tracks = None  # all tracks active

    # Render (or stream)
    from song.renderer import SongRenderer
    renderer = SongRenderer(song, active_tracks=active_tracks)

    if args.from_bar > 0:
        print(f"  Fast-forwarding to bar {args.from_bar}...", end=" ", flush=True)
        t_ff = time.time()
        renderer.fast_forward(args.from_bar)
        print(f"done in {(time.time() - t_ff)*1000:.0f}ms")

    # Resolve default paths only when not streaming (stream mode: no files unless requested)
    wav_path  = args.wav  or (None if args.stream else "/tmp/trance_v3.wav")
    midi_path = args.out_midi or (None if args.stream else "/tmp/trance_v3.mid")

    if args.stream:
        buf_l, buf_r = _stream_bars(renderer, n_bars, args.volume, wav_path,
                                    use_viz=args.viz,
                                    ascii_video_path=args.ascii_video)
    else:
        print(f"Rendering {n_bars} bars...")
        buf_l, buf_r = renderer.render_bars(n_bars)

        if args.volume != 1.0:
            buf_l *= args.volume
            buf_r *= args.volume
            # Scale stored bars so write_wav() writes the volume-adjusted audio
            renderer._audio_l = [b * args.volume for b in renderer._audio_l]
            renderer._audio_r = [b * args.volume for b in renderer._audio_r]

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


def _stream_bars(renderer: 'SongRenderer', n_bars: int | None, volume: float,
                 wav_path: str | None, use_viz: bool = False,
                 ascii_video_path: str | None = None) -> tuple:
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
    spb  = renderer._spb
    sp16 = renderer._sp16

    all_l: list[np.ndarray] = []
    all_r: list[np.ndarray] = []

    wav_file = None
    if wav_path:
        wav_file = _wave.open(wav_path, 'wb')
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sr)

    import queue, threading

    # Double-buffer: render thread fills a queue, audio thread drains it.
    # This decouples render time from playback so bar boundaries never stall.
    # Queue depth 2: one bar playing, one bar ready — render of bar N+1 starts
    # immediately when bar N is queued, not after it finishes playing.
    audio_queue: queue.Queue = queue.Queue(maxsize=3)
    SENTINEL = None

    stop_event = threading.Event()

    def render_thread():
        bar_idx   = renderer._bar   # may be non-zero after --from-bar fast-forward
        bars_done = 0
        while not stop_event.is_set():
            if n_bars is not None and bars_done >= n_bars:
                break
            t0 = time.time()
            bar_l, bar_r = renderer._render_bar()
            if volume != 1.0:
                bar_l = bar_l * volume
                bar_r = bar_r * volume
            render_ms = (time.time() - t0) * 1000
            audio_queue.put((bar_idx, bar_l, bar_r, render_ms))
            bar_idx  += 1
            bars_done += 1
        audio_queue.put(SENTINEL)

    render_t = threading.Thread(target=render_thread, daemon=True)
    render_t.start()

    stream = sd.OutputStream(samplerate=sr, channels=2, dtype='float32',
                             latency='low')
    stream.start()
    bars_label = f"{n_bars}" if n_bars is not None else "∞"
    bar_dur_ms = spb / sr * 1000

    # Set up visualiser (if requested)
    viz = None
    _make_bar_info = None
    if use_viz:
        import sys as _sys
        _sys.path.insert(0, str(REPO_ROOT / "tools"))
        from visualiser import Visualiser, make_bar_info as _make_bar_info

        av_frames, av_fps, av_w, av_h = None, 30, 60, 32
        if ascii_video_path:
            from ascii_video import load_frames as _load_av
            av_frames, av_fps, av_w, av_h = _load_av(ascii_video_path)
            print(f"  ASCII video: {len(av_frames)} frames @ {av_fps}fps  ({av_w}×{av_h})")

        viz = Visualiser(renderer.song, n_bars,
                         ascii_video_frames=av_frames,
                         ascii_video_fps=av_fps,
                         ascii_video_width=av_w,
                         ascii_video_height=av_h)
        viz.start()
    else:
        print(f"Streaming {bars_label} bars in real time — Ctrl-C to stop.")

    try:
        while True:
            item = audio_queue.get()
            if item is SENTINEL:
                break
            bar_idx, bar_l, bar_r, render_ms = item
            if viz:
                # Full-frame update at bar boundary (CA, filter, etc.)
                viz.update(_make_bar_info(bar_idx, renderer.song, render_ms, bar_dur_ms))
                renderer.ca_state = {
                    'density':        viz.ca_density(),
                    'voicing_offset': viz.ca_voicing_offset(),
                }
                # Sub-bar tick: stream 16 sixteenth-note steps individually,
                # flashing track indicators on each instrument's actual hits.
                song = renderer.song
                sb   = song.stage_bars
                from song.theory import (
                    KICK_STEPS_BASIC, KICK_STEPS_SYNCOPATED,
                    CLAP_STEPS_BACKBEAT, HIHAT_STEPS,
                    HIHAT_STEPS_OFFBEAT, HIHAT_STEPS_SPARSE,
                    BASS_STEPS_A, BASS_STEPS_B,
                )
                kick_steps  = (KICK_STEPS_SYNCOPATED
                               if bar_idx >= sb.get('kick_syncopated', 9999)
                               else KICK_STEPS_BASIC)
                hihat_pat   = getattr(song, 'hihat_pattern', 'full')
                hihat_steps = (HIHAT_STEPS_OFFBEAT if hihat_pat == 'offbeat'
                               else HIHAT_STEPS_SPARSE if hihat_pat == 'sparse'
                               else HIHAT_STEPS)
                ca_dense    = renderer.ca_state.get('density', 0.5) > 0.55
                bass_steps  = (BASS_STEPS_B if ca_dense
                               else BASS_STEPS_A if bar_idx % 2 == 0
                               else BASS_STEPS_B)
                # Lead fires on steps 4 and 10 once melody is active
                lead_steps  = ([4, 10] if bar_idx >= sb.get('lead_melody_on', 9999)
                               else [0])

                for step in range(16):
                    onset = step * sp16
                    end   = onset + sp16
                    chunk = np.column_stack([bar_l[onset:end], bar_r[onset:end]])
                    stream.write(chunk)
                    hit_map = {
                        'kick':  bar_idx >= sb.get('kick_on',       0)    and step in kick_steps,
                        'pad':   bar_idx >= sb.get('pad_root_on',   9999) and step == 0,
                        'bass':  bar_idx >= sb.get('bass_on',       9999) and step in bass_steps,
                        'lead':  bar_idx >= sb.get('lead_root_on',  9999) and step in lead_steps,
                        'hihat': bar_idx >= sb.get('hihat_on',      9999) and step in hihat_steps,
                        'clap':  bar_idx >= sb.get('clap_on',       9999) and step in CLAP_STEPS_BACKBEAT,
                        'pulse': bar_idx >= sb.get('pulse_on',      9999) and step % 4 == 0,
                    }
                    viz.tick(hit_map)
            else:
                stereo = np.column_stack([bar_l, bar_r])
                stream.write(stereo)
                print(f"  bar {bar_idx + 1:4d}/{bars_label}  render={render_ms:.0f}ms  "
                      f"budget={bar_dur_ms:.0f}ms  "
                      f"headroom={bar_dur_ms - render_ms:.0f}ms",
                      end='\r')
            all_l.append(bar_l)
            all_r.append(bar_r)
            if wav_file is not None:
                wav_stereo = np.column_stack([bar_l, bar_r])
                pcm = (np.clip(wav_stereo, -1, 1) * 32767).astype(np.int16)
                wav_file.writeframes(pcm.tobytes())

    except KeyboardInterrupt:
        if viz:
            viz.stop()
        else:
            print(f"\nStopped at bar {len(all_l)}.")
        stop_event.set()
        while not audio_queue.empty():
            try: audio_queue.get_nowait()
            except: break
    finally:
        stop_event.set()
        render_t.join(timeout=2.0)
        stream.stop()
        stream.close()
        if viz:
            viz.stop()
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
