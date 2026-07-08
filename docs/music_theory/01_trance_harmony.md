# Trance Harmony: Theory Reference for `song/theory.py`

This document is the authoritative source for every musical constant in `song/theory.py`. Every Python
value in that file — scale intervals, chord degree lists, filter frequencies, build timings — cites a
section below. Nothing in this document is abstract: every claim maps directly to a constant or formula.

The style target throughout is **Switch Angel (SA)**: a procedural trance producer whose session
recordings were OCR-analysed to extract synthesis parameters. Where a value is confirmed from those
recordings it is marked **[SA confirmed]**.

---

## 1. Scales and Emotional Character

A scale is represented as a list of semitone offsets from the root (0 = root, integers ascending).
In Python: `SCALE_INTERVALS: list[int]`.

### 1.1 Natural Minor (Aeolian)

```
intervals = [0, 2, 3, 5, 7, 8, 10]
```

Degree names: root (0), M2 (2), m3 (3), P4 (5), P5 (7), m6 (8), m7 (10).

**SA uses this exclusively. Root = G.** The working key is therefore G natural minor:
`G – A – Bb – C – D – Eb – F`. **[SA confirmed]**

Why each interval produces the characteristic trance character:

- **Flat 3rd (Bb, +3 semitones):** creates minor quality. All chords built on the tonic are minor.
- **Flat 6th (Eb, +8 semitones):** this is the defining dark/tense colour. It sits a tritone above
  the dominant (D), creating harmonic dissonance that unresolved. The bVI chord (Eb major) built here
  is the most-used "lift" chord in uplifting trance because it is simultaneously inside the minor
  scale and strikingly consonant on its own.
