# Pad and Lead: What They Are, How They Sound, How SA Uses Them

This document is the authoritative reference before touching `instruments/pad.py` or
`instruments/lead.py`. Every implementation decision should be checked against this.

Sources: OCR analysis of 5 SA sessions. See `research/analysis/switch_angel_vocabulary.md`
and `switch_angel_song_structure.md`.

---

## 1. The Fundamental Distinction

**Pad** and **lead** are the same synthesis architecture (supersaw → filter → trancegate) placed
in different musical roles.

| Property          | Pad                                | Lead                              |
|-------------------|------------------------------------|-----------------------------------|
| Role              | Harmonic background / atmosphere   | Melodic foreground                |
| Pitch register    | Root chord in the octave played    | One octave above the pad          |
| Number of notes   | 1–3 simultaneous (chord)           | 1–2 simultaneous (melody)         |
| Note duration     | Whole bar (sustained)              | 2–3 beats (sustained phrase)      |
| Filter behaviour  | Opens slowly on chord trigger      | Brighter, faster filter response  |
| Delay             | None                               | Ping-pong delay wet=0.7           |
| Reverb            | Yes — diffuse room                 | Yes — room                        |
| Rhythmic role     | Background pulse (trancegate only) | Between-kick melodic movement     |
| First entry       | Bar 2 — one note, single root      | Bar 8 — one note, one octave up   |
| Full form         | Bar 40 — moving chord progression  | Bar 24 — melodic pattern + delay  |

They are not two different instruments. They are the same instrument heard from two different
distances — the pad is the harmonic floor, the lead floats above it.

---

## 2. The Pad

### 2.1 What the pad does

The pad is the harmonic body of the track. It:

- Establishes the key and chord immediately and holds it for the bar
- Provides sub-bass via its -14 and -21 semitone doublings (before the acid bass enters)
- Creates the "breathing" sensation through the trancegate amplitude modulation
- Makes the kick feel louder by ducking on every kick hit (sidechain)
- Evolves from static root → moving chord progression mid-session

The pad is NOT a melody instrument. It never plays a fast sequence of notes. It holds chords.

### 2.2 What the pad sounds like

**Bars 2–39 (root stage):** A single note played at three octave levels simultaneously — the root
itself, the root -14 semitones (roughly one octave + a perfect fifth below), and the root -21
semitones (roughly 1.75 octaves below). The supersaw detune (0.6 = 60 cents spread across 5
voices) gives each note a slow, wide chorus character. The trancegate makes the whole thing pulse
in and out smoothly at 1.5× the bar rate — one breath every ~1.14 seconds. There is reverb; the
sound feels spatially large. The filter starts partially open (~slider 0.45–0.50 = 850–1100 Hz)
and gradually opens over the session arc.

If you were to describe it in plain words: a large, slowly breathing chord that fills the room. It
has audible movement (the trancegate) but not rhythmic complexity.

**Bars 40+ (chord stage):** The same texture, but the root note changes every few bars according to
the progression (C → D → Eb → F in G minor). SA adds `.seg 16` at this stage, which retriggers the
filter envelope every 16th note — each 16th beat gets a brief filter brightness pulse, adding
rhythmic texture to what was a smooth swell. The -21 semitone doubling also appears here for
extra low-end density.

### 2.3 SA's exact synthesis chain

```
supersaw(voices=5, detune=0.6)   →
  .add("-14", "-21")              →  sub-bass doublings, 3 octave levels per chord note
  .lpenv(2)                       →  filter swell: opens ~2 units on chord trigger, decays slowly
  .rlpf(slider, ~0.5–0.877)       →  LP filter, cutoff controlled live throughout session
  .trancegate(1.5, 45, 1)         →  amplitude gate: 1.5 cycles/bar, cosine shape, full depth
  .seg(16)                        →  [bar 40+] retrigger lpenv every 16th note
  .room(~0.7)                     →  diffuse reverb tail
  .duck("3:4:5").duckattack(.16)  →  sidechain: pad ducks on kick, 160ms recovery
  .duckdepth(.6)                  →  amplitude reduced by 60% on kick hit
  .pg(0.5)                        →  output gain = 0.5
```

### 2.4 What lpenv(2) actually means

