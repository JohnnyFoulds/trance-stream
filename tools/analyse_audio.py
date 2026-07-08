# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Spectral and dynamic analysis of a trance_stream WAV + MIDI render.

Reads a WAV file and its companion MIDI file and prints a structured report
covering:

- Peak and RMS levels
- Spectral energy by frequency band (sub / bass / mid / hi-mid / air)
- Crest factor (dynamic range proxy)
- Note counts, pitch range, and velocity stats per voice
- Lead melody interval distribution and erratic-motion warnings
- Harmony check: are all melodic notes in the expected minor scale?
- Bass root notes per chord block (confirms progression is correct)
- Arp pitch-class distribution
- Voice density (notes per bar) per voice

Usage::

    python tools/analyse_audio.py [WAV_PATH] [MIDI_PATH] [--seed SEED] [--mood MOOD]

    WAV_PATH   Path to WAV file (default: /tmp/trance_out.wav)
    MIDI_PATH  Path to MIDI file (default: /tmp/trance_out.mid)
    --seed     Seed used when generating the file (default: center)
    --mood     Mood used when generating the file (default: uplifting)

Typical workflow::

    python trance_stream.py --bars 32 --wav /tmp/out.wav -o /tmp/out.mid -s center
    python tools/analyse_audio.py /tmp/out.wav /tmp/out.mid --seed center
