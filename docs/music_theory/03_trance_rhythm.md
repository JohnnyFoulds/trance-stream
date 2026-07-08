# Trance Rhythm: Theory Reference for `song/theory.py`

This document is the authoritative source for every rhythm-related constant in `song/theory.py`. Every
Python value that encodes kick steps, hihat parameters, sidechain coefficients, or gate timing cites a
section below. Nothing in this document is abstract: every claim maps directly to a constant or formula.

The style target throughout is **Switch Angel (SA)**: a procedural trance producer whose session
recordings were OCR-analysed to extract synthesis parameters. Where a value is confirmed from those
recordings it is marked **[SA confirmed]**.

Reference tempo throughout: **140 BPM**. All timing values are derived from this tempo unless stated
otherwise.

---

## Tempo Derivation

All timing constants flow from one root value:

```
BPM          = 140
BAR_S        = 60 / BPM * 4   = 1.714 s
BEAT_S       = 60 / BPM       = 0.429 s
SIXTEENTH_S  = BEAT_S / 4     = 0.107 s   (≈107 ms)
```

A 16th-note grid divides the bar into 16 steps numbered 0–15. Each step is 107 ms. This grid is the
coordinate system for every kick, clap, and gate constant below.

```python
# song/theory.py
BPM         = 140
BAR_S       = 60 / BPM * 4      # 1.714 s
BEAT_S      = 60 / BPM           # 0.429 s
SIXTEENTH_S = BEAT_S / 4         # 0.107 s
```

---

## 1. Kick Pattern Analysis

### 1.1 Grid placement

SA's confirmed kick pattern is `beat("0,4,8,11,14", 16)`: five hits on a 16-step bar. **[SA confirmed]**

| Step | Beat position | Time (ms) | Label |
|------|--------------|-----------|-------|
| 0    | beat 1 downbeat | 0 ms | downbeat |
| 4    | beat 2 downbeat | 428 ms | downbeat |
| 8    | beat 3 downbeat | 856 ms | downbeat |
| 11   | "e" of beat 3 + 3 sixteenths | 1 177 ms | anticipation hit |
| 14   | "+" of beat 4 | 1 498 ms | anticipation hit |

Bar boundaries for reference: beat 4 downbeat = step 12 = 1 284 ms; bar end = step 16 = 1 714 ms.

Steps 0, 4, 8 form the standard three-on-floor skeleton (beats 1, 2, 3). The fourth downbeat (step 12)
is intentionally absent — it is replaced by two anticipation hits at steps 11 and 14.

### 1.2 Anticipation timing in milliseconds

**Step 11 vs beat 4 (step 12):**

```
step_11 = 11 * SIXTEENTH_S = 11 * 107 = 1177 ms
step_12 = 12 * SIXTEENTH_S = 12 * 107 = 1284 ms
gap     = 1284 - 1177 = 107 ms  (one 16th note early)
```

Step 11 fires exactly one 16th note (107 ms) before the expected beat 4 downbeat. The expected hit
does not arrive; instead a hit has already passed. This is the core mechanism of **kick anticipation**.

**Step 14 vs bar end:**

```
step_14   = 14 * 107 = 1498 ms
bar_end   = 16 * 107 = 1714 ms
gap_to_end = 1714 - 1498 = 216 ms  (two 16ths before bar end)
```

Step 14 fires 216 ms before the bar boundary, placing kinetic energy in the "pickup" position that
leads into the next bar's downbeat.

### 1.3 Psychology of kick anticipation

The phenomenon is sometimes called "pre-beat kick" in electronic music production literature. The
mechanism:

1. The listener's motor system entrains to the beat after hearing beats 1, 2, 3 (steps 0, 4, 8).
2. The body anticipates a hit on beat 4 (step 12).
3. The kick fires at step 11 — 107 ms early. The expected beat 4 hit never comes.
4. The nervous system, already committed to moving toward the expected beat, redirects that energy
   forward into the next beat cycle.

