# SA Vocabulary Codified: Pattern Parameters for `song/theory.py`

This document is the authoritative source for all SA-specific synthesis constants. Every value
derives from OCR analysis of 5 Switch Angel Strudel.cc session recordings. Where a value is
directly visible in the OCR output it is marked **[SA confirmed]**. Derived values (computed from
confirmed formulas or confirmed patterns) are marked **[derived]**.

Style target: **Switch Angel (SA)** — procedural trance at 140 BPM, key of G natural minor, live-
coded in Strudel.cc. All Strudel degree values are **0-indexed** (degree 0 = root note = G).

Scale reference for G natural minor: `0=G, 1=A, 2=Bb, 3=C, 4=D, 5=Eb, 6=F`

---

## 1. Pad Chord Progression

### 1.1 Strudel Source Pattern

```
<3@3 4 5@3 6>*2
```

**[SA confirmed]** Observed in multiple sessions as the primary pad harmonic motion.

The outer `<...>*2` means the sequence runs at 2x bar rate. The `@3` weight makes degrees 3 and 5
each three times as long as their neighbours. Unpacked rhythm over one pass:

| Step weight | Degree | Duration (relative) |
|-------------|--------|---------------------|
| @3          | 3      | 3 units             |
| 1           | 4      | 1 unit              |
| @3          | 5      | 3 units             |
| 1           | 6      | 1 unit              |

Total: 8 units per pass. Degrees 3 and 5 each occupy 3/8 of the cycle; degrees 4 and 6 each occupy
1/8. The progression is **rhythmically asymmetric**: two long chords flanking two short chords.
This asymmetry prevents the four-chord sequence from feeling metronomic.

### 1.2 Scale Degree Table (G Natural Minor)

| Strudel degree | Semitone offset | Note | Triad within G minor      | Roman numeral |
|----------------|-----------------|------|---------------------------|---------------|
| 3              | 5               | C    | C – Eb – G (minor)        | iv            |
| 4              | 7               | D    | D – F – A (minor)         | v             |
| 5              | 8               | Eb   | Eb – G – Bb (major)       | bVI           |
| 6              | 10              | F    | F – A – C (major)         | bVII          |

### 1.3 Harmonic Analysis: C → D → Eb → F

The bass motion is: C → D (whole step) → Eb (half step) → F (whole step). Voice-leading is smooth;
no voice moves more than a major second. This stepwise ascent through the upper tetrachord of G
minor (C D Eb F) is the defining feature of the progression.

**Chord qualities:** Degrees 3 and 4 are minor chords, built entirely within the G minor scale.
Degrees 5 and 6 are major chords. A chord's quality is determined by whether its third is major or
minor: on Eb, the third is G (4 semitones = major third); on F, the third is A (4 semitones = major
third). Both are major triads even though they are diatonic to G natural minor.

**The bVI → bVII trance lift:** The motion from Eb major to F major is the most characteristic sound
in the style. Both chords are borrowed from G natural minor's own diatonic set, yet both are major —
the opposite quality of the tonic chord (G minor). Moving between two consecutive major chords a
whole step apart (Eb to F) creates a brief moment of unambiguous brightness inside the minor context.
This is the "trance lift": the listener hears major quality twice in succession, generating a
euphoric surge before the cycle resets to the darker iv and v chords. The effect depends on position
in the cycle — it only works because the lift chords arrive after the two minor chords have
established the dark foundation.

**Why not i?** SA's progression deliberately omits the tonic chord (G minor, degree 0). The cycle
never lands on the chord whose root matches the key center. This creates **unresolved harmonic
motion**: the progression implies G minor as its home without ever explicitly stating it. The ear
expects resolution to G minor that never arrives, producing the continuous forward propulsion
characteristic of looping trance.

### 1.4 Python Constants

```python
# song/theory.py
PAD_PROGRESSION: list[int] = [3, 4, 5, 6]          # [SA confirmed] Strudel degrees in G minor
PAD_RHYTHM_WEIGHTS: list[int] = [3, 1, 3, 1]        # [SA confirmed] @3 durations per degree
```

---

## 2. Pad Synthesis Chain

### 2.1 Filter: `lpenv(2)` — Not Acidenv

SA's pad uses `.lpenv(2)`, **not** an acidenv. **[SA confirmed]**