- **Minor 7th (F, +10 semitones):** the scale has no leading tone (there is no F# pulling back to G).
  This keeps harmonic motion feeling cyclical and forward-driving rather than concluding. Trance tracks
  loop without resolution; the natural minor's open 7th enables that.

Emotional character: **tension, drama, euphoria**. The combination of the minor 3rd (drama) and the
bVI chord (euphoria) is the structural reason trance tracks feel simultaneously dark and uplifting.

### 1.2 Dorian

```
intervals = [0, 2, 3, 5, 7, 9, 10]
```

Degree names: root (0), M2 (2), m3 (3), P4 (5), P5 (7), **M6 (9)**, m7 (10).

Dorian is natural minor with the 6th raised one semitone (m6 → M6, e.g. Eb → E in G context). This
single change has large harmonic consequences: the iv chord becomes IV (major), and the bVI chord
becomes a tritone-free major chord. The result is noticeably more hopeful and forward-looking.

Emotional character: **dreamy, forward, less dark than Aeolian**. Use for "progressive" or melodic
sections where full minor darkness would be too heavy.

### 1.3 Major (Ionian)

```
intervals = [0, 2, 4, 5, 7, 9, 11]
```

Degree names: root (0), M2 (2), M3 (4), P4 (5), P5 (7), M6 (9), M7 (11).

The leading tone (+11) creates a strong pull back to the root. All tonic chords are major. No
flat-6th tension.

Emotional character: **bright, uplifting, resolved**. SA's "progressive" mood sections. The M3 (+4)
is the sole interval that completely eliminates minor ambiguity — every chord built diatonically is
consonant and unambiguous.

---

## 2. Canonical Trance Chord Progressions

Progressions are encoded as lists of **0-indexed scale degrees** (not MIDI notes, not Roman numerals).
Scale degree 0 = root note, degree 1 = second scale note, etc. This encoding is scale-agnostic:
the same degree list works in any key by looking up `SCALE_INTERVALS[degree] + root_midi`.

### 2.1 SA's Canonical Pad Progression — `[3, 4, 5, 6]`

Scale degrees 3, 4, 5, 6 in G natural minor correspond to notes:

| Degree | Semitone offset | Note in G minor |
|--------|-----------------|-----------------|
| 3      | 5               | C               |
| 4      | 7               | D               |
| 5      | 8               | Eb              |
| 6      | 10              | F               |

**[SA confirmed]** This progression is heard throughout SA's sessions as the primary pad movement.

This is **not** a conventional Roman-numeral progression. It is four consecutive scale steps starting
from the 4th degree (C), traversing the scale upward. The chords built on those roots (triads within
the G minor scale) are:

- **C (degree 3):** C–Eb–G = C minor (iv in G minor)
- **D (degree 4):** D–F–A = D minor (v in G minor; note: natural minor v is minor, not dominant)
- **Eb (degree 5):** Eb–G–Bb = Eb major (bIII in G minor) — **the trance lift chord**
- **F (degree 6):** F–A–C = F major (bVII in G minor)

The stepwise bass motion C → D → Eb → F (whole step, half step, whole step) creates smooth
voice-leading. The Eb major chord is the characteristic "trance lift": it is a major chord inside a
minor key, built on the flat-3rd degree. Its major quality against the minor context creates the
euphoric tension that defines the style.

### 2.2 Uplifting — `[0, 5, 2, 4]`

In G natural minor:

| Degree | Note | Chord           |
|--------|------|-----------------|
| 0      | G    | G minor (i)     |
| 5      | Eb   | Eb major (bVI)  |
| 2      | Bb   | Bb major (bIII) |
| 4      | D    | D minor (v)     |

Roman-numeral notation: **i – bVI – bIII – v** (sometimes written i–VI–III–VII when the minor
numerals are implied).

Why it works: the i → bVI motion is a descending minor 3rd in the bass; bVI → bIII is a descending
P4; bIII → v is a rising M2. The two major chords (bVI and bIII) provide the "uplifting" brightness
inside the minor key. This is the most widely used progression in euphoric/uplifting trance.

Emotional function: **classic euphoric trance**. The alternation between tonic minor and two major
chords creates the tension-release cycle that drives the genre.

### 2.3 Dark — `[0, 3, 0, 6]`

In G natural minor: Gm – Cm – Gm – Fm.

Roman numerals: **i – iv – i – viidim** (the F at degree 6 roots an F major chord in this context,
but with a diminished quality depending on voicing).

The return to i in the middle prevents harmonic departure; the iv and degree-6 chords are close
enough to i to feel like neighbours rather than escapes. The lack of the bVI "lift" chord keeps the
mood dark throughout.

Emotional function: **tense, driving, minimal harmonic variation**. Use for low-energy or night-mode
sections.

### 2.4 Acid — `[0, 2, 3, 2]`

In G natural minor: Gm – Bb – Cm – Bb.

The progression cycles through i → bIII → iv → bIII. The bIII chord (Bb major) appears twice,
framing the iv (Cm). Because bIII and iv share the Bb note (it is in both chords), the motion is
smooth. The return to bIII before the repeat creates a hypnotic two-chord oscillation at the macro
level (Gm/Bb alternation).

Emotional function: **hypnotic, looping, acid-adjacent**. Works with 303-style bass lines.

### 2.5 Progressive — `[0, 3, 4, 1]` (major key)

In C major: C – F – G – Dm.

Roman numerals: **I – IV – V – ii**.

The V chord (G major, degree 4) contains the leading tone B, which resolves up to C. The ii chord
(Dm) provides a pre-dominant function, making the I → IV → V → ii loop feel forward-moving rather
than static. This is a textbook functional major-key cycle.

Emotional function: **bright, resolved, progressive trance**. Use when the mood is positive and
unambiguous.

---

## 3. Voicing Theory: SA's `add("-14, -21")` Doublings

SA's SuperCollider pad synth uses `.add("-14,-21")` on every chord note. **[SA confirmed]**

This means each chord note N is sounded simultaneously at:
- N (original pitch)
- N − 14 semitones (one octave + minor 7th below, i.e. 14 = 12 + 2)
- N − 21 semitones (one octave + minor 7th + perfect 4th below, i.e. 21 = 12 + 2 + 7 = 14 + 7)

### Spectral and Mixing Function

For a chord rooted on G3 (MIDI 55, ~196 Hz), the doublings land at:

| Offset | MIDI | Frequency  | Register            |
|--------|------|------------|---------------------|
| 0      | 55   | ~196 Hz    | Tenor / lower mid   |
| −14    | 41   | ~87 Hz     | Bass (80–150 Hz)    |
| −21    | 34   | ~62 Hz     | Sub-bass (< 80 Hz)  |

The −14 doubling fills the **bass register (80–150 Hz)** without requiring a separate bass voice.
During the first 3 minutes of an SA session the bass synth has not yet entered; the pad's −14
doublings are the entire low end.

The −21 doubling adds **sub-bass weight below 80 Hz**. On a system with subwoofer reproduction this
creates the physical impact characteristic of SA's mix.

The practical result: the pad is a three-register instrument. Its upper voices carry melody and
harmonic colour; its lower doublings carry bass energy. This is why SA's mix has audible low-end
density from the very first bar, even though the explicit bass synth voice is absent.

**Python implementation note:** `chord_doublings: list[int] = [-14, -21]`. Apply by extending each
chord note's MIDI list with `[note + d for d in chord_doublings]`.

---

## 4. Tension/Release Mechanics in SA's 11-Stage Build Arc

SA's build order has been confirmed from session recordings. The following maps each stage to a
tension/release narrative. Bar numbers assume 140 BPM, 4/4, with one bar = ~1.71 seconds.

| Bars      | Stage / Voice Added          | Tension Level | Harmonic/Rhythmic Mechanism |
|-----------|------------------------------|---------------|-----------------------------|
| 0–8       | Kick + pad root only         | Minimal       | Root pedal establishes key and tempo groove. No harmonic movement. |
| 8–24      | Lead root note enters        | Low           | Single-note lead creates melodic expectation. Harmonic content unchanged (still root). |
| 24–40     | Lead melody + delay          | Rising        | Notearp pattern introduces rhythmic syncopation against the 4/4 kick. Delay feedback creates polyrhythmic density. |
| 40–48     | Pad chord progression + seg16 | Medium        | First harmonic movement: the [3,4,5,6] progression begins. The seg16 euclidean sequencer adds sub-beat rhythmic detail. Harmonic tension releases as the chord cycle establishes itself. |
| 48–72     | Lead voicing shift           | Medium-high   | Lead adapts to chord progression, adding harmonic colour to the melody. Tension sustained by ongoing harmonic cycle. |
| 72–96     | Clap enters                  | High          | Backbeat clap on beats 2 and 4 locks the rhythmic grid; perceived energy increases sharply. |
| 96–108    | FM modulation opens          | Peak harmonic | The FM texture adds upper partials and inharmonic content. Perceived "brightness" and complexity peaks. |
| 108–120   | Pulse + hihat                | Maximum total | All voices active. Hihat fills the 16th-note grid; pulse synth adds mid-range density. |
| 116+      | Kick → syncopated pattern    | Final peak    | Off-beat kick hits replace the straight 4-on-the-floor pattern, adding the final layer of rhythmic complexity before any plateau. |

### Why This Arc Works

The build never introduces two large elements simultaneously. Each new voice adds exactly one new
dimension (harmonic, melodic, or rhythmic), allowing the listener to register the change as an
uplift. The order is: **groove first (kick), then harmony (pad root, then chords), then melody
(lead), then rhythm density (clap, hihat, syncopated kick), then timbre complexity (FM)**.

The FM stage at bars 96–108 is placed late deliberately: spectral complexity added too early
competes with melodic clarity. Added last (before the rhythmic peak), it reads as "the sound
opening up fully" rather than "the sound getting busy".

---

## 5. Filter Arc as Emotional Energy

SA's synths use an `rlpf` (resonant low-pass filter). The slider position `x` (range 0.0–1.0) maps
to cutoff frequency in Hz by the formula:

```
cutoff_hz = (x * 12) ** 4
```

**[SA confirmed]** This formula is nonlinear: small changes at low slider values produce small Hz
changes; the same slider delta at high values produces large Hz changes. This matches perceptual
logarithmic scaling of pitch.

### Confirmed Slider → Frequency Map

| Slider `x` | Computation                  | Cutoff (Hz) | Emotional State |
|------------|------------------------------|-------------|-----------------|
| 0.35       | (0.35 × 12)^4 = 4.200^4      | **311 Hz**  | Dark, muffled. Only fundamental and first partial pass. Supersaw sounds like a sine wave with slight harmonic texture. Deliberate pullback / drop-down moments. |
| 0.45       | (0.45 × 12)^4 = 5.400^4      | **850 Hz**  | Opening, warm. Low-mids present. Pad sounds full but not bright. Early build sections. |
| 0.60       | (0.60 × 12)^4 = 7.200^4      | **2,687 Hz**| Bright, energetic. Harmonics up to the 13th partial of a 200 Hz root pass. Mid-build peak energy. |
| 0.877      | (0.877 × 12)^4 = 10.524^4    | **12,267 Hz**| Fully open, euphoric. All audible harmonics pass. Maximum brightness. Climax moments. **[SA confirmed as peak slider value]** |

Precise Python constants:
```python
FILTER_DARK     = 0.35   # 311 Hz
FILTER_WARM     = 0.45   # 850 Hz
FILTER_BRIGHT   = 0.60   # 2687 Hz
FILTER_OPEN     = 0.877  # 12267 Hz
```

### Physical Mechanism

A low-pass filter removes all frequency content above its cutoff frequency. A supersaw oscillator
is harmonically rich (many partials at integer multiples of the fundamental). When the cutoff is at
311 Hz:

- A root note of G2 (98 Hz) passes its fundamental and partials at 196, 294 Hz only — three partials.
  The sound is almost pure sine.
- At 2,687 Hz: partials up to the 27th harmonic of G2 pass. The sound has the characteristic
  buzzing, dense supersaw texture.
- At 12,267 Hz: the filter is effectively open for all audio-range content.

The filter arc — from a low opening value (0.35–0.45) rising to the peak (0.877) — is the **primary
mechanism of emotional build in trance**. It does not require note changes, tempo changes, or new
voices: the same supersaw chord progression sounds completely different at filter 0.35 versus 0.877.
This is why SA's filter automation is the single most important parameter to get right.

---

## 6. Trancegate Polyrhythm

SA uses `trancegate(1.5, 45, 1)`. **[SA confirmed]**

Parameters:
- `1.5` — gate cycles per bar (the rate multiplier relative to the 4/4 bar)
- `45` — gate angle in degrees, controlling envelope shape
- `1` — gate depth (full amplitude modulation)

### Polyrhythmic Analysis

In 4/4 at 140 BPM:
- One bar = 4 beats = 60/140 × 4 = **1.714 seconds**
- The trancegate runs at 1.5 cycles per bar = **3 cycles per 2 bars**

This is a **3:2 polyrhythm**: the gate completes 3 full open-close cycles for every 2 bars of 4/4
kick. The pattern does not align with the bar line every bar — it only resolves (gate cycle downbeat
= bar downbeat) every **2 bars (3.43 seconds)**. This 2-bar non-resolution creates a sense of
continuous forward propulsion: the listener's ear anticipates alignment but it only arrives every
2 bars, producing a subtle urge to keep listening.

If the gate were at 1.0 or 2.0 cycles/bar, it would align on every bar, feeling static and settled.
At 1.5 it never locks cleanly to the kick, creating productive rhythmic ambiguity.

### Envelope Shape: 45° Angle

The cosine gate envelope with angle parameter θ = 45° means the envelope spends equal time rising
and falling. At θ = 45°, the cosine function `cos(θ)` = cos(45°) = 0.707 — the midpoint of the
envelope is at half-amplitude at the half-cycle point. This is a **symmetrical, smooth gate**:

- θ < 45°: shorter open time, more staccato. The gate is closed for more of the cycle.
- θ = 45°: equal open/close time. Smooth "breathing" character.
- θ > 45°: longer open time, more sustained. Resembles tremolo rather than gate.

At 45°, the gate creates an audible rhythmic "breathing" texture on the pad without introducing
harsh amplitude choppping. This preserves the harmonic content of the pad while adding movement.

**Python implementation constants:**
```python
TRANCEGATE_RATE  = 1.5   # cycles per bar — 3:2 polyrhythm against 4/4
TRANCEGATE_ANGLE = 45    # degrees — symmetrical cosine envelope
TRANCEGATE_DEPTH = 1     # full depth amplitude modulation
```

---

*Document version: 1.0. Sources: Switch Angel session OCR analysis (see `reference_switch_angel.md`)
and standard trance production theory. All Hz values computed from confirmed SA formulas.*