This is why the kick "pumps" the room: the listener is continuously leaning forward, energy perpetually
transferred ahead rather than landing squarely on the downbeat. Step 14 reinforces this by placing a
second hit in the bar's final pickup, so the bar ends with momentum rather than rest.

### 1.4 Density analysis

```
four_on_floor_hits = 4  hits/bar
sa_syncopated_hits = 5  hits/bar   # steps 0,4,8,11,14
density_increase   = (5 - 4) / 4 = 0.25  (25% denser)
```

The two extra hits (steps 11 and 14) are concentrated in the last five 16ths of the bar (steps 11–15).
This back-loading concentrates kinetic energy toward the bar end, producing the sensation of "falling
forward" into the next downbeat.

```python
# song/theory.py
KICK_STEPS       = [0, 4, 8, 11, 14]   # 16th-note grid, 16-step bar [SA confirmed]
KICK_GRID_SIZE   = 16
KICK_DENSITY     = len(KICK_STEPS) / 4  # hits per beat = 1.25; 25% above four-on-floor
KICK_ANTICIPATION_STEPS = [11, 14]      # pre-beat hits that create forward momentum
```

---

## 2. Hihat Groove

### 2.1 Base parameters

SA's confirmed hihat: `sound("hh").decay(.08).sustain(0).gain(.5)`. **[SA confirmed]**

```
HH_DECAY_BASE    = 0.08  s  (80 ms)
HH_SUSTAIN       = 0.0
HH_GAIN          = 0.5
```

`sustain(0)` means the envelope has no sustain phase: it is purely attack → decay. The hihat sound is
entirely defined by its decay length. A longer decay = more "open" hi-hat; shorter = more "closed" snap.

### 2.2 LFO as accent generator

SA applies `.tri.fast(4).range(0.05, 0.12)` to modulate the decay. **[SA confirmed]**

```
LFO waveform : triangle
LFO speed    : fast(4) = 4 cycles per bar
LFO range    : 0.05 s – 0.12 s  (50 ms – 120 ms)
```

**LFO rate calculation at 140 BPM:**

```
bar_rate    = BPM / 60 / 4 = 140 / 60 / 4 = 0.583 Hz  (one bar per cycle)
lfo_rate_hz = 4 * bar_rate = 4 * 0.583    = 2.33 Hz
lfo_period  = 1 / lfo_rate_hz             = 429 ms
```

One LFO period = 429 ms. One 16th note = 107 ms. Therefore:

```
lfo_period / sixteenth = 429 / 107 ≈ 4.0  (exactly 4 sixteenth notes per LFO cycle)
```

The LFO completes exactly one cycle per group of four 16th notes. In a 16-step bar, this gives four
complete LFO cycles, each aligned with one beat. The triangle wave means:

- **Beat downbeat (top of triangle):** decay at maximum → 0.12 s (120 ms) → open, sustained hi-hat
- **Beat midpoint (bottom of triangle):** decay at minimum → 0.05 s (50 ms) → closed, snappy hi-hat
- **Off-beat 16ths:** interpolated values between 50 ms and 120 ms

The perceived effect: hi-hats on the main beat feel slightly more open and present; hi-hats between
beats feel tighter and more percussive. This creates groove without altering grid position — the accent
pattern is encoded in timbre, not timing.

```python
# song/theory.py
HH_DECAY_BASE    = 0.08   # s — base decay [SA confirmed]
HH_DECAY_MIN     = 0.05   # s — closed position (LFO trough) [SA confirmed]
HH_DECAY_MAX     = 0.12   # s — open position (LFO peak) [SA confirmed]
HH_SUSTAIN       = 0.0
HH_GAIN          = 0.5    # [SA confirmed]
HH_LFO_WAVEFORM  = "tri"
HH_LFO_CYCLES_PER_BAR = 4          # fast(4) in Strudel [SA confirmed]
HH_LFO_RATE_HZ   = HH_LFO_CYCLES_PER_BAR * (BPM / 60 / 4)  # 2.33 Hz at 140 BPM
HH_LFO_PERIOD_S  = 1 / HH_LFO_RATE_HZ                       # 0.429 s = 4 sixteenths
```

