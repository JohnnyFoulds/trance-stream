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
import argparse
import hashlib
import math
import sys
import wave
from collections import Counter, defaultdict

try:
    import numpy as np
except ImportError:
    sys.exit("numpy required: pip install numpy")

try:
    import mido
except ImportError:
    sys.exit("mido required: pip install mido")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("wav",  nargs="?", default="/tmp/trance_out.wav")
parser.add_argument("midi", nargs="?", default="/tmp/trance_out.mid")
parser.add_argument("--seed", default="center")
parser.add_argument("--mood", default="uplifting")
args = parser.parse_args()

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
CH_NAMES   = {0: "lead", 1: "arp", 2: "bass", 3: "pad", 4: "kick"}

CHORD_DURATION_BARS = 4


def midi_name(n: int) -> str:
    return f"{NOTE_NAMES[n % 12]}{n // 12 - 1}"


# ---------------------------------------------------------------------------
# WAV analysis
# ---------------------------------------------------------------------------

print("=" * 64)
print("WAV ANALYSIS")
print("=" * 64)

with wave.open(args.wav, "rb") as wf:
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

print(f"File:          {args.wav}")
print(f"Duration:      {total_s:.1f}s  ({n_frames} frames, {framerate} Hz, {n_channels}ch)")
print(f"Peak level:    {peak:.4f}  ({20*math.log10(max(peak, 1e-9)):.1f} dBFS)")
print(f"RMS level:     {rms:.4f}  ({20*math.log10(max(rms, 1e-9)):.1f} dBFS)")

# Spectral energy per band via chunked FFT
CHUNK = 65536
BANDS = {
    "sub    (<80 Hz)":    (0,    80),
    "bass   (80-300 Hz)": (80,   300),
    "mid    (300-2k Hz)": (300,  2000),
    "hi-mid (2k-8k Hz)":  (2000, 8000),
    "air    (>8k Hz)":    (8000, 22050),
}
band_energy: dict[str, list[float]] = defaultdict(list)
n_chunks = len(mono) // CHUNK

for i in range(n_chunks):
    seg      = mono[i * CHUNK:(i + 1) * CHUNK]
    spectrum = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
    freqs    = np.fft.rfftfreq(len(seg), 1.0 / framerate)
    for label, (lo, hi) in BANDS.items():
        mask = (freqs >= lo) & (freqs < hi)
        e = float(np.sqrt((spectrum[mask] ** 2).mean())) if mask.any() else 0.0
        band_energy[label].append(e)

print("\nSpectral energy by band (mean magnitude, relative to loudest band):")
vals     = {k: float(np.mean(v)) for k, v in band_energy.items()}
peak_val = max(vals.values()) or 1e-9
for label, v in vals.items():
    db      = 20 * math.log10(max(v / peak_val, 1e-9))
    bar_str = "█" * int(30 * v / peak_val)
    flag    = ""
    if db > -3  and "hi-mid" in label: flag = "  ← HARSH (too much high-mid)"
    if db > -3  and "air"    in label: flag = "  ← HARSH (too much air)"
    if db < -20 and "bass"   in label: flag = "  ← THIN (bass too quiet)"
    if db < -20 and "sub"    in label: flag = "  ← THIN (sub too quiet)"
    print(f"  {label:25s}  {bar_str:<30s}  {db:+.1f} dB{flag}")

# Crest factor (peak/RMS per second)
crest = []
for i in range(int(total_s)):
    seg = mono[i * framerate:(i + 1) * framerate]
    if len(seg) == 0:
        continue
    seg_rms  = math.sqrt(float((seg ** 2).mean()) + 1e-12)
    seg_peak = float(abs(seg).max())
    crest.append(seg_peak / seg_rms)

print(f"\nCrest factor:  "
      f"mean={float(np.mean(crest)):.2f}  "
      f"min={float(np.min(crest)):.2f}  "
      f"max={float(np.max(crest)):.2f}")
print("  (trance target: 3–8 | >12 = too sparse/thin | <2 = distorted/clipping)")

# ---------------------------------------------------------------------------
# MIDI analysis
# ---------------------------------------------------------------------------

print()
print("=" * 64)
print("MIDI ANALYSIS")
print("=" * 64)
print(f"File:          {args.midi}")

mid = mido.MidiFile(args.midi)
tpb = mid.ticks_per_beat