The distinction matters:
- **`lpenv(amount)`**: the low-pass filter opens by a fixed `amount` (in octaves or filter units)
  on each note trigger, then closes slowly according to a release envelope. The filter movement is
  smooth and sustained — a gradual swell. Amount = 2 means the filter opens two units above its
  base cutoff position on each new chord trigger.
- **acidenv (`.lpenv(x*9).lps(.2).lpd(.12).lpq(2)`)**: very short decay (120 ms), high resonance
  (Q=2), large amount (x*9). Creates a percussive "blip" — the filter opens and closes within one
  note event. This is the 303 acid character. See Section 3.3.

The pad's `lpenv(2)` creates a **pad swell**: each new chord trigger causes a gentle filter opening
that sustains for the chord duration, then the filter gradually closes before the next trigger. This
is the correct behaviour for a smooth atmospheric pad. An acidenv on the pad would produce a
percussive texture incompatible with the sustained pad function.

### 2.2 Trancegate: `trancegate(1.5, 45, 1)`

**[SA confirmed]**

| Parameter | Value | Meaning |
|-----------|-------|---------|
| Speed     | 1.5   | 1.5 gate cycles per bar = 3 cycles per 2 bars |
| Angle     | 45    | Equal rise/fall time (symmetrical cosine envelope) |
| Depth     | 1     | Full amplitude modulation (gate closes to silence) |

The rate 1.5 creates a **3:2 polyrhythm** against the 4/4 bar: the gate resolves to its starting
phase only every 2 bars, maintaining rhythmic forward motion between bar lines. A rate of 1.0 or
2.0 would align on every bar and feel static. See `01_trance_harmony.md §6` for full polyrhythm
analysis.

### 2.3 Sidechain: `.duck("3:4:5").duckattack(.16).duckdepth(.6)`

**[SA confirmed]**

| Parameter       | Value | Meaning |
|-----------------|-------|---------|
| Target pattern  | 3:4:5 | Duck on the kick bus (SuperCollider bus 3:4:5) |
| Duck attack     | 0.16  | Sidechain compressor attack = 160 ms |
| Duck depth      | 0.6   | Gain reduction depth = 60 % amplitude reduction on kick hit |

The 160 ms attack means the pad does not duck instantly on the kick transient; it ducks slightly
late, allowing the kick click to pass through cleanly before the pad volume pulls back. This is
intentional — it preserves the kick's transient punch while still creating the pumping effect in
the 150–300 ms post-transient window.

Depth 0.6 means at maximum duck the pad drops to 40% of its normal amplitude (i.e. −8 dB). This
is a moderate pump — audible but not violent. A depth of 1.0 would create a full mute, which would
destroy the pad's atmospheric character.

### 2.4 Python Constants

```python
# song/theory.py
PAD_GAIN: float = 0.50          # [SA confirmed] .pg(.5)
PAD_LPENV_AMOUNT: float = 2.0   # [SA confirmed] lpenv(2) — pad swell, not acid
TRANCEGATE_RATE: float = 1.5    # [SA confirmed] cycles per bar
TRANCEGATE_ANGLE: int = 45      # [SA confirmed] degrees — symmetrical cosine
TRANCEGATE_DEPTH: int = 1       # [SA confirmed] full depth
DUCK_ATTACK: float = 0.16       # [SA confirmed] sidechain attack in seconds
DUCK_DEPTH: float = 0.6         # [SA confirmed] amplitude reduction depth
```

---

## 3. Lead Melodic Patterns

### 3.1 Notearp Source Pattern

```
"< <- - - -> 0 1@2 0 1 0 1>*16"
```

**[SA confirmed]** Used from bar 24 onward when `lead_melody_on` fires.

The outer `<...>*16` runs the sequence at 16x bar rate (16th-note resolution). The inner `<...>`
is a cycling sequence. Parsing the inner sequence item by item:

| Item | Strudel value | Steps | Content |
|------|---------------|-------|---------|
| `<-` | rest (opening cycle bracket) | — | begins silence block |
| `-`  | rest | 1/16 | |
| `-`  | rest | 1/16 | |
| `-`  | rest | 1/16 | |
| `->` | rest (closing cycle bracket) | — | ends silence block |
| `0`  | chord index 0 | 1/16 | root note of current chord |
| `1@2`| chord index 1, held 2 units | 2/16 | second note, held for an eighth |
| `0`  | chord index 0 | 1/16 | root |
| `1`  | chord index 1 | 1/16 | second note |
| `0`  | chord index 0 | 1/16 | root |
| `1`  | chord index 1 | 1/16 | second note |