---

## 3. Clap Patterns

### 3.1 Backbeat placement

The standard trance clap uses `struct("~ 1 ~ 1")`: hits only on beats 2 and 4 (steps 4 and 12 on the
16-step grid). SA's confirmed gain: `.pg(.7)`. **[SA confirmed]**

```
CLAP_BACKBEAT_STEPS = [4, 12]   # beats 2 and 4
CLAP_GAIN           = 0.7
```

**Why backbeat placement is psychologically powerful:**

In 4/4 metre, beats 1 and 3 are the "strong" metrical positions — the downbeats. Beats 2 and 4 are
metrically weak. Placing a loud, sharp sound (clap/snare) on the weak beats creates a syncopated accent
that the body perceives as a "lift" against the kick's downbeat. This is the fundamental groove tension
in virtually all dance music descended from Afroamerican popular styles.

The clap on beat 4 specifically marks the end of the bar and signals the downbeat of the next bar.
A listener hears: *kick (1) → clap (2) → kick (3) → clap+anticipation kicks (4) → downbeat (1)*.
The clap at step 12 and the anticipation kicks at steps 11 and 14 form a three-event cadence at the
bar's end: clap lands, then two quick kicks propel the listener into bar 1.

### 3.2 Syncopated variant

In some sessions SA uses `beat("0,4,8,11,14", 16)` for the clap as well — identical to the kick
pattern. **[SA confirmed]** This overlays clap accents on every kick hit, collapsing the kick/clap
distinction. The groove becomes more aggressive and forward-driving because the backbeat contrast is
removed. Use sparingly: without the beat-2/4 contrast the groove feels denser but less swinging.

```python
# song/theory.py
CLAP_BACKBEAT_STEPS   = [4, 12]       # beats 2 and 4 — standard trance clap
CLAP_SYNCOPATED_STEPS = KICK_STEPS    # [0,4,8,11,14] — aggressive variant [SA confirmed]
CLAP_GAIN             = 0.7           # [SA confirmed]
```

---

## 4. Trancegate Polyrhythm

### 4.1 Parameters

SA's confirmed gate: `trancegate(1.5, 45, 1)` on pad. **[SA confirmed]**

```
GATE_SPEED  = 1.5   # cycles per bar
GATE_ANGLE  = 45    # degrees — shape parameter
GATE_PARAM3 = 1     # depth/intensity
```

### 4.2 Mathematical derivation of the 3/2 polyrhythm

Speed 1.5 cycles per bar means the gate runs at 3/2 the rate of the bar metre:

```
gate_cycles_per_bar = 3/2
gate_period_bars    = 1 / (3/2) = 2/3 bar
```

The gate completes 3 cycles in the time the bar completes 2. This is a **3-against-2 polyrhythm**
(hemiola).

**Alignment interval (LCM):**

For the gate to return to phase with the bar, find the least common multiple of the gate period
(2/3 bar) and the bar (1 bar):

```
LCM(2/3, 1) = LCM of 2 and 1 / GCD of 3 and 1 = 2/1 = 2 bars
```

The gate and bar re-align every **2 bars**. Over a 4-bar phrase the alignment occurs at bars 1, 3, and
5 (the downbeats of the phrase boundary). Every bar presents the gate in a different phase relative to
the kick pattern, which is why each bar "feels different" despite using the same gate parameters.

**Gate period in real time:**

```
gate_period_s = BAR_S / GATE_SPEED = 1.714 / 1.5 = 1.143 s per gate cycle
attack_s      = gate_period_s / 2  = 0.571 s   (rise)
decay_s       = gate_period_s / 2  = 0.571 s   (fall)
```

Each gate envelope takes 571 ms to open and 571 ms to close. This is approximately 5.3 sixteenth notes
per half-cycle — a leisurely, "breathing" rate well above audible modulation but clearly felt as a
rhythmic pulsation.