`lpenv(2)` in Strudel: the LP filter opens 2 octaves above its rest position on each note trigger,
then decays back. The decay time is slow — on the order of the note duration (whole bar or
half-bar). This means:

- **At the start of a chord**: filter snaps open to ~4× the resting cutoff frequency
- **During the chord**: filter slowly decays back toward resting cutoff
- **At the next chord trigger**: filter snaps open again

The result is a gentle, sustained brightness on each chord — not a percussive "wah" but a slow
bloom. This is why the pad sounds lush and warm, not nasal.

**Critically:** the filter rests at the slider value, not at zero. At slider=0.5 (~1100 Hz) the pad
is already audibly bright at rest; the lpenv pushes it toward 4400 Hz momentarily. At slider=0.877
(~12,267 Hz, full open) the pad is at maximum brightness even at rest and the lpenv has no
audible effect.

### 2.5 What the trancegate actually does

`trancegate(1.5, 45, 1)`:
- **Speed 1.5**: the gate runs 1.5 cycles per bar. One gate cycle = 1/1.5 bar ≈ 1.14 seconds.
- **Angle 45**: the gate envelope is a raised cosine — smooth rise and fall, equal duration.
- **Depth 1**: the gate goes all the way to zero amplitude at its trough.

This is NOT a binary on/off. The gate opens and closes in a smooth sine-like arc. When the pad is
at trough, it is genuinely silent. When it is at peak, it is at full amplitude. The movement between
silence and full sounds like natural breathing, not clicking.

At 1.5 cycles/bar, the gate creates a 3:2 polyrhythm against the 4/4 kick. The gate and kick fall
in sync only every 2 bars, which prevents the gate from sounding like a simple rhythm and makes the
pad feel alive and slightly out of phase with the downbeats.

### 2.6 The sub-bass doublings

SA's `.add("-14, -21")` adds two extra synthesiser voices per chord note:

- **-14 semitones**: one octave + a minor seventh below (approximately). At root C (MIDI 60): C3 → Bb1 (MIDI 46). This voice fills the low-mid register.
- **-21 semitones**: one octave + a perfect fifth + a major third below (approximately). At root C: C3 → F#0 (MIDI 39). This is sub-bass territory.

These are not bass notes in the traditional sense — they are the same chord note transposed down,
keeping the harmonic relationship. The effect is that the pad sounds enormous even when the bass
line is absent (bars 2–6). This is the primary source of low-end energy in the early session.

At root G (MIDI 55, which is G3 in MIDI numbering): the doublings land at MIDI 41 (F2) and MIDI 34
(Bb1). Both are below the standard bass guitar range, reinforcing the sub-bass floor.

### 2.7 Filter arc across the session

The filter cutoff slider is moved live throughout. Documented progression from `GWXCCBsOMSg`:

| Time           | Bar (approx) | Slider   | Hz        | Character |
|----------------|--------------|----------|-----------|-----------|
| Session opens  | 0–20         | 0.45–0.5 | 850–1100  | Warm, partial |
| Mid build      | 20–60        | 0.5–0.55 | 1100–1550 | Opening |
| Pre-climax     | 60–80        | 0.418    | 665       | Deliberate pullback / darker moment |
| Re-opening     | 80–96        | 0.46–0.6 | 850–2687  | Rising toward climax |
| Climax         | 96+          | 0.877    | 12,267    | Fully open |

The pullback at ~0.418 (665 Hz) is intentional — a timbral contrast moment before the final
opening. It makes the subsequent full-open feel like a release rather than a continuous fade.

---

## 3. The Lead

### 3.1 What the lead does

The lead is the melodic foreground. It:

- Plays the melody — a specific sequence of notes with silences and movement
- Sits one octave above the pad register so it cuts through the harmonic background
- Uses delay to create space and rhythmic complexity (each note spawns multiple echoes)
- Has more filter brightness than the pad (slider stays at 0.593+ throughout)
- Evolves from static root tone → active melodic phrase over bars 8–32
- Adds FM texture after bar 96 for a more metallic, complex timbre

The lead IS a melody instrument. It plays rhythmic, directional note sequences. It does not hold
chords across the whole bar (the trancegate + delay give it its rhythmic character).

### 3.2 What the lead sounds like