The first 4/16 of the cycle are silent. Melodic activity begins at step 5 (the back half of the
bar). The `1@2` hold creates a syncopation: the second note is held across the step boundary,
displacing the subsequent attacks and creating an irregular, non-grid melodic surface.

### 3.2 Interval Content

In the context of the pad progression (degrees 3, 4, 5, 6), chord index 0 and index 1 refer to
the two lowest notes of each chord. In G minor:

| Pad chord | Index 0 | Index 1 | Interval |
|-----------|---------|---------|----------|
| C minor (deg 3) | C | Eb | minor 3rd (3 semitones) |
| D minor (deg 4) | D | F  | minor 3rd (3 semitones) |
| Eb major (deg 5)| Eb | G | major 3rd (4 semitones) |
| F major (deg 6) | F  | A | major 3rd (4 semitones) |

The lead arpeggiates the bottom two notes of each underlying chord. The minor/major 3rd shift that
occurs when the chord changes from minor to major is the source of the characteristic melodic
brightness on the bVI and bVII chords.

### 3.3 Back-Loaded Rhythm

The 4-step silence at the start creates a **back-loaded rhythm**: the first three beats of the bar
are empty; the melodic content fires in the second half. Against a kick pattern that hits on beats
1 and 3 (steps 0 and 8 in 16th-note steps), the lead's silence on beats 1–3 lets the kick occupy
the structural downbeats while the lead fills the upbeat and "and" positions. This is the standard
trance lead/kick interlocking strategy: kick on the grid, melody between the grid lines.

### 3.4 Python Constants

```python
# song/theory.py
LEAD_NOTEARP_RESTS: int = 4          # [SA confirmed] 4 silent 16th-note steps at bar start
LEAD_NOTEARP_INDICES: list[int] = [0, 1]  # [SA confirmed] arpeggiate chord indices 0 and 1
LEAD_NOTEARP_HOLD: int = 2           # [SA confirmed] index 1 held for 2 units (@2)
```

---

## 4. Lead Synthesis Chain

### 4.1 Acidenv Parameters

SA's lead uses `lpf(100).lpenv(x*9).lps(.2).lpd(.12).lpq(2)` where `x` is the acidenv amount
slider. **[SA confirmed]**

| Parameter | Value   | Meaning |
|-----------|---------|---------|
| `lpf(100)`| 100 Hz  | Base filter cutoff (very low; nearly closed at rest) |
| `lpenv(x*9)` | x×9 | Filter envelope amount — scales with acidenv slider |
| `lps(.2)` | 0.2     | LP sustain level (filter stays 20% open during note hold) |
| `lpd(.12)`| 0.12 s  | LP decay = 120 ms — very fast, creates percussive blip |
| `lpq(2)`  | 2       | Filter resonance Q = 2 — moderate resonance peak at cutoff |

**How it works:** On each note attack, the filter opens to `100 + (x * 9)` units (the base plus the
envelope amount). Over the next 120 ms it decays to 20% of the envelope peak (the sustain level).
This 120 ms decay is fast enough that the filter closes within a single 16th note at 140 BPM
(1/16 bar = ~107 ms). The result is a sharp filter "blip" at each note onset: the classic acid
character. The base cutoff of 100 Hz ensures the synth is almost silent between notes, making the
blip the primary audible event on each trigger.

### 4.2 Lead Gain and Pan

**[SA confirmed]**

```python
LEAD_GAIN: float = 0.70    # [SA confirmed] .pg(.7)
```

No pan offset is confirmed from SA's sessions. Default: centred.

### 4.3 Python Constants

```python
# song/theory.py
LEAD_GAIN: float = 0.70          # [SA confirmed] .pg(.7)
ACID_LPF_BASE: float = 100.0     # [SA confirmed] lpf(100) base cutoff Hz
ACID_LPENV_SCALE: float = 9.0    # [SA confirmed] lpenv(x*9) scale factor
ACID_LPS: float = 0.2            # [SA confirmed] LP sustain 20%
ACID_LPD: float = 0.12           # [SA confirmed] LP decay 120 ms
ACID_LPQ: float = 2.0            # [SA confirmed] filter resonance Q
```

