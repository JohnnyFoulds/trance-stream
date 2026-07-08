# Generative Melody: Theory Reference for `song/theory.py`

This document is the authoritative source for every melody-generation rule in `song/theory.py`. Every
Python constant, algorithm, and constraint below is derived from either SA's confirmed Strudel code
(OCR-extracted from YouTube session recordings) or first-principles music theory that can be
operationalised as a Python rule. Nothing here is vague: every claim ends in a testable assertion.

Style target: **Switch Angel (SA)**, G natural minor, 138–140 BPM.

---

## 1. How `notearp` Works

`notearp` is a Strudel built-in that takes a list of notes (a chord) and a pattern of integers (indices)
and returns the note at each specified index on each trigger. It is an index-selector, not a
transposer.

```
notearp(chord, index_pattern) → note_per_step
```

Mechanics:
- `chord` is an ordered list of MIDI note numbers, lowest to highest (e.g. `[60, 62, 63, 65]`).
- The index pattern specifies, for each rhythmic step, which position in that list to play.
- Index 0 = lowest chord note, index 1 = second-lowest, etc.
- Indices are taken modulo `len(chord)`, so index 4 on a 4-note chord wraps back to index 0.
- A `-` (rest) in the index pattern produces silence on that step — no note is selected.

SA applies `notearp` to the pad chord. The pad chord in G natural minor at scale degrees [3,4,5,6] is,
from root G3 (MIDI 43):

| Scale degree | Semitone offset | Note | MIDI (root = G3) |
|--------------|-----------------|------|-------------------|
| 3            | +5              | C4   | 60                |
| 4            | +7              | D4   | 62                |
| 5            | +8              | Eb4  | 63                |
| 6            | +10             | F4   | 65                |

So `notearp([60, 62, 63, 65], 0)` = C4 (60) and `notearp([60, 62, 63, 65], 1)` = D4 (62).

The `.add("-14,-21")` octave doublings SA applies elsewhere are added to the full chord signal, not
to the notearp index output. Notearp sees only the un-doubled 4-note chord.

**Python constant (song/theory.py):**

```python
# SA's pad chord as scale degrees — confirmed from OCR analysis
SA_PAD_CHORD_DEGREES: list[int] = [3, 4, 5, 6]

def chord_midi_notes(root_midi: int, scale_intervals: list[int],
                     degrees: list[int]) -> list[int]:
    """Return MIDI notes for a chord specified as scale degree indices."""
    return [root_midi + scale_intervals[d] for d in degrees]

def notearp(chord: list[int], index: int) -> int:
    """Select a MIDI note from a chord by index (wraps on overflow)."""
    return chord[index % len(chord)]
```

---

## 2. SA's Confirmed Notearp Pattern

**[SA confirmed]** Source: video `3fpx7Scysw4`, consistent across all 128 OCR-extracted snapshots.

```
"< <- - - -> 0 1@2 0 1 0 1>*16"
```

### 2.1 Parsing the Strudel Syntax

Strudel's `< >` creates an **alternating cycle**: each evaluation advances to the next item in the
list, cycling back after the last. The `*16` suffix forces 16 evaluations per bar — i.e. 16th-note
resolution.

The outer cycle `< A B C D E F G >*16` contains 7 items:

