# Switch Angel: Musical Vocabulary and Synthesis Parameters
# Extracted from YouTube live-coding sessions via OCR

Sources:
- `3fpx7Scysw4` — Coding Trance IV (6m, 128 code snapshots)
- `-pDO2RhcGhM` — Coding Trance From Scratch YET AGAIN (8m, 87 snapshots)
- `iu5rnQkfO6M` — Coding Trance From Scratch Again (5m, 39 snapshots)
- `vn9VDbacUgQ` — Coding Trance Official (4m, 15 snapshots)
- `GWXCCBsOMSg` — Coding Trance Full Narrated (6m, 42 snapshots)

---

## 1. Global Settings

```
setCpm(140/4)       — 140 BPM (setCpm uses cycles per minute; /4 = quarter notes)
setScale('g:minor') — G natural minor, always
```

---

## 2. Kick Drum — THE MOST IMPORTANT VOICE

**She does NOT use a synthesised kick.** She uses a sample bank: `s("bd")` or `s("tbd")`.

From `3fpx7Scysw4` (Coding Trance IV):
```javascript
$KICK: s("bd:3!4").dec(.3)
  .duck("3:4:5")
  .duckattack(.16).duckdepth(.6)
  .o(2).bank('tr909')._scope()
```

From `GWXCCBsOMSg` (narrated):
```javascript
$: s "tbd:2!4" .beat "0,4,8,11,14",16 ._scope
```

**Critical:** `.beat("0,4,8,11,14", 16)` — kick fires on steps 0, 4, 8, 11, 14 of a 16-step bar.
- Steps 0, 4, 8, 12 = four-on-the-floor (quarter notes)
- Step 11 and 14 = syncopated kicks BEFORE the 4th beat
- This is NOT simple four-on-the-floor. The extra kicks on 11 and 14 are what give it trance drive.

`!4` = the pattern repeats 4x (held for 4 bars). `tbd` and `bd` = TR909 kick sample.
`tr909` bank = classic TR-909 drum machine samples.
`dec(.3)` = decay time 0.3 — tight punchy kick.
`duck("3:4:5")` = sidechain duck to orbits 3, 4, 5 — pad and lead duck on kick.

**Our generator has been using a synthesised sine-sweep kick. She uses TR-909 samples.**

---

## 3. Clap / Snare

From `GWXCCBsOMSg`:
```javascript
$: s "jcp:2!4" .o 5 .beat "0,4,8,11,14",16
```

`jcp` = clap sample (Jomox? or generic). Same beat pattern as kick.
Also seen: `s("jcp:9, dsd:2:.8")` with `.struct("<- 1>*4")` — backbeat clap.

From `3fpx7Scysw4` (late stage):
```javascript
$CLAP: s("[cpkb], [dsd:2][.0]").struct("<- [1>*4]")
  .o(7).pg(.7).sb(.12, ply(2)).early(.001)
```
`.struct("<- 1>*4")` = clap on beats 2 and 4 only (backbeat). `-` = rest, `1` = hit.

---

## 4. Hi-Hat

From `GWXCCBsOMSg` (final state):
```javascript
$: s "tke" .note "e2" .add "<0 7 12 0>*8"
  // + something like: .rib rand .pan 16 .rib .46?
```

From `3fpx7Scysw4`:
```javascript
$HAT: s("white!16").dec(tri.fast(4).range(0.05,.12)).gain(.5)
  .hpf(1200).transient(.2).pg(.9).pan(.2).swingBy(.08,8).late(.001).o(9)
```

**`white!16`** = white noise every 16th note as hi-hat. Decay modulated by a triangle LFO
`tri.fast(4).range(0.05,.12)` — creates a rolling hi-hat feel with varying decay times.
`hpf(1200)` = high-pass at 1200 Hz (filters out low rumble).
This is how she gets the hi-hat: white noise bursts, 16th-note grid, varying decay.

**We have NO hi-hat. This is a massive missing element.**

---

## 5. Pad Voice (orbit 2)

```javascript
$: n "<3@3 4 5 @3 6>*2".add "-14,-21" .scale "g:minor"
  .s "supersaw"
  .trancegate 1.5,45,1 .o 2
  .seg 16
  .rlpf slider 0.877 .lpenv 2
```

Or in function form:
```javascript
$BASS: n(bline.sub("{i4}")).clip(.8).sc()
  .struct(bstruct)
  .acidenv(slider(0.598))
  .o(3).pg(1.4).lpq(0)
  .detune(.5).o(3).flood(slider(0.293))
  .diode("1:.6")
  .s("supersaw").unison(5).detune(.6)._scope()
```