### 4.3 The 45° cosine shape

The angle parameter selects the cosine curve's shape. At 45° (π/4 radians):

- The cosine function `cos(θ)` at θ = π/4 reaches its zero-crossing (maximum gate open) at the cycle
  midpoint.
- Equal time is spent in the rising and falling phases.
- The envelope is symmetric: the pad fades in over 571 ms, briefly peaks, then fades out over 571 ms.

This gives the pad a "breathing" character: it swells in, dwells momentarily at full volume, then
retreats. Contrast with a sharper angle (e.g. 60°–80°) which would produce a tighter, more abrupt
gate, or 0° which would be a square gate (hard cut).

```python
# song/theory.py
GATE_SPEED           = 1.5    # cycles per bar — 3/2 polyrhythm [SA confirmed]
GATE_ANGLE_DEG       = 45     # cosine shape — symmetric breathing envelope [SA confirmed]
GATE_DEPTH           = 1      # [SA confirmed]
GATE_PERIOD_S        = BAR_S / GATE_SPEED    # 1.143 s
GATE_HALF_CYCLE_S    = GATE_PERIOD_S / 2     # 0.571 s  (attack = decay)
GATE_REALIGN_BARS    = 2      # gate re-aligns with bar every 2 bars (LCM of 2/3 and 1)
```

---

## 5. Sidechain Pump Mechanics

### 5.1 Parameters

SA's confirmed sidechain: `.duck("3:4:5").duckattack(.16).duckdepth(.6)`. **[SA confirmed]**

```
SIDECHAIN_DEPTH    = 0.6    # fractional gain reduction
SIDECHAIN_ATTACK_S = 0.16   # s — recovery time constant (160 ms)
```

Note: in Strudel's `.duck()` nomenclature "attack" refers to the envelope's **release/recovery** phase
(how fast the ducked signal returns to full gain after the trigger). This is the inverse of the
synthesis envelope convention.

### 5.2 Exponential recovery model

The duck envelope follows an exponential recovery. At kick onset (t = 0) the gain is reduced to its
minimum. It recovers asymptotically toward unity:

```
gain(t) = 1 - SIDECHAIN_DEPTH + SIDECHAIN_DEPTH × (1 - e^(−t / SIDECHAIN_ATTACK_S))
        = 0.4 + 0.6 × (1 - e^(−t / 0.16))
```

Evaluated at key time points:

| t | Description | Calculation | Gain |
|---|-------------|-------------|------|
| 0 ms | kick onset | 0.4 + 0.6 × (1 − e^0) | **0.400** (maximum duck) |
| 107 ms | 1 sixteenth later | 0.4 + 0.6 × (1 − e^(−0.107/0.16)) | **0.692** (still ducked) |
| 214 ms | 2 sixteenths later | 0.4 + 0.6 × (1 − e^(−0.214/0.16)) | **0.836** |
| 320 ms | 3 sixteenths (step 11→14 gap) | 0.4 + 0.6 × (1 − e^(−0.32/0.16)) | **0.919** (mostly recovered) |
| 428 ms | 4 sixteenths (beat spacing) | 0.4 + 0.6 × (1 − e^(−0.428/0.16)) | **0.966** (nearly full) |

At t = 0.16 s (one time constant), the gain has recovered to `0.4 + 0.6 × 0.632 = 0.779`. At t = 3 ×
0.16 = 0.48 s (≈ 4.5 sixteenths), gain is at `0.4 + 0.6 × 0.950 = 0.970` — essentially full.

### 5.3 What creates the "pump" sensation

The pump arises from the **perceptibility of the recovery curve**, not just the duck depth:

1. On each kick the pad drops sharply to 40% gain.
2. Over 160 ms the pad swells back toward full volume.
3. The next kick hits before the pad has fully recovered (for the close steps 11 and 14, only 321 ms
   apart: pad reaches ~0.92 gain before the next duck).
4. The listener perceives the pad as "breathing" in synchrony with the kick — a swell and collapse
   cycle at kick rate.