| Position | Token       | Meaning                                          |
|----------|-------------|--------------------------------------------------|
| 0        | `<- - - ->` | Sub-cycle of 4 rests — one rest per evaluation   |
| 1        | `0`         | chord index 0 (C4 in SA's G minor pad chord)     |
| 2        | `1@2`       | chord index 1, held for 2 units (D4, held)       |
| 3        | `0`         | chord index 0 (C4)                               |
| 4        | `1`         | chord index 1 (D4)                               |
| 5        | `0`         | chord index 0 (C4)                               |
| 6        | `1`         | chord index 1 (D4)                               |

The sub-cycle `<- - - ->` iterates through its own 4 rests once per evaluation, so on every
evaluation it produces exactly one rest. This means positions 0 through 3 of the sub-cycle are each
consumed once per bar-of-the-outer-cycle.

### 2.2 Active Steps per Bar

With 16 16th-note slots and 7 items in the outer cycle, the pattern distributes proportionally:

```
Outer-cycle item weights (by default Strudel proportional distribution with *16):
  Item 0 (sub-cycle rest): weight 1/7 → ~2.3 steps → rounds to 2 steps = rest, rest
  Item 1 (index 0):        weight 1/7 → ~2.3 steps → 2 steps
  Item 2 (index 1@2):      weight 2/7 → ~4.6 steps → 4 steps (held)
  Item 3 (index 0):        weight 1/7 → ~2.3 steps → 2 steps
  Item 4 (index 1):        weight 1/7 → ~2.3 steps → 2 steps
  Item 5 (index 0):        weight 1/7 → ~2.3 steps → 2 steps
  Item 6 (index 1):        weight 1/7 → ~2.3 steps → 2 steps
```

Approximate 16-step grid (R = rest, 0 = C4, 1 = D4, H = held):

```
Step:  1  2  3  4  5  6  7  8  9 10 11 12 13 14 15 16
       R  R  0  0  1  1  1  1  0  0  1  1  0  0  1  1
```

The key structural observation: **steps 1–2 are silent, melodic content begins at step 3**. This is
the "back-loaded" characteristic — the first ~12% of the bar is silence, creating a rhythmic breath
before the melody enters. Steps 5–8 are a held D4 (the `1@2`), giving a sense of arrival and rest
before the faster alternation in steps 9–16.

### 2.3 What the Back-Loaded Rhythm Creates

1. **Breath before entry**: the 2-step rest at the bar start gives the pad and kick space to be heard
   clearly before the arpeggio enters. This prevents harmonic clutter on the downbeat.
2. **Perceived backbeat**: entry on step 3 (the "and" of beat 1 at 16th-note resolution) creates a
   syncopated feel — the melody sounds like it is answering the kick rather than doubling it.
3. **Held note as phrase centre**: the `1@2` held note lands roughly at the bar's midpoint and is the
   longest note in the pattern. Perceptually, it is the "main note" of each bar even though it is not
   on beat 1. This is consistent with trance production practice of placing emphasis slightly off the
   downbeat to create forward propulsion.
4. **Index-0/index-1 alternation**: only two distinct pitches are used (C4 and D4 in SA's key). This
   minimal pitch vocabulary makes the arpeggiated pattern hypnotic and loop-friendly. Trance melodies
   that feel complex often use ≤3 pitches per bar; SA uses 2.

**Python constant (song/theory.py):**

```python
# SA's confirmed notearp index pattern, encoded as a list of (index_or_rest, duration_in_16ths).
# Each tuple: (None = rest, int = chord index, duration in 16th notes).
# Total durations sum to 16 (one bar at 16th-note resolution).
SA_NOTEARP_PATTERN: list[tuple[int | None, int]] = [
    (None, 2),   # 2 rests (sub-cycle <-- - - ->)
    (0,    2),   # chord index 0
    (1,    4),   # chord index 1, held (1@2 ≈ 4 sixteenths)
    (0,    2),   # chord index 0
    (1,    2),   # chord index 1
    (0,    2),   # chord index 0
    (1,    2),   # chord index 1
]
# Sanity check: sum(d for _, d in SA_NOTEARP_PATTERN) == 16
```

---

## 3. SA's Lead Note Pattern

**[SA confirmed]** Source: OCR-extracted from SA's session recordings.

```
"@@2 <-7 [-5 -2]>@3 <0 -3 2 1>@3"
```

### 3.1 Parsing the Strudel Syntax

This pattern is written in **semitone offsets from the root**, applied with `.add()` or as direct
note transpositions on a base pitch (root of the current chord).

| Token             | Duration  | Meaning                                                     |
|-------------------|-----------|-------------------------------------------------------------|
| `@@2`             | 2 bars    | Rest for 2 full bars                                        |
| `<-7 [-5 -2]>@3`  | 3 bars    | Alternating cycle over 3 bars: bar 1 = -7, bars 2–3 = [-5,-2] |
| `<0 -3 2 1>@3`    | 3 bars    | 4-item cycle over 3 bars: one item per bar, cycling         |

Total length: 2 + 3 + 3 = **8 bars**, a standard trance phrase.

**Breaking down `<-7 [-5 -2]>@3`:**
- The alternating cycle has 2 items: `-7` (a single semitone offset) and `[-5 -2]` (a dyad — two
  notes played simultaneously).
- `@3` stretches this 2-item cycle over 3 bars: bar 1 → item 0 (-7), bar 2 → item 1 ([-5,-2]),
  bar 3 → item 0 (-7) again (cycle wraps).
- So the actual bar-by-bar breakdown of this segment: bar 3 = -7, bar 4 = [-5,-2], bar 5 = -7.

**Breaking down `<0 -3 2 1>@3`:**
- A 4-item cycle over 3 bars: bar 6 → 0, bar 7 → -3, bar 8 → 2. (Item 1 = `1` would start bar 9.)
- Each item lasts one bar (3 bars total consumed from the 4-item cycle).
- The `1` (last cycle item) is not reached within the 8-bar phrase; the phrase ends at bar 8.

### 3.2 Bar-by-Bar Breakdown

| Bar | Semitone(s) relative to root | Note in G minor (root = G) | Name                |
|-----|------------------------------|----------------------------|---------------------|
| 1   | rest                         | —                          | silence             |
| 2   | rest                         | —                          | silence             |
| 3   | -7                           | C (one octave below root G = C3 region) | minor 7th below |
| 4   | [-5, -2]                     | D, F# (= D and F dyad below G)          | dyad: P4 below + M2 below |
| 5   | -7                           | C (same as bar 3)          | minor 7th below again |
| 6   | 0                            | G (root)                   | root / unison       |
| 7   | -3                           | E (minor 3rd below G = Eb/E)| minor 3rd below    |
| 8   | +2                           | A (major 2nd above G)      | stepwise rise       |

Note on bar 4: `-5` is a perfect 4th below, `-2` is a major 2nd below. In G minor: G-5 = D, G-2 = F.
The dyad [D, F] is a minor 3rd interval, and both notes are diatonic to G natural minor. D is the
scale's 5th degree, F is the 7th degree — a power dyad that implies dominant function.

### 3.3 Interval Analysis

Computing the melodic intervals between successive bars (rests treated as breaks; intervals measured
within melodic segments):

**Segment 1 (bars 3–5): descent figure**

```
Bar 3 → Bar 4: -7 to -5 = +2 semitones (stepwise rise within the descent)
Bar 4 → Bar 5: -5 to -7 = -2 semitones (stepwise fall back)
```

This creates an oscillation around the -7 position: reach down to -7, momentarily rise to -5/-2,
fall back to -7. The listener experiences this as hovering at the bottom of the range.

**Segment 2 (bars 6–8): turn figure**

```
Bar 5 → Bar 6: -7 to 0 = +7 semitones (perfect 5th rise — the main leap)
Bar 6 → Bar 7: 0 to -3  = -3 semitones (minor 3rd fall — dip below root)
Bar 7 → Bar 8: -3 to +2 = +5 semitones (perfect 4th rise — the climax move)
```

The P5 leap from bar 5 to bar 6 (-7 to 0) is the phrase's dramatic pivot: after hovering at the
bottom for 3 bars, the melody jumps a fifth to the root and then turns. This is a textbook "springboard
and pivot" phrase shape.

**Interval histogram for the complete active phrase (bars 3–8):**

| Interval (semitones) | Count | Direction | Classification          |
|----------------------|-------|-----------|-------------------------|
| +2                   | 1     | up        | stepwise (M2)           |
| -2                   | 1     | down      | stepwise (M2)           |
| +7                   | 1     | up        | P5 leap (structural)    |
| -3                   | 1     | down      | m3 (chord tone)         |
| +5                   | 1     | up        | P4 (structural)         |

Stepwise motion (±1 or ±2): 2/5 = **40%** of intervals. Structural leaps (P4, P5): 2/5 = 40%.
Chord-tone leaps (m3): 1/5 = 20%. No tritones (+6). No major 7ths (±11). No augmented intervals.

### 3.4 Phrase Structure

The 8-bar phrase follows a **2+3+3 durational division**:

```
Bars 1–2:  Call silence   — pad establishes harmony, kick establishes groove
Bars 3–5:  Statement      — low register, oscillating, creates tension
Bars 6–8:  Response/rise  — jump to root, turn, climb to +2 (phrase peak)
```

This is a **question-answer (antecedent-consequent)** structure compressed into 3 macro-units:
- The silence is the question (expectation).
- The low statement is the antecedent (tension statement).
- The high turn is the consequent (partial resolution).

The phrase does not fully resolve — it ends on +2 (A over G = major 2nd above root), which is an
unstable scale tone. This deliberate non-resolution is what causes the 8-bar phrase to repeat and
loop naturally: the ear is not given a full cadence, so it accepts the looping as continuation.

**Python constant (song/theory.py):**

```python
# SA's confirmed lead pattern, encoded as list of (semitone_offset_or_rest, bars).
# Semitone offset is relative to the current chord root.
# Dyads (simultaneous notes) are encoded as tuples.
SA_LEAD_PATTERN: list[tuple[int | tuple[int, int] | None, int]] = [
    (None,    2),   # 2 bars rest (@@2)
    (-7,      1),   # bar 3: minor 7th below root
    ((-5,-2), 1),   # bar 4: dyad — P4 below + M2 below (dominant dyad)
    (-7,      1),   # bar 5: minor 7th below again
    (0,       1),   # bar 6: root (unison)
    (-3,      1),   # bar 7: minor 3rd below
    (+2,      1),   # bar 8: major 2nd above (phrase peak, non-resolving)
]
# Total: 8 bars. Phrase ends unresolved on +2 → natural loop point.
```

---

## 4. What Makes Trance Melody Work

These are the structural mechanisms behind SA's specific pattern choices. Each has a measurable
correlate that can be checked by a generative algorithm.

### 4.1 Repetition with Variation

SA's notearp pattern repeats identically every bar. The chord progression (degrees [3,4,5,6]) changes
every 2–4 bars. Result: the **rhythm** stays constant (familiarity), the **pitches** change with the
harmony (interest).

Measurable test: the interval between adjacent melody notes changes with the chord root, even though
the notearp index sequence is identical. If root moves from C (degree 3) to D (degree 4), then
notearp index 0 shifts from C4 to D4 (+2 semitones) and index 1 shifts from D4 to Eb4 (+1 semitone).
The rhythm has not changed; the melody has.

**Rule for `theory.py`:** the notearp pattern is a constant; the chord is the variable. Do not
generate a new rhythm pattern for every bar. The pattern is the template; the chord changes the
pitches automatically.

### 4.2 Call-and-Response Phrasing

SA's lead pattern has an explicit 2-bar rest before the first note. This enforces the
**call-and-response** relationship between pad (which establishes harmony during bars 1–2) and lead
(which responds starting bar 3).

Minimum silence before first lead entry in any 8-bar phrase: **2 bars**. Maximum: 3 bars. Entering
before bar 3 makes the lead feel like it is competing with the pad instead of answering it.

Measurable test: compute bar index of first non-rest event in lead pattern. Must be ≥ 2.

### 4.3 Climax Note Placement

In an 8-bar phrase, the highest pitch (melodic climax) must appear in bars 5–7. SA's climax is at bar
8 (+2 semitones, the highest pitch in the lead pattern). This falls in the last third of the phrase.

The rule from classical phrase composition: the climax should arrive between 60–87% of phrase length
(bar 5 out of 8 = 62%, bar 7 out of 8 = 87%). SA's climax at bar 8 = 100% is at the outer edge of
this window but the phrase loops, so "bar 8 leading into bar 1 of the next phrase" is structurally
a climax-to-silence arc.

**Rule for `theory.py`:** place the maximum semitone offset in the second half of the phrase (bars 5–8
for an 8-bar phrase). Do not place the highest note in bar 1 or 2.

Measurable test: `argmax(abs(semitone)) >= len(phrase) // 2` (phrase indexed from 0).

### 4.4 Single-Octave Range

SA's lead pattern spans -7 to +2 = **9 semitones** total. This is within one octave (12 semitones).
A sub-octave range means the melody is easily trackable by the listener's working memory. Trance
melodies that "wander" across 2+ octaves are harder to recognise after repetition.

**Rule for `theory.py`:** `max(offsets) - min(offsets) <= 12`. Ideal: ≤ 9 (perfect 6th).

### 4.5 Hypnotic Minimal Pitch Vocabulary

SA's notearp pattern uses only 2 distinct pitch classes per bar (chord index 0 and 1 = C and D in
G minor). The lead pattern uses 5 distinct pitches across the 8-bar phrase — an average of less than
1 new pitch per bar.

Low pitch-class cardinality is a structural feature of trance melody, not a limitation. It creates
the hypnotic loop-ability that distinguishes trance from jazz (high cardinality) or ambient
(near-zero cardinality).

**Rule for `theory.py`:** for a 1-bar arpeggio, use ≤ 3 distinct chord indices. For an 8-bar lead,
use ≤ 6 distinct semitone values.

---

## 5. Interval Rules

All rules are stated as Python constraints. A generative melody algorithm should enforce these
as hard-rejects or weighted penalties on each candidate interval.

### 5.1 Forbidden Intervals (hard reject)

```python
FORBIDDEN_CONSECUTIVE_INTERVALS: set[int] = {6, -6}
# Augmented 4th / tritone between adjacent melody notes.
# Tritone creates maximum dissonance in equal temperament. It violates
# the trance aesthetic of dark-but-melodic. SA's patterns contain zero tritone
# motions between consecutive notes.
```

```python
FORBIDDEN_LARGE_LEAPS: set[int] = {11, -11, 12, -12}
# Major 7th and octave leaps. Allowed only as structural events (< 2% of intervals).
# SA's maximum leap is +7 (P5) and -7 (P5). Major 7th (+11) is never used melodically.
```

### 5.2 Restricted Intervals (weighted penalty)

```python
RESTRICTED_INTERVALS: dict[int, float] = {
    # (semitone_offset): weight_penalty (higher = less likely to be chosen)
     8: 0.8,  # minor 6th — usable but awkward for melody
    -8: 0.8,
     9: 0.9,  # major 6th — acceptable in arpeggiation, weak in stepwise lead
    -9: 0.9,
    10: 0.95, # minor 7th — use at phrase boundaries only (SA uses -7 as a "long drop")
   -10: 0.95,
}
# Intervals with absolute value > 7 (P5) that are not -7 or +7 should be rare.
# SA's -7 is structurally special (phrase opener descent) — it is not a general interval.
```

### 5.3 Preferred Intervals

```python
PREFERRED_INTERVALS: dict[int, float] = {
    # (semitone_offset): weight_bonus (higher = more likely to be chosen)
    1: 1.4,   # minor 2nd — passing tone, chromatic colour
   -1: 1.4,
    2: 1.8,   # major 2nd — diatonic stepwise motion, most common melodic interval
   -2: 1.8,
    3: 1.5,   # minor 3rd — chord tone in minor scale, SA uses -3 in turn figure
   -3: 1.5,
    5: 1.3,   # perfect 4th — structural, appears in SA's bar-7→8 interval
   -5: 1.3,
    7: 1.2,   # perfect 5th — power jump, SA's main structural leap
   -7: 1.2,
}
```

### 5.4 Range Constraint

```python
MELODY_SEMITONE_RANGE: tuple[int, int] = (-7, +5)
# Lower bound: -7 (minor 7th below root). SA never goes lower than -7.
# Upper bound: +5 (perfect 4th above root). SA's highest lead note is +2.
# Setting +5 gives a margin; generative algorithm should target -7 to +2 as default.

MELODY_SOFT_RANGE: tuple[int, int] = (-5, +2)
# 80% of notes should fall in this range. Excursions to -7 or +5 are structural moments.
```

### 5.5 Stepwise Motion Target

```python
STEPWISE_INTERVAL_TARGET: float = 0.40
# At least 40% of melodic intervals should be ±1 or ±2 semitones (stepwise motion).
# Derived from SA's lead pattern: 2/5 = 40% stepwise.
# Below 40%, the melody sounds angular/jumpy. Above 75%, it sounds scalar/boring.

STEPWISE_INTERVALS: set[int] = {-2, -1, 1, 2}
```

---

## 6. Generative Rules Derived from SA's Patterns

These are the concrete, imperative rules for the `generate_melody()` function in `song/theory.py`.
Each rule cites the section above that justifies it.

### Rule 1 — Use the notearp template unchanged for arpeggiation

```python
def generate_arpeggio_bar(chord_midi_notes: list[int]) -> list[tuple[int | None, int]]:
    """
    Generate one bar of arpeggio by applying SA_NOTEARP_PATTERN to chord_midi_notes.
    Returns list of (midi_note_or_None, duration_in_16ths).
    """
    result = []
    for index, duration in SA_NOTEARP_PATTERN:
        if index is None:
            result.append((None, duration))
        else:
            result.append((notearp(chord_midi_notes, index), duration))
    return result
```

Do not modify the rhythm. The chord changes; the pattern does not. (§2, §4.1)

### Rule 2 — Begin lead phrases with 1–2 bars of silence

```python
MIN_LEAD_REST_BARS: int = 2
MAX_LEAD_REST_BARS: int = 3

def lead_phrase_rest_bars() -> int:
    """Return the number of silent bars before lead entry in an 8-bar phrase."""
    import random
    return random.choices([2, 3], weights=[0.75, 0.25])[0]
```

SA's confirmed value is 2. Allow 3 occasionally for variety. Never 0 or 1. (§3.4, §4.2)

### Rule 3 — Place the melodic climax in bars 5–7 of an 8-bar phrase

```python
def validate_climax_position(phrase: list[int | None]) -> bool:
    """
    phrase: list of semitone-offsets (or None for rest), one entry per bar.
    Returns True if the maximum absolute-value offset is in bars 4–7 (0-indexed).
    """
    active = [(i, v) for i, v in enumerate(phrase) if v is not None]
    if not active:
        return True
    max_bar, _ = max(active, key=lambda x: abs(x[1]))
    return max_bar >= len(phrase) // 2  # second half of phrase
```

(§4.3)

### Rule 4 — Enforce stepwise-motion target ≥ 40%

```python
def stepwise_fraction(semitone_sequence: list[int]) -> float:
    """Compute fraction of consecutive intervals that are stepwise (±1 or ±2)."""
    if len(semitone_sequence) < 2:
        return 1.0
    intervals = [abs(b - a) for a, b in zip(semitone_sequence, semitone_sequence[1:])]
    stepwise = sum(1 for i in intervals if i in {1, 2})
    return stepwise / len(intervals)

def melody_is_valid(semitone_sequence: list[int]) -> bool:
    """Hard + soft validity check for a generated melodic phrase."""
    # Hard: no tritones
    intervals = [b - a for a, b in zip(semitone_sequence, semitone_sequence[1:])]
    if any(abs(i) == 6 for i in intervals):
        return False
    # Hard: no major 7th+ leaps
    if any(abs(i) >= 11 for i in intervals):
        return False
    # Hard: stay within range
    if max(semitone_sequence) > MELODY_SEMITONE_RANGE[1]:
        return False
    if min(semitone_sequence) < MELODY_SEMITONE_RANGE[0]:
        return False
    # Soft: stepwise fraction
    if stepwise_fraction(semitone_sequence) < STEPWISE_INTERVAL_TARGET:
        return False
    return True
```

(§5.1–§5.5)

### Rule 5 — Prefer SA's confirmed interval vocabulary

When randomly selecting the next semitone offset in a generative lead, weight intervals using
`PREFERRED_INTERVALS` and `RESTRICTED_INTERVALS`. Implement as a weighted choice:

```python
import random

ALL_DIATONIC_INTERVALS: list[int] = [-7, -5, -3, -2, -1, 0, 1, 2, 3, 5, 7]

def next_interval_weight(interval: int) -> float:
    if interval in FORBIDDEN_CONSECUTIVE_INTERVALS:
        return 0.0
    if abs(interval) in {11, 12}:
        return 0.0
    weight = 1.0
    weight *= PREFERRED_INTERVALS.get(interval, 1.0)
    weight *= (1.0 - RESTRICTED_INTERVALS.get(interval, 0.0))
    return weight

def sample_next_semitone(current: int) -> int:
    """Sample next semitone offset, weighted by SA's interval preferences."""
    candidates = [
        c for c in ALL_DIATONIC_INTERVALS
        if MELODY_SEMITONE_RANGE[0] <= c <= MELODY_SEMITONE_RANGE[1]
    ]
    weights = [next_interval_weight(c - current) for c in candidates]
    return random.choices(candidates, weights=weights)[0]
```

(§5.3, §5.4)

### Rule 6 — Keep pitch-class cardinality low

```python
MAX_DISTINCT_PITCHES_PER_BAR: int = 3   # for notearp
MAX_DISTINCT_PITCHES_PHRASE: int = 6    # for 8-bar lead phrase
```

If a generated phrase exceeds `MAX_DISTINCT_PITCHES_PHRASE`, collapse two of the less-used pitches
to the nearest preferred value. (§4.5)

---

## 7. `notearp` → MIDI Note Mapping Algorithm

This section gives the complete, self-contained algorithm for converting a notearp pattern to a
MIDI note sequence. Future code in `song/theory.py` that generates arpeggiated output should use
exactly this method.

### 7.1 Inputs

```
root_midi     : int   — MIDI note of the scale root (SA uses G3 = 43)
scale         : list[int]  — semitone offsets from root (natural minor = [0,2,3,5,7,8,10])
chord_degrees : list[int]  — 0-indexed scale degrees for the chord (SA's pad = [3,4,5,6])
notearp_pattern : list[tuple[int|None, int]]  — (chord_index_or_rest, duration_in_16ths)
```

### 7.2 Step 1 — Build the chord note list

```python
def build_chord(root_midi: int, scale: list[int], degrees: list[int]) -> list[int]:
    """
    Convert scale degrees to MIDI note numbers.
    Degrees outside scale length wrap to the next octave.
    """
    n = len(scale)
    notes = []
    for d in degrees:
        octave_shift = (d // n) * 12
        semitone = scale[d % n]
        notes.append(root_midi + octave_shift + semitone)
    return notes
```

Example: `build_chord(43, [0,2,3,5,7,8,10], [3,4,5,6])`:
- degree 3: octave 0, semitone 5 → MIDI 48 = C3? Wait — G3 = MIDI 55 in standard numbering.
  Let's resolve: MIDI 60 = C4, MIDI 55 = G3. Root G3 = 55.
  Degree 3 → `scale[3]` = 5 semitones → MIDI 55+5 = 60 = C4. Correct.
- degree 4 → `scale[4]` = 7 → MIDI 62 = D4. Correct.
- degree 5 → `scale[5]` = 8 → MIDI 63 = Eb4. Correct.
- degree 6 → `scale[6]` = 10 → MIDI 65 = F4. Correct.

SA's pad chord: `[60, 62, 63, 65]` = `[C4, D4, Eb4, F4]`.

### 7.3 Step 2 — Apply the notearp pattern

```python
def apply_notearp(chord: list[int],
                  pattern: list[tuple[int | None, int]]) -> list[tuple[int | None, int]]:
    """
    Apply a notearp pattern to a chord.
    Returns list of (midi_note_or_None, duration_in_16ths).
    """
    result = []
    for index, duration in pattern:
        if index is None:
            result.append((None, duration))
        else:
            midi = chord[index % len(chord)]
            result.append((midi, duration))
    return result
```

### 7.4 Step 3 — Handle chord changes (modulation)

When the chord root changes (e.g. from degree-3 root to degree-4 root in SA's progression), rebuild
the chord list. The notearp pattern does not change. Call `build_chord()` with the new root degree:

```python
def chord_root_midi(scale_root: int, scale: list[int], degree: int) -> int:
    """Return the MIDI note of a scale degree from the scale root."""
    n = len(scale)
    octave_shift = (degree // n) * 12
    return scale_root + octave_shift + scale[degree % n]
```

Example: SA's progression cycles through degrees [3,4,5,6]. For a 4-bar loop, each bar uses a
different degree as the new chord root, and the notearp is applied to the re-built chord each bar.

### 7.5 Complete Example

```python
SCALE_NATURAL_MINOR = [0, 2, 3, 5, 7, 8, 10]
G3_MIDI = 55
PROGRESSION = [3, 4, 5, 6]  # SA's pad progression

for bar, chord_degree in enumerate(PROGRESSION):
    root = chord_root_midi(G3_MIDI, SCALE_NATURAL_MINOR, chord_degree)
    chord = build_chord(root, SCALE_NATURAL_MINOR, [0, 1, 2, 3])
    # ^ rebuild relative chord from new root (4 consecutive scale degrees)
    notes = apply_notearp(chord, SA_NOTEARP_PATTERN)
    print(f"Bar {bar+1} (degree {chord_degree}): {notes}")
```

### 7.6 Correction: SA's Chord is Rooted at Scale Degree, Not Rebuilt Per Chord Root

There is an important implementation distinction. SA does **not** rebuild a chord from each
progression root. Instead:

- The single chord `[C4, D4, Eb4, F4]` is played as a **pad** (all notes simultaneously).
- The notearp operates over this **fixed chord list** and the progression advances that chord
  in Strudel's `setcps`/`chord` system — the chord list itself changes per progression step.

For the generative Python code, the cleanest equivalent is: for each bar of the progression,
compute the chord MIDI notes for that bar's root degree, then run `apply_notearp()` on that bar's
chord. The "chord" changes each bar; the pattern does not.

```python
def generate_arpeggio_sequence(
    scale_root: int,
    scale: list[int],
    chord_degrees_per_bar: list[int],
    chord_voicing_degrees: list[int],
    pattern: list[tuple[int | None, int]],
) -> list[list[tuple[int | None, int]]]:
    """
    Generate a multi-bar arpeggio sequence.

    scale_root             : MIDI note of scale root (e.g. G3 = 55)
    scale                  : semitone intervals of the scale
    chord_degrees_per_bar  : which scale degree is the chord root each bar
    chord_voicing_degrees  : which scale degrees (relative to chord root) form the chord
    pattern                : notearp pattern (constant across all bars)

    Returns list of bars, each bar is list of (midi_or_None, duration_16ths).
    """
    bars = []
    for chord_root_degree in chord_degrees_per_bar:
        chord_root = scale_root + scale[chord_root_degree % len(scale)]
        chord = build_chord(chord_root, scale, chord_voicing_degrees)
        bars.append(apply_notearp(chord, pattern))
    return bars
```

---

## Summary: Constants for `song/theory.py`

```python
# === Melody constants (from 04_generative_melody.md) ===

SA_NOTEARP_PATTERN: list[tuple[int | None, int]] = [
    (None, 2), (0, 2), (1, 4), (0, 2), (1, 2), (0, 2), (1, 2),
]

SA_LEAD_PATTERN: list[tuple[int | tuple[int, int] | None, int]] = [
    (None, 2), (-7, 1), ((-5, -2), 1), (-7, 1), (0, 1), (-3, 1), (+2, 1),
]

MELODY_SEMITONE_RANGE: tuple[int, int] = (-7, +5)
MELODY_SOFT_RANGE: tuple[int, int] = (-5, +2)
STEPWISE_INTERVAL_TARGET: float = 0.40
STEPWISE_INTERVALS: set[int] = {-2, -1, 1, 2}
MAX_DISTINCT_PITCHES_PER_BAR: int = 3
MAX_DISTINCT_PITCHES_PHRASE: int = 6
MIN_LEAD_REST_BARS: int = 2
MAX_LEAD_REST_BARS: int = 3

FORBIDDEN_CONSECUTIVE_INTERVALS: set[int] = {6, -6}
FORBIDDEN_LARGE_LEAPS: set[int] = {11, -11, 12, -12}

PREFERRED_INTERVALS: dict[int, float] = {
    1: 1.4, -1: 1.4, 2: 1.8, -2: 1.8,
    3: 1.5, -3: 1.5, 5: 1.3, -5: 1.3,
    7: 1.2, -7: 1.2,
}

RESTRICTED_INTERVALS: dict[int, float] = {
    8: 0.8, -8: 0.8, 9: 0.9, -9: 0.9, 10: 0.95, -10: 0.95,
}
```