---

## 5. Filter Arc Mapped to Hz

SA's rlpf formula (all synths): `cutoff_hz = (slider * 12) ** 4`

**[SA confirmed]** The formula is nonlinear: doubling the slider value multiplies frequency by
16 (2^4). This matches perceptual logarithmic pitch scaling, compressing the useful control range
into a 0–1 slider.

### 5.1 Slider → Hz Conversion Table

| Arc point     | Slider `x` | `x × 12`  | `(x × 12)^4` | Hz (rounded) | Perceptual character |
|---------------|------------|-----------|--------------|--------------|----------------------|
| `arc_pullback`| 0.35       | 4.200     | 311.2        | **311 Hz**   | Muffled; only fundamental and 2–3 partials pass. Supersaw sounds near-sine. Pullback / tension hold. |
| `arc_start`   | 0.45       | 5.400     | 850.3        | **850 Hz**   | Warm opening. Low-mids present. Pad sounds full but not bright. Early build. |
| `lead_base`   | 0.593      | 7.116     | 2564.2       | **2,564 Hz** | Lead default cutoff. Bright enough for melodic clarity, not harsh. [derived from confirmed slider] |
| `arc_mid`     | 0.60       | 7.200     | 2687.4       | **2,687 Hz** | Energetic mid-build peak. Harmonics to ~13th partial of 200 Hz root pass. |
| `arc_full_open`| 0.877     | 10.524    | 12266.6      | **12,267 Hz**| Fully open. All audible harmonics pass. Maximum brightness. Climax. **[SA confirmed]** |

### 5.2 Physical Interpretation

At 311 Hz with a root of G2 (98 Hz): only the fundamental (98 Hz) and 2nd harmonic (196 Hz) pass;
3rd harmonic at 294 Hz is near the cutoff. The sound is nearly sine-like. The filter makes the same
synthesiser chord sound completely different — not a subtle colour shift but a near-total timbral
transformation.

At 12,267 Hz: the −3 dB point is above the highest audible frequency for most listeners (~16 kHz).
The filter is effectively open. The supersaw's full harmonic stack (100+ partials) passes without
attenuation.

The ratio between `arc_pullback` and `arc_full_open` is 12,267 / 311 = **39.4×** — nearly 6
octaves of timbral range from a single slider traversal from 0.35 to 0.877.

### 5.3 Python Constants

```python
# song/theory.py
FILTER_PULLBACK: float = 0.35    # [SA confirmed] 311 Hz — dark pullback
FILTER_START: float = 0.45       # [SA confirmed] 850 Hz — warm opening
FILTER_LEAD_BASE: float = 0.593  # [SA confirmed] 2564 Hz — lead default
FILTER_MID: float = 0.60         # [SA confirmed] 2687 Hz — mid-build
FILTER_OPEN: float = 0.877       # [SA confirmed] 12267 Hz — full open / climax

def rlpf_hz(slider: float) -> float:
    """SA's confirmed rlpf formula: cutoff_hz = (slider * 12) ** 4"""
    return (slider * 12) ** 4
```

---

## 6. Build Order Timing

Session reference: `GWXCCBsOMSg` (SA session, confirmed timing). All bar numbers assume
140 BPM, 4/4. One bar = 60/140 × 4 = **1.714 seconds**.

### 6.1 11-Stage Table

