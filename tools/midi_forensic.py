# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Bar-by-bar forensic MIDI dump for trance_stream output.

Prints every note event in every voice, grouped by bar, showing:

- Beat position within the bar (0.00 = beat 1, 1.00 = beat 2, …)
- Pitch name with octave (e.g. A#4)
- Duration in beats
- Whether the note is a chord tone for the current chord block

This makes it possible to see exactly what the engine is playing — useful
for diagnosing problems like:

- Lead firing too many notes per bar (sounds random/erratic)
- Lead or arp notes that are out of the current chord (sounds clashing)
- Bass not landing on beat 1 of each bar
- Notes creeping into registers that sound piercing (e.g. >C5 on lead)
- Trance gate having nothing to work with (all notes shorter than 1 beat)

Usage::

    python tools/midi_forensic.py [MIDI_PATH] [--seed SEED] [--mood MOOD]
                                  [--bars N] [--voice VOICE]

    MIDI_PATH   Path to MIDI file (default: /tmp/trance_out.mid)
    --seed      Seed used when generating the file (default: center)
    --mood      Mood (default: uplifting). Used to determine the chord
                progression so notes can be flagged as in/out of chord.
    --bars N    Only show the first N bars (default: all)
    --voice     Filter to one voice: lead | arp | bass | pad | kick
                (default: all except kick)

Example — look at bars 5-20 of a render, lead and arp only::

    python trance_stream.py --bars 20 -o /tmp/out.mid -s center
    python tools/midi_forensic.py /tmp/out.mid --bars 20 --voice lead
"""
import argparse
import hashlib
from collections import defaultdict

try:
    import mido
except ImportError:
    import sys
    sys.exit("mido required: pip install mido")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("midi",    nargs="?", default="/tmp/trance_out.mid")
parser.add_argument("--seed",  default="center")
parser.add_argument("--mood",  default="uplifting")
parser.add_argument("--bars",  type=int, default=0,
                    help="Show only first N bars (0 = all)")
parser.add_argument("--voice", default=None,
                    choices=["lead", "arp", "bass", "pad", "kick"],
                    help="Filter to a single voice")
args = parser.parse_args()

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
CH_NAMES   = {0: "LEAD", 1: "ARP ", 2: "BASS", 3: "PAD ", 4: "KICK"}
VOICE_CH   = {"lead": 0, "arp": 1, "bass": 2, "pad": 3, "kick": 4}

CHORD_DURATION_BARS = 4

# ---------------------------------------------------------------------------
# Chord progressions (mirrors trance_stream.py MOODS)
# ---------------------------------------------------------------------------

CHORD_INTERVALS = {
    "minor":  [0, 3, 7],
    "major":  [0, 4, 7],
    "minor7": [0, 3, 7, 10],
    "major7": [0, 4, 7, 11],
}

MOOD_PROGRESSIONS = {
    "uplifting":   [(0, "minor"), (8, "major"), (3, "major"),  (10, "major")],
    "dark":        [(0, "minor"), (5, "minor"), (7, "minor"),  (0,  "minor")],
    "acid":        [(0, "minor"), (10,"major"), (8, "major"),  (10, "major")],
    "progressive": [(0, "minor"), (5, "minor"), (0, "major"),  (10, "major")],
    "ambient":     [(0,"major7"), (10,"major7"),(8, "major7"), (10,"major7")],
}

digest    = int(hashlib.md5(args.seed.encode()).hexdigest(), 16)
root      = 48 + (digest % 12)
root_name = NOTE_NAMES[root % 12]

progression_def = MOOD_PROGRESSIONS.get(args.mood, MOOD_PROGRESSIONS["uplifting"])

chords = []
for deg, qual in progression_def:
    chord_root = root + deg
    tones = set((chord_root + i) % 12 for i in CHORD_INTERVALS[qual])
    name  = NOTE_NAMES[(chord_root) % 12]
    if "minor" in qual:
        name += "m"
    elif qual == "major7":
        name += "M7"
    chords.append((name, tones))

print(f"Seed: {args.seed!r}  →  root: {root_name}  |  "
      f"mood: {args.mood}  |  "
      f"progression: {' → '.join(c[0] for c in chords)}")
print()

# ---------------------------------------------------------------------------
# Parse MIDI
# ---------------------------------------------------------------------------

mid      = mido.MidiFile(args.midi)
tpb      = mid.ticks_per_beat
bar_ticks = tpb * 4

notes = []   # (start_tick, ch, note, vel, dur_ticks)
active: dict[tuple, tuple] = {}
abs_tick = 0

for track in mid.tracks:
    abs_tick = 0
    for msg in track:
        abs_tick += msg.time
        if msg.type == "note_on" and msg.velocity > 0:
            active[(msg.channel, msg.note)] = (abs_tick, msg.velocity)
        elif msg.type == "note_off" or (
            msg.type == "note_on" and msg.velocity == 0
        ):
            key = (msg.channel, msg.note)
            if key in active:
                st, vel = active.pop(key)
                notes.append((st, msg.channel, msg.note, vel, abs_tick - st))

notes.sort()

# Voices to display
if args.voice:
    show_chs = {VOICE_CH[args.voice]}
else:
    show_chs = {0, 1, 2, 3}   # everything except kick by default

# Group by bar
by_bar: dict[int, list] = defaultdict(list)
for st, ch, note, vel, dur in notes:
    if ch not in show_chs:
        continue
    bar           = st // bar_ticks
    beat_in_bar   = (st % bar_ticks) / tpb
    by_bar[bar].append((beat_in_bar, ch, note, vel, dur / tpb))

max_bar = max(by_bar.keys()) if by_bar else 0
if args.bars > 0:
    max_bar = min(max_bar, args.bars - 1)

# ---------------------------------------------------------------------------
# Print
# ---------------------------------------------------------------------------

print(f"{'BAR':>4}  {'CHORD':6}  {'VOICE':4}  {'BEAT':5}  {'NOTE':5}  "
      f"{'DUR (b)':7}  {'IN CHORD':8}")
print("-" * 56)

for bar in range(max_bar + 1):
    chord_block          = (bar // CHORD_DURATION_BARS) % len(chords)
    chord_name, chord_tones = chords[chord_block]

    events = sorted(by_bar.get(bar, []), key=lambda x: (x[0], x[1]))
    if not events:
        continue

    bar_label_printed = False
    for beat, ch, note, vel, dur_beats in events:
        note_name   = NOTE_NAMES[note % 12] + str(note // 12 - 1)
        in_chord    = "yes" if (note % 12) in chord_tones else "NO ⚠"
        bar_label   = f"{bar + 1:2d}" if not bar_label_printed else "  "
        chord_label = chord_name      if not bar_label_printed else ""
        bar_label_printed = True
        voice = CH_NAMES.get(ch, f"CH{ch}")
        print(f"  {bar_label}  {chord_label:6s}  {voice}  "
              f"{beat:4.2f}  {note_name:5s}  {dur_beats:6.2f}b  {in_chord}")
    print()