**Bars 8–23 (root stage):** A single note held through the trancegate breathing — same texture as
the pad but one octave higher and with more filter brightness. No distinct rhythm; just the
trancegate pulse. No delay yet. Sounds like a brighter, higher version of the pad — a hint of
melody to come.

**Bars 24–39 (melody stage):** The melodic pattern kicks in. The first 4 sixteenth-notes of each
bar are silent; the lead only plays in the back half of the bar. When it does play, it alternates
between two notes (the bottom two notes of the current chord) with the second note held for an
eighth-note duration (`1@2`). Ping-pong delay at wet=0.7 fills the silences with echoes. The
combined effect: a sparse, syncopated melody that sounds busier than it is because of the delay
feedback. Heard in isolation it is just 6–7 note events per bar; heard in the mix the delay makes
it feel like a continuous melodic stream.

**Bars 48+ (voicing stage):** The entire melody shifts up or down by different intervals each bar
(`.add "<5 4 0 <0 2>>"`). Bar-to-bar the melody moves: +5 semitones one bar, +4 the next, no shift
the bar after. This creates harmonic variety without changing the note pattern.

**Bars 96+ (FM stage):** Sine FM at depth 0.5 adds inharmonic sidebands, making the lead sound
more complex and slightly metallic/bell-like. The filter also opens further.

### 3.3 SA's exact synthesis chain

From `GWXCCBsOMSg` (the clearest session):

```
n "@@2 <-7 [-5 -2]>@3 <0 -3 2 1>@3"
  .add 7                           →  transpose one octave above pad register
  .add "<5 4 0 <0 2>>"             →  [bar 48+] bar-varying voicing shift
  .scale "g:minor"                 →  scale quantization
  .s "supersaw"                    →
  .trancegate(1.5, 45, 1)          →  same gate as pad — shared rhythmic breathing
  .delay(0.7)                      →  ping-pong delay wet=0.7
  .pan(rand)                       →  random left/right panning per note
  .fm(0.5).fmwave("brown")         →  [bar 96+] FM with brown noise modulator
  .rlpf(slider, 0.593–0.828)       →  brighter than pad; stays above 0.593 throughout
  .lpenv(2)                        →  same filter swell as pad
  .pg(0.7)                         →  output gain = 0.7 (above pad's 0.5)
```

From `3fpx7Scysw4` (more complex variant):
```
n "<[0,6] [[0,7] _ _ [0,4]] [2,9] ...>"
  .notearp("< <- - - -> 0 1@2 0 1 0 1>*16")  →  arpeggio selects which chord tone per step
  .acidenv(slider(0.702))          →  acid envelope modulates filter, not amplitude
  .dly(slider(0.438))              →  delay time slider-controlled
  .fm(slider(0)).fmwave('white')   →  FM starts at 0, opened live
  .s("supersaw,white:0:.4")        →  supersaw + white noise blend (extra air)
  .detune(0.3)                     →  tighter detune than pad
  .roomsize(4)                     →  reverb room size
```

### 3.4 The `.add 7` octave shift

SA's `.add 7` in Strudel adds 7 **scale steps** (not 7 semitones) to the note. In a 7-note scale
(G natural minor), 7 scale steps = one octave = 12 semitones.

In MIDI numbers: if the pad root is C3 (MIDI 48), the lead root is C4 (MIDI 60).
If the chord tones are at C3 and G3 (MIDI 48, 55), the lead tones are at C4 and G4 (MIDI 60, 67).