"""
import hashlib
import math
import wave
from collections import Counter, defaultdict

try:
    import numpy as np
except ImportError:
    raise ImportError("numpy required: pip install numpy")

try:
    import mido
except ImportError:
    raise ImportError("mido required: pip install mido")

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
CH_NAMES   = {0: "lead", 1: "arp", 2: "bass", 3: "pad", 4: "kick"}
CHORD_DURATION_BARS = 4

BANDS = [
    ("sub",    0,    80),
    ("bass",   80,   300),
    ("mid",    300,  2000),
    ("hi_mid", 2000, 8000),
    ("air",    8000, 22050),
]


def midi_name(n: int) -> str:
    return f"{NOTE_NAMES[n % 12]}{n // 12 - 1}"


def analyse_wav(wav_path: str) -> dict:
    """Analyse a WAV file for level and spectral content.

    Returns:
      peak, peak_dbfs, rms, rms_dbfs    — amplitude statistics
      crest_factor_mean/min/max         — dynamic range proxy (trance target: 3–8)
      band_energy                       — {sub, bass, mid, hi_mid, air} mean magnitude
      duration_s, n_frames, framerate, n_channels
    """
    with wave.open(wav_path, "rb") as wf:
        n_channels = wf.getnchannels()
        framerate  = wf.getframerate()
        n_frames   = wf.getnframes()
        raw        = wf.readframes(n_frames)

    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if n_channels == 2:
        pcm  = pcm.reshape(-1, 2)
        mono = pcm.mean(axis=1)
    else:
        mono = pcm.flatten()

    total_s = len(mono) / framerate
    peak    = float(abs(mono).max())
    rms     = float(math.sqrt((mono ** 2).mean()))

    # Per-band energy via chunked FFT
    CHUNK = 65536
    band_accum = {name: [] for name, _, _ in BANDS}
    n_chunks = len(mono) // CHUNK

    for i in range(n_chunks):
        seg      = mono[i * CHUNK:(i + 1) * CHUNK]
        spectrum = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        freqs    = np.fft.rfftfreq(len(seg), 1.0 / framerate)
        for name, lo, hi in BANDS:
            mask = (freqs >= lo) & (freqs < hi)
            e = float(np.sqrt((spectrum[mask] ** 2).mean())) if mask.any() else 0.0
            band_accum[name].append(e)

    band_energy = {name: float(np.mean(v)) if v else 0.0
                   for name, v in band_accum.items()}

    # Per-second crest factor
    crest = []
    for i in range(int(total_s)):
        seg = mono[i * framerate:(i + 1) * framerate]
        if len(seg) == 0:
            continue
        seg_rms  = math.sqrt(float((seg ** 2).mean()) + 1e-12)
        seg_peak = float(abs(seg).max())
        crest.append(seg_peak / seg_rms)

    return {
        "peak":              peak,
        "peak_dbfs":         20 * math.log10(max(peak, 1e-9)),
        "rms":               rms,
        "rms_dbfs":          20 * math.log10(max(rms, 1e-9)),
        "crest_factor_mean": float(np.mean(crest)) if crest else 0.0,
        "crest_factor_min":  float(np.min(crest)) if crest else 0.0,
        "crest_factor_max":  float(np.max(crest)) if crest else 0.0,
        "band_energy":       band_energy,
        "duration_s":        total_s,
        "n_frames":          n_frames,
        "framerate":         framerate,
        "n_channels":        n_channels,
    }


def analyse_midi(midi_path: str, seed: str = "center") -> dict:
    """Analyse a MIDI file for melody, harmony, and rhythm properties.

    Returns:
      notes_by_ch       — {channel: [(tick, pitch, velocity, duration_ticks)]}
      lead_intervals    — absolute semitone intervals between consecutive lead notes
      lead_mean_interval
      lead_large_leaps_pct  — fraction with interval > 7 semitones
      voice_density     — {voice_name: notes_per_bar}
      out_of_scale_pct  — {voice_name: fraction of out-of-scale notes}
      total_bars
      warnings          — list of human-readable quality warnings
    """
    mid = mido.MidiFile(midi_path)
    tpb = mid.ticks_per_beat

    notes_by_ch: dict[int, list] = defaultdict(list)
    active_notes: dict[tuple, tuple] = {}

    for track in mid.tracks:
        abs_tick = 0
        for msg in track:
            abs_tick += msg.time
            if msg.type == "note_on" and msg.velocity > 0:
                active_notes[(msg.channel, msg.note)] = (abs_tick, msg.velocity)
            elif msg.type == "note_off" or (
                msg.type == "note_on" and msg.velocity == 0
            ):
                key = (msg.channel, msg.note)
                if key in active_notes:
                    start, vel = active_notes.pop(key)
                    notes_by_ch[msg.channel].append(
                        (start, msg.note, vel, abs_tick - start)
                    )

    bar_ticks = tpb * 4
    total_bars = max(
        (max((t for t, _, _, _ in evts), default=0) // bar_ticks) + 1
        for evts in notes_by_ch.values()
    ) if notes_by_ch else 1

    # Lead interval analysis
    lead = sorted(notes_by_ch.get(0, []))
    if len(lead) >= 2:
        intervals = [abs(lead[i + 1][1] - lead[i][1]) for i in range(len(lead) - 1)]
        leaps     = [x for x in intervals if x > 7]
        mean_int  = sum(intervals) / len(intervals)
        large_leaps_pct = len(leaps) / max(len(intervals), 1)
    else:
        intervals = []
        mean_int  = 0.0
        large_leaps_pct = 0.0

    # Scale adherence
    digest    = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    root      = 48 + (digest % 12)
    minor_pcs = {0, 2, 3, 5, 7, 8, 10}

    out_of_scale_pct = {}
    for ch in (0, 1, 2):
        events = notes_by_ch.get(ch, [])
        if events:
            oob = sum(1 for _, n, _, _ in events if (n - root) % 12 not in minor_pcs)
            out_of_scale_pct[CH_NAMES.get(ch, f"ch{ch}")] = oob / len(events)

    # Voice density
    voice_density = {}
    for ch, name in CH_NAMES.items():
        events = notes_by_ch.get(ch, [])
        voice_density[name] = len(events) / total_bars

    # Warnings
    warnings = []
    if intervals and intervals.count(0) / len(intervals) > 0.15:
        warnings.append("TOO MANY UNISONS — melody is stuck, sounds like a drum")
    if mean_int > 5:
        warnings.append(f"MEAN INTERVAL TOO LARGE ({mean_int:.1f} st) — melody jumping around, not flowing")
    if large_leaps_pct > 0.25:
        warnings.append(f"TOO MANY LARGE LEAPS ({large_leaps_pct:.0%}) — erratic, not melodic")
    for voice, pct in out_of_scale_pct.items():
        if pct > 0.05:
            warnings.append(f"CLASHING: {voice} has {pct:.0%} out-of-scale notes")
    if voice_density.get("lead", 0) < 0.5:
        warnings.append("SPARSE LEAD — less than 1 note every 2 bars")
    if voice_density.get("lead", 0) > 8:
        warnings.append("BUSY LEAD — too many notes per bar")
    if voice_density.get("kick", 0) < 3.5:
        warnings.append(f"SPARSE KICK — {voice_density.get('kick', 0):.1f} notes/bar (target: ≥3.5)")

    return {
        "notes_by_ch":        dict(notes_by_ch),
        "lead_intervals":     intervals[:50],
        "lead_mean_interval": mean_int,
        "lead_large_leaps_pct": large_leaps_pct,
        "voice_density":      voice_density,
        "out_of_scale_pct":   out_of_scale_pct,
        "total_bars":         total_bars,
        "ticks_per_beat":     tpb,
        "warnings":           warnings,
    }


def quality_warnings(wav_stats: dict, midi_stats: dict) -> list:
    """Combine wav and midi stats into a single list of quality warnings.

    Adds level and spectral warnings on top of the MIDI warnings already in midi_stats.
    """
    warnings = list(midi_stats.get("warnings", []))

    # Level checks
    peak = wav_stats.get("peak", 0)
    if peak >= 0.99:
        warnings.append("CLIPPING — peak level at or above full scale")
    if peak < 0.1:
        warnings.append("TOO QUIET — peak < 0.1 (check gain levels)")

    crest = wav_stats.get("crest_factor_mean", 0)
    if crest < 2.0:
        warnings.append(f"DISTORTED — crest factor {crest:.1f} < 2 (possible clipping/saturation)")
    if crest > 12.0:
        warnings.append(f"TOO SPARSE — crest factor {crest:.1f} > 12 (too little sustain)")

    # Spectral checks
    be = wav_stats.get("band_energy", {})
    peak_val = max(be.values()) if be else 1e-9
    if be.get("bass", 0) < peak_val * 0.03:
        warnings.append("THIN (bass band energy < 3% of loudest band)")
    if be.get("hi_mid", 0) > peak_val * 0.9:
        warnings.append("HARSH (hi-mid band energy dominates — check filter)")

    return warnings


def _print_wav_report(wav_path: str, stats: dict) -> None:
    print("=" * 64)
    print("WAV ANALYSIS")
    print("=" * 64)
    print(f"File:          {wav_path}")
    print(f"Duration:      {stats['duration_s']:.1f}s  "
          f"({stats['n_frames']} frames, {stats['framerate']} Hz, {stats['n_channels']}ch)")
    print(f"Peak level:    {stats['peak']:.4f}  ({stats['peak_dbfs']:.1f} dBFS)")
    print(f"RMS level:     {stats['rms']:.4f}  ({stats['rms_dbfs']:.1f} dBFS)")

    be       = stats["band_energy"]
    peak_val = max(be.values()) or 1e-9
    labels   = {
        "sub":    "sub    (<80 Hz)",
        "bass":   "bass   (80-300 Hz)",
        "mid":    "mid    (300-2k Hz)",
        "hi_mid": "hi-mid (2k-8k Hz)",
        "air":    "air    (>8k Hz)",
    }
    print("\nSpectral energy by band (mean magnitude, relative to loudest band):")
    for key, label in labels.items():
        v       = be.get(key, 0)
        db      = 20 * math.log10(max(v / peak_val, 1e-9))
        bar_str = "█" * int(30 * v / peak_val)
        flag    = ""
        if db > -3  and key == "hi_mid": flag = "  ← HARSH (too much high-mid)"
        if db > -3  and key == "air":    flag = "  ← HARSH (too much air)"
        if db < -20 and key == "bass":   flag = "  ← THIN (bass too quiet)"
        if db < -20 and key == "sub":    flag = "  ← THIN (sub too quiet)"
        print(f"  {label:25s}  {bar_str:<30s}  {db:+.1f} dB{flag}")

    cf = stats
    print(f"\nCrest factor:  "
          f"mean={cf['crest_factor_mean']:.2f}  "
          f"min={cf['crest_factor_min']:.2f}  "
          f"max={cf['crest_factor_max']:.2f}")
    print("  (trance target: 3–8 | >12 = too sparse/thin | <2 = distorted/clipping)")


def _print_midi_report(midi_path: str, stats: dict, seed: str = "center") -> None:
    print()
    print("=" * 64)
    print("MIDI ANALYSIS")
    print("=" * 64)
    print(f"File:          {midi_path}")

    notes_by_ch = stats["notes_by_ch"]
    tpb         = stats["ticks_per_beat"]
    bar_ticks   = tpb * 4

    print("\nNote counts by voice:")
    for ch in sorted(notes_by_ch):
        name   = CH_NAMES.get(ch, f"ch{ch}")
        events = notes_by_ch[ch]
        if not events:
            continue
        pitches = [n for _, n, _, _ in events]
        vels    = [v for _, _, v, _ in events]
        print(
            f"  {name:8s} (ch{ch}): {len(events):4d} notes  "
            f"range [{midi_name(min(pitches))}–{midi_name(max(pitches))}]  "
            f"vel avg={sum(vels)//len(vels)} min={min(vels)} max={max(vels)}"
        )

    print("\nLead melody intervals:")
    intervals = stats["lead_intervals"]
    if intervals:
        hist     = dict(sorted(Counter(intervals).items()))
        mean_int = stats["lead_mean_interval"]
        leaps    = [x for x in intervals if x > 7]
        print(f"  {len(intervals)} intervals,  mean={mean_int:.1f} st,  "
              f"unisons={intervals.count(0)},  leaps>7st={len(leaps)} "
              f"({100*len(leaps)//max(len(intervals), 1)}%)")
        print(f"  distribution: {hist}")
        lead = sorted(notes_by_ch.get(0, []))
        if lead:
            durations = [d / tpb for _, _, _, d in lead]
            print(f"  note durations (beats): min={min(durations):.2f}  "
                  f"max={max(durations):.2f}  mean={sum(durations)/len(durations):.2f}")
    else:
        print("  (not enough notes to analyse)")

    digest    = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    root      = 48 + (digest % 12)
    root_name = NOTE_NAMES[root % 12]
    minor_pcs = {0, 2, 3, 5, 7, 8, 10}
    print(f"\nHarmony check  (seed '{seed}' → root {root_name}, natural minor):")
    for ch in (0, 1, 2):
        name   = CH_NAMES.get(ch, f"ch{ch}")
        events = notes_by_ch.get(ch, [])
        if not events:
            continue
        oob = [(t, n) for t, n, _, _ in events if (n - root) % 12 not in minor_pcs]
        pct = 100 * len(oob) / len(events)
        flag = "  ← CLASHING" if pct > 5 else "  OK"
        print(f"  {name:8s}: {len(oob)}/{len(events)} out-of-scale ({pct:.0f}%){flag}")
        if oob:
            bad = [midi_name(n) for _, n in oob[:6]]
            print(f"             offenders: {bad}")

    print("\nBass roots per 4-bar chord block:")
    bass = sorted(notes_by_ch.get(2, []))
    for block in range(10):
        t_lo = block * CHORD_DURATION_BARS * bar_ticks
        t_hi = t_lo + CHORD_DURATION_BARS * bar_ticks
        blk  = [n for t, n, _, _ in bass if t_lo <= t < t_hi]
        if not blk:
            continue
        roots = Counter(NOTE_NAMES[n % 12] for n in blk).most_common(3)
        print(f"  bars {block*4+1:2d}–{block*4+4:2d}: {roots}")

    print("\nArp pitch variety:")
    arp = sorted(notes_by_ch.get(1, []))
    if arp:
        pitches    = [n for _, n, _, _ in arp]
        unique_pct = 100 * len(set(pitches)) / len(pitches)
        pc_dist    = dict(Counter(NOTE_NAMES[n % 12] for n in pitches).most_common())
        print(f"  {len(pitches)} notes,  {len(set(pitches))} unique pitches  "
              f"({unique_pct:.0f}% variety)")
        print(f"  pitch classes: {pc_dist}")

    print(f"\nVoice density (notes/bar, over {stats['total_bars']} bars):")
    for ch in (0, 1, 2, 4):
        name    = CH_NAMES.get(ch, f"ch{ch}")
        density = stats["voice_density"].get(name, 0)
        flag    = ""
        if ch == 0 and density < 0.5: flag = "  ← SPARSE LEAD"
        if ch == 0 and density > 8:   flag = "  ← BUSY LEAD"
        if ch == 1 and density < 3:   flag = "  ← SPARSE ARP"
        print(f"  {name:8s}: {density:.1f} notes/bar{flag}")

    if stats["warnings"]:
        print("\nWarnings:")
        for w in stats["warnings"]:
            print(f"  ⚠  {w}")

    print()
    print("=" * 64)


def main():
    import argparse
    import sys

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wav",  nargs="?", default="/tmp/trance_out.wav")
    parser.add_argument("midi", nargs="?", default="/tmp/trance_out.mid")
    parser.add_argument("--seed", default="center")
    parser.add_argument("--mood", default="uplifting")
    args = parser.parse_args()

    wav_stats  = analyse_wav(args.wav)
    midi_stats = analyse_midi(args.midi, seed=args.seed)
    _print_wav_report(args.wav, wav_stats)
    _print_midi_report(args.midi, midi_stats, seed=args.seed)

    warnings = quality_warnings(wav_stats, midi_stats)
    if warnings:
        print("\nQuality summary:")
        for w in warnings:
            print(f"  ⚠  {w}")


if __name__ == "__main__":
    main()