The 160 ms time constant is critical: too fast (< 80 ms) and the pump disappears (recovery is
imperceptible); too slow (> 300 ms) and the pad sounds suppressed rather than pumping. At 160 ms the
recovery is audible but incomplete between the close kicks (steps 11 and 14), which means those kicks
feel heavier because the pad is still slightly compressed when they land.

```python
# song/theory.py
SIDECHAIN_DEPTH    = 0.6     # gain reduction fraction [SA confirmed]
SIDECHAIN_ATTACK_S = 0.16    # s — exponential recovery time constant [SA confirmed]
SIDECHAIN_MIN_GAIN = 1.0 - SIDECHAIN_DEPTH   # 0.4 — gain floor at kick onset
# gain(t) = SIDECHAIN_MIN_GAIN + SIDECHAIN_DEPTH * (1 - exp(-t / SIDECHAIN_ATTACK_S))
```

---

## 6. `seg 16` Retriggering

### 6.1 What `seg 16` does

In Strudel, `seg N` (or `segment N`) divides each cycle into N equal segments, retriggering the note
event at the start of each segment. For `seg 16` on a pad at 140 BPM:

```
retrigger_rate  = 16 per bar
retrigger_period = BAR_S / 16 = 1.714 / 16 = 0.107 s = one sixteenth note
```

Without `seg 16` the pad sustains one continuous note per chord change. The attack envelope fires once
per chord event, then the note decays or sustains to the next chord.

With `seg 16` the pad re-triggers its attack envelope 16 times per bar — once on every 16th note.
Each retrigger produces a fresh amplitude onset at 107 ms intervals.

### 6.2 Rhythmic difference

| Mode | Attacks per bar | Texture |
|------|----------------|---------|
| No seg | 1 (per chord change) | drone / sustain pad |
| seg 16 | 16 | rhythmic stab element |

The 16 attacks per bar align with the kick grid. Kick hits at steps 0, 4, 8, 11, 14 each coincide with
a pad retrigger. The result: every kick hit is reinforced by a simultaneous pad attack. Between kicks,
pad retriggerers at the non-kick steps (1, 2, 3, 5, 6, 7, 9, 10, 12, 13, 15) create a continuous
rhythmic texture that fills the space between kick hits.

The sidechain (section 5) then ducks this rhythmic texture on each kick: the pad attacks at step 0 and
immediately ducks to 40% gain, recovers over 160 ms, and the next pad retrigger at step 1 (107 ms
later) lands while the duck is still at ~0.69. This means the off-beat pad stabs are softer than the
downbeat stabs — a natural dynamic gradient created by the interaction of seg 16 and sidechain.

```python
# song/theory.py
PAD_SEG_DIVISIONS = 16   # retrigger pad on every 16th note
```

---

## 7. Groove Summary

All rhythm elements are designed to interact with each other. The combined mechanism:

### 7.1 The pump cycle

Each 16th-note grid step triggers one or more of these events:

1. **Kick** (steps 0, 4, 8, 11, 14) — initiates sidechain duck; provides the body-pulse reference beat
2. **Pad retrigger** (all 16 steps via `seg 16`) — fresh pad attack every 107 ms
3. **Sidechain recovery** — pad swells back toward full gain over 160 ms after each kick
4. **Hihat** (all 16 steps, uniform grid) — decay modulated 50–120 ms by 2.33 Hz triangle LFO
5. **Clap** (steps 4, 12) — backbeat accent marking beats 2 and 4
6. **Trancegate** (continuous, period 1.143 s) — slow 3/2 polyrhythmic swell over the pad

### 7.2 Energy profile across the bar

```
Step: 0    1    2    3    4    5    6    7    8    9   10   11   12   13   14   15
      K              K              K         K    K         K              K
      C    .    .    .    C    .    .    .    .    .    .    .    C    .    .    .
      (K = kick, C = clap on beats 2+4, k = anticipation kick)
```