The result: lead lives in the C4–A4 range (262–440 Hz fundamental frequency). Harmonics extend
to 2000–8000 Hz where the ears are most sensitive. This is why the lead is audible above the pad
even at a lower gain (0.7 vs pad's sub-bass doublings filling the low end).

**If the `.add 7` is missing** (i.e. lead notes are at the same octave as the pad), the lead and
pad compete in the same frequency range and the lead sounds muddy, buried, or dronish. This was the
original bug in our generator — centroid at 190–313 Hz instead of 500–700 Hz.

### 3.5 The notearp pattern

```
"< <- - - -> 0 1@2 0 1 0 1>*16"
```

This is a 16-step sequence that fires at 16th-note resolution:

| Step | Value | Duration | Note                                |
|------|-------|----------|-------------------------------------|
| 0    | rest  | 1/16     | silence                             |
| 1    | rest  | 1/16     | silence                             |
| 2    | rest  | 1/16     | silence                             |
| 3    | rest  | 1/16     | silence                             |
| 4    | 0     | 1/16     | chord tone 0 (root of current chord)|
| 5    | 1     | 2/16     | chord tone 1, held for an eighth    |
| 7    | 0     | 1/16     | chord tone 0                        |
| 8    | 1     | 1/16     | chord tone 1                        |
| 9    | 0     | 1/16     | chord tone 0                        |
| 10   | 1     | 1/16     | chord tone 1                        |

Steps 0–3: silence. Steps 4–10: alternating root/fifth with the first fifth held for two steps.
Steps 11–15 are also silence (the `@3` weights expand the held 1 to consume the remaining steps).

The `1@2` hold at step 5 is the key rhythmic feature — it creates a syncopation that displaces the
remaining notes off the 16th-note grid.

Note that **the lead is silent for the first quarter of the bar**. The melody starts at step 4
(beat 2 of a 16th-note bar). This interlocks with the kick at beats 1 and 3 — kick holds the
structural downbeats, lead fills the back half.

### 3.6 Sustained notes, not triggered bursts

The `@@2 <-7 [-5 -2]>@3 <0 -3 2 1>@3` pattern (GWXCCBsOMSg) uses `@3` weights, meaning each note
group is held for roughly 3 beats. In practice the lead note is held for a long duration; the
trancegate and delay shape the perceived rhythm.

The lead is NOT firing a rapid burst of short notes. Each note is a sustained tone shaped by:
1. The trancegate (smooth amplitude breathing at 1.5× bar rate)
2. The delay (multiple echoes panning left/right)
3. The filter (lpenv opens on the note trigger)

Together these three create the impression of movement and rhythm from just two or three note events
per bar. This is the SA signature: minimalist note sequences made complex by effect depth.

### 3.7 Filter brightness

The lead filter NEVER goes below slider=0.593 (2564 Hz). This is SA's confirmed baseline for the
lead in `GWXCCBsOMSg`. The filter can open higher (up to 0.828 = 6200 Hz, or 0.877 = 12267 Hz at
climax), but it never goes to the dark values (0.35–0.45) that the pad uses in its early bars.

The lead is always bright. It sits in the audible melody register and needs to cut through the pad.
Applying the same filter arc as the pad (starting at 0.45) to the lead is wrong — it makes the
lead sound muffled and buried.

### 3.8 Filter arc across the session (lead)

From `3fpx7Scysw4` (most documented):

| Time           | Bar (approx) | Slider   | Hz        | Character |
|----------------|--------------|----------|-----------|-----------|
| Lead enters    | 8–24         | 0.593    | 2,564     | Default — clear, melodic |
| Mid build      | 24–64        | 0.513–0.601 | 1400–2700 | Slight arc variations |
| Deliberate dark| ~60          | 0.319–0.396 | 500–665   | Rare pullback moment |
| Climax opening | 96+          | 0.619–0.696 | 2800–4000 | Opening with FM |
| End            | 112+         | 0.828–0.877 | 6200–12267 | Fully open |

The deliberate pullback to 0.319–0.396 (500–665 Hz) is a single contrast moment. Outside of that
moment, the lead stays in the 2500–4000 Hz range. At climax it opens to 12,267 Hz with FM.

---

## 4. How Pad and Lead Interact

The pad and lead are designed to occupy different frequency spaces:

- Pad: sub-bass (via doublings), low-mid, mid (130–500 Hz fundamentals, 500–2000 Hz harmonics)
- Lead: mid-high, high (262–440 Hz fundamentals, 1000–8000 Hz harmonics)

They use the same trancegate phase (1.5 cycles/bar) so they breathe in synchrony. When both are
present, their synchronized gate creates the characteristic trance "unison pulse" — both voices
rise and fall together while the kick pushes through.

The sidechain on the pad makes the pad duck on kick hits. The lead also sidechains but is at higher
gain (0.7 vs 0.5) so it recovers faster perceptually. In practice the kick transient is the loudest
element in the mix; everything else ducks around it.

The delay on the lead fills the trancegate silences. When the trancegate closes the pad to silence,
the lead's delay echoes continue — the track never goes completely silent even when the trancegate
is at trough. This creates rhythmic continuity even in the "quiet" parts of the gate cycle.

---

## 5. What "Sounds Wrong" Maps To

This is the diagnostic reference: if the pad or lead sounds bad, this table says what to measure.

### Pad problems

| Perceptual symptom            | Root cause                                               | Measurement |
|-------------------------------|----------------------------------------------------------|-------------|
| Pad sounds muffled/too dark   | Filter stuck near base_hz, lpenv not opening properly   | Centroid < 400 Hz in early bars |
| Pad sounds like a drone       | Trancegate not working (amplitude not varying)           | RMS max/min ratio < 2× per 16th |
| Pad sounds thin (no low end)  | -14/-21 voicing doublings missing or too quiet           | Band energy below 200 Hz < 10% |
| Pad sounds too clicky/choppy  | Trancegate using hard gate, not smooth cosine            | Sample-level delta > 0.02 at gate edges |
| Pad sounds washy/no rhythm    | Trancegate too slow or not at 1.5 rate                   | No amplitude variation at 1.5×/bar rate |
| Pad sounds thin after chord   | lpenv decaying too fast (< 0.2s) back to base            | Centroid drops by > 50% in first 0.2s |

### Lead problems

| Perceptual symptom             | Root cause                                              | Measurement |
|--------------------------------|---------------------------------------------------------|-------------|
| Lead sounds buzzy/fly sound    | Multiple notes at identical pitch (notearp returning    | All MIDI notes identical; centroid at   |
|                                | same chord index because chord has only 1 entry)        | fundamental only, no harmonic spread   |
| Lead sounds buried/muffled     | Missing `.add 7` — lead is at pad register, not octave up | Centroid < 400 Hz; peak freq < 200 Hz |
| Lead sounds too muddy          | Filter below 0.593 slider (< 2564 Hz)                   | Centroid < 500 Hz in bars 8–96 |
| Lead sounds too thin/harsh     | Filter too bright without pad sub-bass below it         | Centroid > 3000 Hz with no energy < 200 Hz |
| Lead has no spatial movement   | Delay missing or wet < 0.3                              | No echo repeats in sonogram |
| Lead sounds like a single drone| Melody pattern not generating note variation            | MIDI notes constant across all steps |
| Lead sounds frantic/busy       | Notes fired every 16th step instead of held 2–3 beats   | >8 note events per bar |

---

## 6. Implementation Checklist

Before the pad or lead can sound right, these conditions must hold:

### Pad

- [ ] Filter rests at slider value (not at base_hz of 5% of slider)
- [ ] lpenv opens filter 2–4× above resting cutoff at note trigger, decays slowly (>0.5s)
- [ ] -14 and -21 semitone doublings present and audible (gain ~0.35 and ~0.15 relative to root)
- [ ] Trancegate produces max/min RMS ratio > 3× at 1.5 cycles/bar
- [ ] FDN reverb wet > 0.3, room_size 0.5–0.9
- [ ] Sidechain active: pad ducks on kick
- [ ] Spectral centroid bars 8–40: 400–1500 Hz (warm, not muffled)
- [ ] Spectral centroid bars 96+: 1500–4000 Hz (fully open)

### Lead

- [ ] All notes transposed +12 semitones above pad register (`.add 7` = +12 in 7-note scale)
- [ ] Filter baseline slider ≥ 0.593 (≥ 2564 Hz) in all bars 8–96
- [ ] Melody uses at minimum 2 distinct pitches alternating; no single-pitch drone
- [ ] Melody fires 4–8 note events per bar (not 16; not 1)
- [ ] Steps 0–3 of the bar are silent (back-loaded rhythm)
- [ ] Ping-pong delay wet ≥ 0.5
- [ ] Spectral centroid bars 8–40: 500–2000 Hz
- [ ] No amplitude shaping via acidenv applied to the whole buffer — only filter modulation

---

*Document version: 1.0. Written before implementing pad/lead fixes.
Sources: `research/analysis/switch_angel_vocabulary.md`, `switch_angel_song_structure.md`,
and measured synthesis output from `instruments/pad.py` and `instruments/lead.py`.*