# Parse note events
notes_by_ch: dict[int, list[tuple]] = defaultdict(list)
active_notes: dict[tuple, tuple]    = {}
abs_tick = 0

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

# Note counts / range / velocity per voice
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

# Lead interval distribution
print("\nLead melody intervals:")
lead = sorted(notes_by_ch.get(0, []))
if len(lead) >= 2:
    intervals = [abs(lead[i + 1][1] - lead[i][1]) for i in range(len(lead) - 1)]
    leaps     = [x for x in intervals if x > 7]
    mean_int  = sum(intervals) / len(intervals)
    hist      = dict(sorted(Counter(intervals).items()))
    print(f"  {len(intervals)} intervals,  mean={mean_int:.1f} st,  "
          f"unisons={intervals.count(0)},  leaps>7st={len(leaps)} "
          f"({100*len(leaps)//max(len(intervals), 1)}%)")
    print(f"  distribution: {hist}")
    if intervals.count(0) / max(len(intervals), 1) > 0.15:
        print("  ⚠  TOO MANY UNISONS — melody is stuck, sounds like a drum")
    if mean_int > 5:
        print("  ⚠  MEAN INTERVAL TOO LARGE — melody jumping around, not flowing")
    if len(leaps) / max(len(intervals), 1) > 0.25:
        print("  ⚠  TOO MANY LARGE LEAPS — erratic, not melodic")
    durations = [d / tpb for _, _, _, d in lead]
    print(f"  note durations (beats): min={min(durations):.2f}  "
          f"max={max(durations):.2f}  mean={sum(durations)/len(durations):.2f}")
    if max(durations) < 1.0:
        print("  ⚠  LEAD NOTES ALL SHORT — no sustained notes; trance gate has "
              "nothing to work with; will sound like random bursts")
else:
    print("  (not enough notes to analyse)")

# Harmony check against the natural minor scale of the seed's root
digest    = int(hashlib.md5(args.seed.encode()).hexdigest(), 16)
root      = 48 + (digest % 12)
root_name = NOTE_NAMES[root % 12]
# Natural minor: W-H-W-W-H-W-W  →  semitones {0,2,3,5,7,8,10}
minor_pcs = {0, 2, 3, 5, 7, 8, 10}

print(f"\nHarmony check  (seed '{args.seed}' → root {root_name}, natural minor):")
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

# Bass root distribution per 4-bar chord block
print("\nBass roots per 4-bar chord block:")
bass     = sorted(notes_by_ch.get(2, []))
bar_ticks = tpb * 4
for block in range(10):
    t_lo = block * CHORD_DURATION_BARS * bar_ticks
    t_hi = t_lo  + CHORD_DURATION_BARS * bar_ticks
    blk  = [n for t, n, _, _ in bass if t_lo <= t < t_hi]
    if not blk:
        continue
    roots = Counter(NOTE_NAMES[n % 12] for n in blk).most_common(3)
    print(f"  bars {block*4+1:2d}–{block*4+4:2d}: {roots}")

# Arp pitch-class distribution
print("\nArp pitch variety:")
arp = sorted(notes_by_ch.get(1, []))
if arp:
    pitches    = [n for _, n, _, _ in arp]
    unique_pct = 100 * len(set(pitches)) / len(pitches)
    pc_dist    = dict(Counter(NOTE_NAMES[n % 12] for n in pitches).most_common())
    print(f"  {len(pitches)} notes,  {len(set(pitches))} unique pitches  "
          f"({unique_pct:.0f}% variety)")
    print(f"  pitch classes: {pc_dist}")

# Voice density
total_bars = max(
    (max((t for t, _, _, _ in evts), default=0) // bar_ticks) + 1
    for evts in notes_by_ch.values()
) if notes_by_ch else 1

print(f"\nVoice density (notes/bar, over {total_bars} bars):")
for ch in (0, 1, 2, 4):
    name   = CH_NAMES.get(ch, f"ch{ch}")
    events = notes_by_ch.get(ch, [])
    density = len(events) / total_bars
    flag = ""
    if ch == 0 and density < 0.5: flag = "  ← SPARSE LEAD (less than 1 note every 2 bars)"
    if ch == 0 and density > 8:   flag = "  ← BUSY LEAD (too many notes per bar)"
    if ch == 1 and density < 3:   flag = "  ← SPARSE ARP"
    print(f"  {name:8s}: {density:.1f} notes/bar{flag}")

print()
print("=" * 64)