| Stage | Bar | Voice / Event     | Cumulative time | Musical justification |
|-------|-----|-------------------|-----------------|-----------------------|
| 1     | 0   | `kick_on`         | 0:00            | Establishes tempo and rhythmic grid first. All other elements are measured against the kick. No harmonic content; listener orients purely to BPM. |
| 2     | 2   | `pad_root_on`     | 0:03            | Root pad (no chord motion yet) introduces key and timbre. The `−14/−21` doublings fill the low end immediately. Two bars of kick-only is enough to establish tempo; any longer delays harmonic content past the engagement threshold. |
| 3     | 8   | `lead_root_on`    | 0:14            | Single-note lead introduces melodic expectation without revealing the full melodic idea. 6 bars after the pad gives the pad time to establish the harmonic colour before the lead competes for the listener's attention. |
| 4     | 24  | `lead_melody_on`  | 0:41            | Notearp + delay. The back-loaded 16-step pattern and delay feedback introduce rhythmic complexity. 16 bars of root lead is long enough that the melody feels like an upgrade, not an interruption. |
| 5     | 40  | `pad_chord_on`    | 1:09            | First harmonic movement: [3,4,5,6] progression begins + seg16 sequencer. Placed after the melody is established so the chord changes are heard as the melody's harmonic environment rather than a competing element. The asymmetric rhythm weights (3:1:3:1) are immediately noticeable against the established straight rhythm. |
| 6     | 48  | `lead_voicing_on` | 1:23            | Lead adapts voicing to track the chord changes. 8 bars of chord-only (bars 40–48) lets the listener learn the new harmonic cycle before the lead changes behaviour. |
| 7     | 72  | `clap_on`         | 2:03            | Backbeat clap on beats 2 and 4. Placed after 24 bars of full harmonic/melodic content; the clap locks the rhythmic grid and sharply raises perceived energy. The long gap before the clap makes its entry a clear milestone. |
| 8     | 96  | `fm_on`           | 2:44            | FM texture adds inharmonic upper partials. Spectral complexity added late so it does not compete with melodic clarity during the melody-establishment phase (bars 8–72). Heard as "the sound opening up fully". |
| 9     | 108 | `pulse_on`        | 3:05            | Mid-range pulse synth adds rhythmic density. |
| 10    | 112 | `hihat_on`        | 3:12            | 16th-note hihat fills the rhythmic grid completely. The tri LFO on decay creates accent variation (see Section 7). Placed near the end so the full-grid hihat reads as the final rhythmic layer. |
| 11    | 116 | `kick_syncopated` | 3:19            | Kick pattern shifts from straight 4-on-the-floor to syncopated pattern (steps 0,4,8,11,14). The anticipation hits at steps 11 and 14 (see Section 7) are the final layer of rhythmic complexity, producing the "trance pump" forward drive. |

### 6.2 Pacing Principle

No two large elements enter simultaneously. Each stage adds exactly one new dimension:

- Stages 1–3: **groove** (kick) → **harmony** (pad root) → **melody hint** (lead root)
- Stages 4–6: **melodic complexity** (notearp) → **harmonic motion** (chords) → **melodic
  adaptation** (lead voicing)
- Stages 7–9: **rhythmic density** (clap, FM, pulse)
- Stages 10–11: **grid completion** (hihat) → **rhythmic displacement** (syncopated kick)

The total arc spans 116 bars = ~3:20 at 140 BPM.

### 6.3 Python Constants

```python
# song/theory.py
BUILD_STAGES: dict[str, int] = {
    "kick_on":           0,    # [SA confirmed] GWXCCBsOMSg session
    "pad_root_on":       2,    # [SA confirmed]
    "lead_root_on":      8,    # [SA confirmed]
    "lead_melody_on":    24,   # [SA confirmed]
    "pad_chord_on":      40,   # [SA confirmed]
    "lead_voicing_on":   48,   # [SA confirmed]
    "clap_on":           72,   # [SA confirmed]
    "fm_on":             96,   # [SA confirmed]
    "pulse_on":          108,  # [SA confirmed]
    "hihat_on":          112,  # [SA confirmed]
    "kick_syncopated":   116,  # [SA confirmed]
}
BARS_PER_SECOND: float = 140 / 60 / 4   # 0.583 bars/sec at 140 BPM
```

---

## 7. Confirmed Gain Table

All values from OCR of SA session recordings. **[SA confirmed]** unless noted.

| Voice   | Strudel call  | Gain value | dBFS (approx.) | Notes |
|---------|---------------|------------|----------------|-------|
| kick    | `.gain(1)`    | **1.00**   | 0 dBFS         | Full amplitude reference. All other gains are relative to kick. |
| pad     | `.pg(.5)`     | **0.50**   | −6 dBFS        | Pad sits 6 dB below kick. Leaves headroom for ducking. |
| lead    | `.pg(.7)`     | **0.70**   | −3 dBFS        | Lead sits 3 dB below kick; 3 dB above pad. Melodic foreground. |
| hihat   | `.gain(.5)`   | **0.50**   | −6 dBFS        | Matches pad level; hihat is texture not foreground. |
| clap    | `.pg(.7)`     | **0.70**   | −3 dBFS        | Matches lead level; clap marks the backbeat at equal prominence to the melody. |
| pulse   | —             | **~0.12**  | ~−18 dBFS      | [inferred — no explicit gain in OCR] Pulse is background texture; low gain prevents masking lead. |