Energy is highest at step 0 (kick + clap-free downbeat) and at the cluster of steps 11–14 (two kicks
plus the approaching bar-end). The region of steps 1–3 and 5–7 is the "release zone" where the
sidechain fully recovers, the gate is at a random phase, and the hihat provides the only rhythmic
pulse. This release zone lets the listener "breathe" before the next kick.

### 7.3 Why these specific constants work together

- `SIXTEENTH_S = 107 ms` is the fundamental time unit. All other values are multiples or fractions of it.
- `SIDECHAIN_ATTACK_S = 0.16 s = 1.5 × SIXTEENTH_S`. The recovery outlasts one 16th note, which is
  why consecutive kicks (steps 11 → 14, gap = 3 × 107 = 321 ms) feel "heavier" — the pad never fully
  recovers.
- `HH_LFO_PERIOD_S = 4 × SIXTEENTH_S`. The hihat accent LFO is phase-locked to the beat grid.
- `GATE_PERIOD_S = 1.143 s ≈ 10.7 × SIXTEENTH_S`. The gate is intentionally *not* aligned to the
  16th grid — it drifts, creating the perceived complexity.
- `KICK_ANTICIPATION_STEPS = [11, 14]` concentrate energy in the final 5 steps of the bar, ensuring
  the bar ends with forward momentum rather than rest.

The result is a groove that is simultaneously predictable (kick on beats 1, 2, 3; clap on 2, 4) and
surprising (anticipation kicks, drifting gate, LFO-modulated hihat timbre). This predictability-within-
surprise is the core perceptual mechanism of trance: the listener can entrain and move to the beat, but
the groove is rich enough that each bar is slightly different.

```python
# song/theory.py  — complete rhythm constants block
BPM                      = 140
BAR_S                    = 60 / BPM * 4          # 1.714 s
BEAT_S                   = 60 / BPM               # 0.429 s
SIXTEENTH_S              = BEAT_S / 4             # 0.107 s

KICK_STEPS               = [0, 4, 8, 11, 14]     # 16th-grid, 16-step bar [SA confirmed]
KICK_GRID_SIZE           = 16
KICK_ANTICIPATION_STEPS  = [11, 14]

HH_DECAY_BASE            = 0.08                  # s [SA confirmed]
HH_DECAY_MIN             = 0.05                  # s (LFO trough) [SA confirmed]
HH_DECAY_MAX             = 0.12                  # s (LFO peak) [SA confirmed]
HH_SUSTAIN               = 0.0
HH_GAIN                  = 0.5                   # [SA confirmed]
HH_LFO_CYCLES_PER_BAR    = 4                     # [SA confirmed]
HH_LFO_RATE_HZ           = HH_LFO_CYCLES_PER_BAR * (BPM / 60 / 4)  # 2.33 Hz
HH_LFO_PERIOD_S          = 1 / HH_LFO_RATE_HZ                       # 0.429 s

CLAP_BACKBEAT_STEPS      = [4, 12]               # beats 2 and 4
CLAP_SYNCOPATED_STEPS    = KICK_STEPS            # aggressive variant [SA confirmed]
CLAP_GAIN                = 0.7                   # [SA confirmed]

GATE_SPEED               = 1.5                   # cycles/bar — 3:2 polyrhythm [SA confirmed]
GATE_ANGLE_DEG           = 45                    # cosine shape [SA confirmed]
GATE_DEPTH               = 1                     # [SA confirmed]
GATE_PERIOD_S            = BAR_S / GATE_SPEED    # 1.143 s
GATE_HALF_CYCLE_S        = GATE_PERIOD_S / 2     # 0.571 s
GATE_REALIGN_BARS        = 2

SIDECHAIN_DEPTH          = 0.6                   # [SA confirmed]
SIDECHAIN_ATTACK_S       = 0.16                  # s [SA confirmed]
SIDECHAIN_MIN_GAIN       = 1.0 - SIDECHAIN_DEPTH # 0.4

PAD_SEG_DIVISIONS        = 16
```