Key parameters:
- `.add("-14,-21")` — two low voices, 14 and 21 semitones below the chord note
- `.scale("g:minor")` — scale quantization
- `.trancegate(1.5, 45, 1)` — trance gate: speed=1.5, angle=45°, probability=1
- `.seg(16)` — segment/step every 16th note
- `.rlpf(slider, 0.877)` — resonant lowpass at ~0.877 = (0.877×12)^4 ≈ 9,400 Hz
- `.lpenv(2)` — LP envelope with time 2
- `.s("supersaw").unison(5).detune(.6)` — supersaw, 5 unison voices, 0.6 detune

**Note on `trancegate(1.5, 45, 1)`:** This is Strudel's native trancegate function.
Speed 1.5 means the gate cycles at 1.5x the pattern speed. Angle 45 = slope shape.
This is NOT a binary on/off gate — it's a smooth shaped envelope that opens and closes.

---

## 6. Lead Voice (orbit 3)

```javascript
$: n "@@2 <-7 [-5 -2]>@3 <0 -3 2 1>@3".add 7
  .add "<5 4 0 <0 2>>"
  .scale "g:minor"
  .s "supersaw"
  .trancegate 1.5,45,1 .o 3
  .delay .7 .pan rand
  .fm .5 .fmwave "brown"
  .rlpf slider 0.828 .lpenv 2
```

Or as seen in Coding Trance IV:
```javascript
$LEAD: n(
  "<[0,6] [[0,7] _ _ [0,4]] [2,9] [[2,8] _ [0,4] [[2,6] [2,7]]]
   [2,7] [[0,7] _ _ [0,4]] [2,9] [[2,8] _ [0,4] [[2,6] [2,8]]]>".add(0))
  .sc().notearp("< <- - - -> 0 1@2 0 1 0 1>*16")
  .acidenv(slider(0.702).add(tri.div(5).slow(20))).fill().lpd(.2)
  .dly(slider(0.438)).clip(1).delayfeedback(.8)
  .pan(rand)
  .fm(slider(0)).fmwave('white')
  .s("supersaw,white:0:.4").o(5).pg(.7).asym("1:.9").detune(.3)
  .flood(slider(0.344)).unison(1)
  .roomsize(4)
```

Key observations:
- `.notearp("< <- - - -> 0 1@2 0 1 0 1>*16")` — **THIS IS THE ARPEGGIO PATTERN**
  Not a random arp. A specific pattern: `<`, `-`, `-`, `-`, `->`, `0`, `1@2`, `0`, `1`, `0`, `1`
  repeated 16 times. This creates specific rhythmic movement within the lead.
- `.fm(.5).fmwave("brown")` — FM synthesis with brown noise as modulator. Adds warmth/texture.
- `.add("<5 4 0 <0 2>>")` — chord voicing: shifts the note up by 5, 4, 0 semitones across bars
- The lead has a multi-note chord notation: `[0,6]`, `[0,7]`, `[2,9]` = multiple simultaneous notes
- `.delay(.7).pan(rand)` — ping-pong delay with random panning
- `.rlpf(slider, 0.828)` — resonant LP at 0.828 = (0.828×12)^4 ≈ 6,200 Hz
- `.unison(5).detune(.6)` — 5 unison voices, 0.6 detune (60 cents)

---

## 7. Bass Voice (bline pattern)

The bass uses a mini-notation pattern string:
```javascript
const bline = "<[3 5@15] [3@12 0@4] [5 7@15] 7>"
const bstruct = "<
  1 1@3 1@2 1 1@2 1 1@2 1 1@2 1 1 1@3 1@2 1 1@2 1 1@2 1 1 1
  1 1@2 1 1@2 1 1@2 1 1@2 1 1@2 1 1111 1@2 1 1@2 1 1@2 1 1 1@2
>*16"
```

This is a complex rhythmic bass pattern using Strudel's mini-notation:
- `3@15` = note 3 held for 15/16ths of the time slot
- `[3@12 0@4]` = note 3 for 12, then note 0 for 4 (subdivided)
- `bstruct` = rhythm pattern applied via `.struct()` — defines WHERE notes fire

Then:
```javascript
$BASS: n(bline.sub("{i4}")).clip(.8).sc()
  .struct(bstruct)
  .acidenv(slider(0.598))
  .o(3).pg(1.4).lpq(0)
  .detune(.5).o(3).flood(slider(0.293))
  .diode("1:.6")
  .s("supersaw").unison(5).detune(.6)
```