### 7.1 Mix Hierarchy

Reading the gain table as a mix hierarchy:

1. **Kick (1.0):** Loudest — the structural anchor. Every other voice is mixed below it.
2. **Lead / Clap (0.7):** Foreground melodic and rhythmic content. 30% below kick.
3. **Pad / Hihat (0.5):** Background texture and harmonic support. 50% below kick.
4. **Pulse (~0.12):** Deep background. 88% below kick. Inaudible as a distinct voice; contributes
   sub-mix density.

The −6 dB headroom between kick (1.0) and pad (0.5) is where the sidechain ducking operates. When
the kick hits, the pad ducks to 0.5 × (1 − 0.6) = **0.20** (−14 dBFS), then recovers. This
provides 14 dB of dynamic range for the pumping effect without the pad ever disappearing entirely.

### 7.2 Python Constants

```python
# song/theory.py
GAIN_KICK: float = 1.00     # [SA confirmed] .gain(1)
GAIN_PAD: float = 0.50      # [SA confirmed] .pg(.5)
GAIN_LEAD: float = 0.70     # [SA confirmed] .pg(.7)
GAIN_HIHAT: float = 0.50    # [SA confirmed] .gain(.5)
GAIN_CLAP: float = 0.70     # [SA confirmed] .pg(.7)
GAIN_PULSE: float = 0.12    # [inferred] no explicit OCR value
```

---

## 8. Kick and Hihat Pattern Details

### 8.1 Kick: `beat("0,4,8,11,14", 16)`

**[SA confirmed]**

The kick fires at 16th-note steps: **[0, 4, 8, 11, 14]**.

| Step | Beat position          | Type               |
|------|------------------------|--------------------|
| 0    | Beat 1 (downbeat)      | Structural         |
| 4    | Beat 2                 | Structural         |
| 8    | Beat 3                 | Structural         |
| 11   | "e" of beat 3 (3½)     | Anticipation hit   |
| 14   | "a" of beat 4 (4¾)     | Anticipation hit   |

Steps 0, 4, 8 are the straight 4-on-the-floor pattern minus beat 4 (step 12). Steps 11 and 14
replace the expected beat-4 hit with two anticipation hits: the kick arrives before the expected
downbeat positions, creating forward momentum. This is the **trance pump** mechanism — the kick
"reaches ahead" of the grid, pulling the listener forward.

### 8.2 Hihat: `.tri.fast(4).range(0.05, 0.12)`

**[SA confirmed]**

A triangle LFO at `fast(4)` (4× bar rate) modulates the hihat decay between 0.05 s (50 ms) and
0.12 s (120 ms). The LFO runs at 4 cycles per bar; in 4/4 this means **one LFO cycle per beat**.
A triangle LFO reaches its peak and trough once per cycle:

- **Peak decay (0.12 s):** hihat is louder and longer — accent hit.
- **Trough decay (0.05 s):** hihat is shorter and quieter — ghost hit.

One LFO cycle per beat means each beat has one accented hihat and the remaining subdivisions are
ghost hits. The accent falls on the beat itself; the intervening 16th notes are quiet. This produces
a perceived triplet-feel accent (accent → ghost → ghost → accent → ...) without requiring a triplet
time signature.

### 8.3 Python Constants

```python
# song/theory.py
KICK_STEPS: list[int] = [0, 4, 8, 11, 14]      # [SA confirmed] beat("0,4,8,11,14", 16)
KICK_RESOLUTION: int = 16                        # 16th-note grid
HIHAT_DECAY_MIN: float = 0.05                    # [SA confirmed] tri LFO trough
HIHAT_DECAY_MAX: float = 0.12                    # [SA confirmed] tri LFO peak
HIHAT_LFO_RATE: int = 4                          # [SA confirmed] .fast(4) — 4 cycles/bar
```

---

*Document version: 1.0. Sources: Switch Angel session OCR analysis, sessions including
`GWXCCBsOMSg`. All Hz values computed precisely using SA's confirmed `(x * 12) ** 4` formula.
Companion document: `01_trance_harmony.md` (scale theory, chord progressions, trancegate polyrhythm).*