`.sub("{i4}")` — substitutes a note from the scale every 4 steps (chord change).
`.acidenv()` — acid bassline envelope (fast attack, controlled decay/sustain).
`.diode("1:.6")` — diode waveshaper for distortion.
`.flood()` — filter flood (rapid filter sweep).
`.lpq(0)` — filter resonance/Q set to 0.

---

## 8. Pulse/Texture Layer

```javascript
$: s "pulse!16" .dec .1 .fm time .fmh time .o 4
```

White/pulse noise triggered every 16th note, with FM modulated by time.
This creates the evolving textural shimmer in the background.

---

## 9. Glitch Layer (Coding Trance IV only)

```javascript
$GLITCH: s("jglitch:5").scrub(rand.seg(16).rib(35,.5)).dec(.06)
  .hpf(500).o(8)
```

Glitch sample scrubbed randomly, very short decay.

---

## 10. What We're Missing vs What We Have

| Element | Switch Angel | Our Generator | Gap |
|---|---|---|---|
| Kick | TR-909 sample, `.beat("0,4,8,11,14",16)` | Synthesised sine sweep, four-on-floor only | Wrong pattern, wrong sound |
| Hi-hat | `white!16` with tri-LFO decay, hpf(1200) | ABSENT | Completely missing |
| Clap | jcp sample, `.struct("<- 1>*4")` (backbeat 2+4) | ABSENT | Completely missing |
| Pad | supersaw, trancegate, add("-14,-21"), rlpf | supersaw, binary gate, add("-14,-21"), IIR | Trance gate vs binary gate |
| Lead | multi-note chord, notearp pattern, FM brown | 3-voice stack, no notearp, no FM | Notearp pattern missing |
| Bass | complex bline pattern, acidenv, diode, flood | rolling 16ths or silent | Pattern, character wrong |
| Pulse | `pulse!16` FM texture | ABSENT | Missing texture layer |
| Sidechain | `.duck("3:4:5")` on kick | manual sidechain env | Functionally similar |
| Scale | g:minor, `.scale()` quantization | g:minor progression | Similar |

---

## 11. The `trancegate` vs Our Binary Gate

Her `trancegate(1.5, 45, 1)` is fundamentally different from our binary LFSR gate:

- It is a **smooth shaped envelope**, not a square on/off
- Speed 1.5 = the gate runs at 1.5× the pattern speed (faster than one gate per step)
- Angle 45 = the envelope shape is a 45° ramp (linear fade in/out)
- Result: notes pulse in with a smooth attack and fade out smoothly — characteristic trance "breathing"

Our gate: hard 1/0 binary on/off per 16th step, even with cosine smoothing at boundaries.
The difference is perceptible: hers sounds like breathing, ours sounds like switching.

---

## 12. Build Order (from narrated video)

1. Start: kick drum only (`tbd!4`)
2. Add pad (orbit 2): `n "0".add -14 .scale "g:minor" .s "supersaw" .trancegate 1.5,45,1`
3. Add lead (orbit 3): `n "0".add 7 .scale "g:minor" .s "supersaw" .trancegate 1.5,45,1`
4. Add lead melody: change lead note pattern to `"@@2 <-7 [-5 -2]>@3 <0 -3 2 1>@3"`
5. Add `.delay .7 .pan rand` to lead for spatial depth
6. Adjust pad to `.add "-14,-21"` and add `.seg 16`
7. Add clap: `s "jcp:2!4" .o 5 .beat "0,4,8,11,14",16`
8. Add FM to lead: `.fm .5 .fmwave "brown"`
9. Add pulse texture: `s "pulse!16" .dec .1 .fm time .fmh time`

**Key insight:** She starts with kick → pad → lead. No bass voice in the first 3 minutes.
The low end is entirely the pad's -14/-21 voicing from the beginning.

---

## 13. Kick Pattern Detail

`.beat("0,4,8,11,14", 16)` fires on steps (0-indexed in a 16-step bar):
```
Step: 0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15
Kick: X  .  .  .  X  .  .  .  X  .  .  X  .  .  X  .
Beat: 1           2           3        e  4     +
```

Steps 0, 4, 8 = beats 1, 2, 3 (four-on-floor first three).
Step 11 = the "e" of beat 3 (16th before beat 4's backbeat).
Step 14 = the "+" of beat 4 (anticipates the downbeat).
Steps 12 is skipped! (No beat 4 on the downbeat — the anticipation on 11 and 14 replaces it.)

This creates the classic trance "pumping" feel — the kick drives FORWARD into the next bar.
