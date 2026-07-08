# Switch Angel: Song Structure, Progression, and Variation
# Temporal/Structural Analysis — complement to switch_angel_vocabulary.md

Sources analysed:
- `3fpx7Scysw4` — Coding Trance IV (6 min, 128 snapshots) — PRIMARY source, most detail
- `-pDO2RhcGhM` — Coding Trance From Scratch YET AGAIN (8+ min, 87 snapshots)
- `GWXCCBsOMSg` — Coding Trance Full Narrated (6 min, 42 snapshots) — clearest build order
- `iu5rnQkfO6M` — Coding Trance From Scratch Again (5 min, 39 snapshots) — different structure
- `vn9VDbacUgQ` — Coding Trance Official (4 min, 15 snapshots) — OCR too degraded for detail

Note: "vn9VDbacUgQ" snapshots are almost entirely unreadable noise. It is excluded from specific claims below.

---

## Summary

Switch Angel makes a coherent trance song rather than a static loop through four mechanisms:

1. **Staged construction**: voices are added one at a time over the first 3–5 minutes, each addition being a discrete musical event (the listener hears something new arrive).
2. **Continuous parametric drift**: slider values for filter cutoff, FM depth, and delay are moved live throughout the session, creating slow evolution even when the code structure is frozen.
3. **Pattern/note variation**: note strings and `.add()` chord voicings are edited mid-session, shifting the melodic content and harmonic texture across bars.
4. **Texture expansion in the second half**: additional voices (bass, glitch, hi-hat, VOX sample) are added progressively, thickening the arrangement from ~3 voices to 6–8.

There is NO explicit breakdown-drop-buildup structure in the observed videos. She does not strip things back to just kick and rebuild. The arc is strictly additive: sparse → full.

---

## A. Build Order — Consistent Across Videos

### Canonical build sequence (synthesised from all videos)

**Stage 0 — Pre-roll (t=0:00)**
- Global declarations: `setCpm(140/4)`, `setScale('g:minor')`, any constant definitions (`bline`, `bstruct` in `3fpx7Scysw4`).
- In `3fpx7Scysw4` the full skeleton (BASS + LEAD declared but with silent/muted voices `_$`) is loaded from the start. The leading underscore `_$` prefix silences a voice in Strudel.

**Stage 1 — Kick first (consistent across all videos)**

In `GWXCCBsOMSg` (t=0:50):
```javascript
$: s 'tbd:2!4' ._scope
```
Kick is always the first audible sound. In `3fpx7Scysw4` the kick appears at t=0:39 (line 29–33 first visible).

In `iu5rnQkfO6M` (t=0:36): The session opens differently — a lead/bass voice is being drafted first (`$: n "<0 4 0 [9] 7>*16"`) before the kick is added. This suggests she sometimes sketches melody first, then brings kick in — but even here the kick appears by t=1:00.

**Stage 2 — Pad (orbit 2) added second**

In `GWXCCBsOMSg` (t=0:50, same snapshot as kick):
```javascript
$: n "0".add -14 .scale "g:minor"
   .s "supersaw" .trancegate 1.5,45,1 .o 2
   .rlpf slider .5 .lpenv 2
```
Note: pad starts as a SINGLE note (`n "0"`) — not the full chord movement pattern yet. Just the root with `.add -14` for the low octave doublings.

**Stage 3 — Lead (orbit 3) added third**

In `GWXCCBsOMSg` (t=1:01):
```javascript
$: n "0".add 7 .scale "g:minor"
   .s "supersaw" .trancegate 1.5,45,1 .o 3
   .rlpf slider .5 .lpenv 2
```
Lead also starts on a single note (n "0" with `.add 7` = one octave up). No melody yet.

**Stage 4 — Lead melody is added (still no separate bass voice)**

In `GWXCCBsOMSg` (t=1:36):
```javascript
$: n "@@2 <-7 [-5 -2]>@3 <0 -3 2 1>@3".add 7 .scale "g:minor"
   .s "supersaw" .trancegate 1.5,45,1 .o 3
   .delay .7 .pan rand
   .rlpf slider .593 .lpenv 2
```
The lead note pattern becomes the melodic pattern. `.delay .7 .pan rand` is added at the same time, giving spatial depth immediately.

**Stage 5 — Pad chord movement is added**

In `GWXCCBsOMSg` (t=2:05):
```javascript
$: n "<3@3 4 5 @3 6>*2".add "-14,-21" .scale "g:minor"
   .trancegate 1.5,45,1 .o 2 .seg 16
   .rlpf slider .5 .lpenv 2
```
Pad gains: (a) a moving chord pattern `<3@3 4 5 @3 6>*2`, (b) a second low octave doubly `.add "-14,-21"`, (c) `.seg 16` for rhythmic stepping.

**Stage 6 — `.add` chord voicing added to lead**

In `GWXCCBsOMSg` (t=2:44):
```javascript
$: n "@@2 <-7 [-5 -2]>@3 <0 -3 2 1>@3".add 7
   .add "<5 [4] 0 <0 2>>"
   .scale "g:minor"
   .s "supersaw" .trancegate 1.5,45,1 .o 3
   .delay .7 .pan rand
   .rlpf slider .593 .lpenv 2
```
The extra `.add "<5 [4] 0 <0 2>>"` shifts the lead melody by different intervals each bar, creating harmonic motion in the lead without changing the note string.

**Stage 7 — Clap added**

In `GWXCCBsOMSg` (t=4:31):
```javascript
$: s "jcp:2!4" .o 5
```
Then refined to:
```javascript
$: s "jcp:2!4" .o 5 .beat "0,4,8,11,14",16
```
Clap gets the same beat pattern as the kick — not a simple backbeat at this point.

**Stage 8 — FM added to lead**

In `GWXCCBsOMSg` (t=4:31 → t=4:48):
```javascript
.fm .5 .fmwave "brown"
```
Added to the lead chain. Immediately changes the timbre — more metallic/buzzy.

**Stage 9 — Pulse texture layer**

In `GWXCCBsOMSg` (t=5:26):
```javascript
$: s "pulse!16" .dec .1 .fm time .fmh time .o 4
```
White/pulse noise every 16th note, FM-modulated by time. This layer shimmers in the background.

**Stage 10 — Hi-hat / scrub texture**

In `GWXCCBsOMSg` (t=5:53):
```javascript
$: s "tke" .note "e2" .add "<0 7 12 0>*8"
   .rib rand .pan 16 .rib .46...
```
(OCR partial, but hi-hat/texture voice appears late.)

**Stage 11 — Beat pattern corrected on kick**

In `GWXCCBsOMSg` (t=5:20):
```javascript
$: s "tbd:2!4" .beat "0,4,8,11,14",16 ._scope
```
The kick's `.beat` pattern is added mid-session, switching from simple `!4` repetition to the syncopated trance pattern.

### Coding Trance IV (`3fpx7Scysw4`) — different starting point

This session starts with a pre-written skeleton where BASS and LEAD are already defined at t=0:00 but with `_$` prefix (silenced). The build order proceeds by activating/unhiding voices rather than writing them from scratch.

By t=0:24 the lead is visible and active. By t=0:39 the kick appears (`$KICK: s("bd:3!4")`). The pre-muted voices become active over the first ~4 minutes. This session also adds:

- `$TOP: s("top:2").ifit(1).scrub("0").o(6).pg(.6)` — a percussion top sample (appears t=0:47)
- `$GLITCH: s("jglitch:5").scrub(rand.seg(16).rib(35,.5)).dec(.06).hpf(500).o(8)` — glitch layer (t=0:58)
- `$HAT: s("white!16").dec(tri.fast(4).range(0.05,.12)).gain(.5).hpf(1200)...` — hi-hat (t=0:59)
- `$BASSLAYER: n(bline.sub("3")...)` — a second bass layer (t=2:04)

### Coding Trance YET AGAIN (`-pDO2RhcGhM`) — melodic-first variant

This session uses a completely different starting architecture:
- Starts with a pre-defined `notes` constant (a complex note matrix, 8 rows, each row 4-6 notes)
- First voice is `$MELODY: s("sawtooth").acidenv(slider(.44)).nsc(notes,3).o(4).rib(0,2)._scope().room(.7)` — a sawtooth with acid envelope using a note-sequence chromatic-approach (`.nsc(notes,3)` = note-scale lookup)
- Second voice is `$BASS: s("supersaw").nsc("<0 2 -2 -1 -4 -2 5 -1>/2",2).o(3).acidenv(slider(.44))` — bass added at t=1:09
- A `$VOX: s("v_utada:1")...` vocal sample is added at t=2:31
- The **kick is added last** (or very late) rather than first — at t=3:58 `$: s("rbd").clip(1).o(2).duck("3:4:5").duckdepth(.7)`

This is the outlier session where the melodic idea comes before the rhythmic foundation.

### Coding Trance Again (`iu5rnQkfO6M`) — two-lead structure

This session also opens with a single-note lead pattern (`.acidenv`-based sawtooth), builds toward a two-layer approach with one voice at `.trans(-12)` and one at `.trans(-24)`, before the kick enters. The starting pattern at t=0:36:
```javascript
$: n "<0 4 0 [9] 7>*16" .scale "g:minor" .trans -12
   .o(3) .s "sawtooth" .acidenv slider 0.546
   ._pianoroll
$: s "tbd:2!4"
```

---

## B. Variation Techniques

### B.1 Note pattern evolution — PAD

The pad note pattern follows a consistent evolution:

1. **Single root**: `n "0"` — just the root, held
2. **Moving chord**: `n "<3@3 4 5 @3 6>*2"` — four chords cycling through degrees 3, 4, 5, 6 with duration weighting
3. Pad note pattern appears **stable once set** — she does not change the chord progression during a session. The movement comes from the `.rlpf slider` cutoff being adjusted live.

Across videos the chord degrees used: 3, 4, 5, 6 (sometimes variations like `<3@3 4 [5] @3 6>*2` where `[5]` brackets indicate OCR uncertainty about the actual value).

### B.2 Note pattern evolution — LEAD

The lead has the richest pattern evolution:

1. **Stage 1**: `n "0".add 7` — single root
2. **Stage 2**: `n "@@2 <-7 [-5 -2]>@3 <0 -3 2 1>@3"` — basic melodic pattern. Breaking this down:
   - `@@2` = rest for 2 beats (silence)
   - `<-7 [-5 -2]>@3` = alternating between note -7 and the pair [-5,-2] for 3 beats
   - `<0 -3 2 1>@3` = four-step sequence cycling for 3 beats
3. **Stage 3**: `.add "<5 [4] 0 <0 2>>"` added — this shifts the pitch by 5, 4, 0 semitones across consecutive bars, and the inner `<0 2>` alternates

In `3fpx7Scysw4` the lead is much more complex from the start (pre-written):
```javascript
"<[0,6] [[0,7] _ _ [0,4]] [2,9] [[2,8] _ [0,4] [[2,6] [2,7]]]
 [2,7] [[0,7] _ _ [0,4]] [2,9] [[2,8] _ [0,4] [[2,6] [2,8]]]>"
```
This is a two-bar chord sequence with multiple simultaneous notes per step (e.g. `[0,6]` = notes 0 and 6 together). The pattern alternates between two similar bars (first ends `[2,7]`, second ends `[2,8]`).

### B.3 Note pattern evolution — BASS (`-pDO2RhcGhM`)

The bass note sequence `"<0 2 -2 -1 -4 -2 5 -1>/2"` is consistent throughout the session but the `.acidenv` slider is moved live (0.44 → 0.616 → 0.634 → 0.698). No changes to the bass note string itself are observed across the 87 snapshots. The rhythm `.rib(0,2)` is changed once (→ `.rib(8,8)`) at around t=3:58, which changes the rhythmic density.

In `3fpx7Scysw4` the bass uses the pre-defined `bline` constant which never changes, but `.flood(slider)` and `.acidenv(slider)` values drift.

### B.4 `.add` chord voicing shifts

A recurring technique: adding a second `.add` call whose pattern creates bar-by-bar harmonic variety.

`GWXCCBsOMSg` lead:
- Before: `.add 7` (constant pitch shift)
- After: `.add 7 .add "<5 [4] 0 <0 2>>"` — shifts by 5, 4, 0, then alternating 0/2 semitones across bars

This technique turns a fixed melodic pattern into one that sounds harmonically varied without touching the core note string.

### B.5 `.delay` timing and feedback

The lead's delay is set once and not changed:
```javascript
.delay .7
.delayfeedback .8
```
In `3fpx7Scysw4` the delay value is stored as `slider(0.585)` and can be varied live. Observed range: 0.438–0.773 (the value is moved during the session).

### B.6 `.rlpf` slider — filter cutoff live variation (PRIMARY VARIATION TOOL)

This is her most-used live variation technique. The filter cutoff slider is moved continuously through the entire session on both pad and lead. Documented values:

**Pad filter (`GWXCCBsOMSg`)**:
- t=0:50: slider 0.5
- t=2:44: slider 0.418
- t=3:39: slider 0.462
- t=4:31: slider 0.669
- t=4:48: slider 0.877 (fully open)
- t=6:03: slider 0.877 (stays open)

**Lead filter (`GWXCCBsOMSg`)**:
- Stays near 0.593 for most of the session
- t=5:53+: slider 0.88 (fully open)

**Lead filter (`3fpx7Scysw4`)**:
- t=0:00: 0.254 (very dark)
- t=0:39: 0.455
- t=1:24: 0.513
- t=1:33: 0.396 (pulled back)
- t=2:29: 0.457
- t=3:18: 0.601
- t=3:47: 0.319 (pulled back again — this is a texture change)
- t=4:00: 0.619
- t=4:15+: 0.696

The pattern: gradual opening with occasional deliberate pullbacks. The pullbacks at t=1:33 (0.396) and t=3:47 (0.319) create brief darker moments before opening again.

### B.7 `.fm` depth slider — FM density live variation

In `3fpx7Scysw4`, lead FM starts at 0 and is opened live:
- t=0:00: `fm(slider(0))` — no FM
- t=4:00: `fm(slider(0.606))` — moderate FM (more metallic texture)
- fm stays around 0.606 for the rest of the session

In `GWXCCBsOMSg`, FM is added as `.fm .5 .fmwave "brown"` at t=4:31 (a fixed value, not slider-controlled in that session).

In `iu5rnQkfO6M`, FM is added at t=4:07 as `.fm(.5).fmwave('white')` and immediately accompanied by `.pan(rand)`.

### B.8 `.acidenv` slider — envelope brightness

Used heavily in `iu5rnQkfO6M` and `-pDO2RhcGhM` where the acid bass/melody envelope is slider-controlled:
- `iu5rnQkfO6M`: lead acidenv goes 0.546 → 0.763 → 0.851 → 0.869 → 1.0 (fully open by t=2:55)
- `-pDO2RhcGhM` melody: starts 0.44, reaches 0.53 by t=1:58, stays 0.579 then 0.707 by t=4:29, final push to 0.889 at t=7:38

The acidenv slider is the "brightness/energy" control. Opening it is the primary way she builds energy in the acid-style sessions.

### B.9 Rhythm structure changes

**`.beat` pattern addition**: In `GWXCCBsOMSg`, the kick starts as `s "tbd:2!4"` (four-on-floor simple) and at t=5:20 gains `.beat "0,4,8,11,14",16`. This is a mid-session rhythmic upgrade.

**`.struct` vs `.beat`**: The clap and kick both use `.beat` while other voices use `.struct`. In `3fpx7Scysw4` the clap uses `.struct("<- 1>*4")` (backbeat only), which is a simpler pattern.

**`.rib(0,2)` vs `.rib(8,8)`**: In `-pDO2RhcGhM`, the bass switches from `.rib(0,2)` (sparse) to `.rib(8,8)` (denser) at around t=3:58. This makes the bass busier and is a structural shift.

### B.10 `.trancegate` — applied/removed

In `GWXCCBsOMSg` at t=2:08, the pad briefly loses `.trancegate` (the code line is absent in one snapshot) but it reappears. This may be an edit in progress, not an intentional removal. The trancegate is considered a core element that stays on both pad and lead throughout.

In `3fpx7Scysw4` at t=3:18, the lead's `.roomsize` value (for reverb) is visible as `roomsize(4)` throughout. This stays constant.

---

## C. Breakdown Structure

**There is no observed traditional breakdown (strip-back → rebuild) in any of the 5 sessions.** Switch Angel does not mute voices or switch to a stripped version. Instead:

1. Voices once added stay in place.
2. The filter cutoff (`.rlpf slider`) is the closest equivalent: pulling it down to ~0.3–0.4 darkens the sound significantly (creates a momentary "darker" section), then opening it again creates a sense of release.
3. In `3fpx7Scysw4` at t=3:47, the lead filter drops to 0.319 and the delay shortens to 0.438 — this is the closest thing to a "dark moment" / low-energy section observed.
4. The `_$` (underscore prefix = muted) convention is visible only in the pre-loaded skeleton at the start of `3fpx7Scysw4`. She may use this to preview a voice before activating it, but does not re-mute a voice after it has been activated.

**In `-pDO2RhcGhM`**, a brief thinning happens at t=2:37–2:39 where `.tgate` is removed from the bass (snapshot shows no tgate line), then it returns at t=2:44. This is likely an edit, not a structural breakdown.

---

## D. Buildup Techniques

Without a formal breakdown to build back from, her "buildup" is the entire first half of the session:

1. **Layering**: each new voice entry is itself a mini-buildup moment
2. **Filter sweep**: gradually opening the `.rlpf slider` toward 0.877–0.88 (fully open) in the final minutes creates a sense of crescendo
3. **FM introduction**: adding `.fm` to the lead (or opening the FM slider from 0) thickens the texture and adds high-frequency content
4. **Acidenv opening**: in acid-style sessions, pushing acidenv slider toward 1.0 brightens the envelope attack
5. **Delay build**: in `3fpx7Scysw4`, delay time slider goes from 0.585 (short) to 0.773 (longer tail) during the second half — more wash, more space

In `-pDO2RhcGhM`, the final third of the session (t=6:25 onwards) sees the melody's `.add` parameter change from `"<0 7 0 7>*8"` to `"<0 7 0 7>*8"` then adding octave transpositions — the notes move into higher registers for energy.

Specific: at t=6:25 in `-pDO2RhcGhM`:
```javascript
.nsc(notes.add("<0 7 0 7>*8"), 3)
```
Then at t=7:46:
```javascript
.nsc(notes.add("<0 7 0 7 13>*16"), 3)
```
Adding `13` (an octave + a major 6th) to the rotation shifts the melody into a brighter register.

---

## E. Drop — Not Observed

No drop in the EDM sense is observed in any session. The sessions are studio live-coding explorations, not set reconstructions. She builds to a full dense arrangement and the session simply ends.

The closest analogue: in `-pDO2RhcGhM` at t=3:58, a kick (`s("rbd")`) and top loop (`s("top:1")`) are added simultaneously — this is the first rhythmic foundation arriving into what was a mostly melodic texture. It functions as a "drop" of sorts in that session, making the beat suddenly prominent.

---

## F. Texture Evolution — Full Session Arc

### Session arc in `GWXCCBsOMSg` (clearest example, 6 min):

| Time | Active voices | Approximate density |
|------|--------------|-------------------|
| 0:00 | setup only | silent |
| 0:50 | kick + pad (single note) | minimal — just pulse |
| 1:01 | kick + pad + lead (single note) | 3-voice open pad |
| 1:36 | kick + pad + lead (with melody + delay) | melodic, spatial |
| 2:05 | kick + pad (moving chords + seg 16) + lead | pad now animated |
| 2:44 | all above + lead chord voicing shift | harmonic complexity added |
| 4:31 | all above + clap + FM on lead | rhythmic + timbral shift |
| 4:48 | all above + pad filter open (0.877) | bright and full |
| 5:26 | all above + pulse texture | shimmer layer |
| 5:53 | all above + hi-hat scrub | rhythmic top end |
| 6:03+ | full arrangement | maximum density, sustained |

### Session arc in `3fpx7Scysw4` (pre-loaded skeleton, 6 min):

| Time | Event |
|------|-------|
| 0:00 | Pre-loaded code: BASS + LEAD declared but silenced (`_$`) |
| 0:24 | Lead active, filter at 0.254 (very dark) |
| 0:39 | KICK added, TOP cymbal added |
| 0:48 | CLAP + GLITCH added |
| 0:59 | HAT added |
| 1:24–2:04 | Lead filter rises slowly from ~0.455 to 0.513 |
| 1:33 | Lead filter pulled back to 0.396 (darker moment) |
| 2:04 | BASSLAYER added (second bass voice) |
| 2:13–3:18 | Filter opens from 0.396 back to 0.601 |
| 3:18 | Lead delay extends to 1.0 (maximum washout) |
| 3:47 | Lead filter drops to 0.319, delay shortens to 0.438 (significant darkening) |
| 4:00 | FM slider opened to 0.606 (FM enters the mix) |
| 4:00 | Lead filter back to 0.619, rising |
| 4:15 | The full code comment `@title 136 Foundation` visible — she's happy with this version |
| 4:30+ | Audience chat visible in snapshots — she's in presentation mode |

### Session arc in `-pDO2RhcGhM` (melodic-first, 8+ min):

| Time | Event |
|------|-------|
| 0:00 | Notes constant defined (8-row chord matrix) |
| 0:54 | MELODY: sawtooth with acidenv, nsc lookup |
| 1:09 | BASS added: supersaw nsc pattern |
| 1:58 | Bass tgate added |
| 2:31 | VOX sample added: `s("v_utada:1")` |
| 3:58 | Kick + top loop added — rhythmic foundation arrives |
| 4:09 | Kick + VOX scrub pattern stable |
| 4:29 | Melody acidenv reaches 0.707 (bright) |
| 6:25 | Melody note transposition added: `.add "<0 7 0 7>*8"` |
| 7:38 | Melody acidenv pushed to 0.889 (maximum brightness) |
| 7:46 | Note transposition changed to `"<0 7 0 7 13>*16"` — octave+ register |
| 8:00 | Break sample added: `s("break:0").ifit(2).scrub("0")` |

---

## G. Specific Pattern Variations — Before/After Code Changes

### G.1 Lead note pattern expansion (`GWXCCBsOMSg`)

**t=1:01** — initial lead:
```javascript
n "0".add 7 .scale "g:minor"
```

**t=1:36** — melody added:
```javascript
n "@@2 <-7 [-5 -2]>@3 <0 -3 2 1>@3".add 7 .scale "g:minor"
.delay .7 .pan rand
```
Change: single note → full melodic pattern + delay + panning all in one edit.

### G.2 Pad chord sequence upgrade (`GWXCCBsOMSg`)

**t=1:56** — pad with single root:
```javascript
n "0".add -14 .scale "g:minor"
.trancegate 1.5,45,1 .o 2
.rlpf slider 0.593 .lpenv 2
```

**t=2:05** — pad with full chord movement:
```javascript
n "<3@3 4 5 @3 6>*2".add "-14,-21" .scale "g:minor"
.trancegate 1.5,45,1 .o 2 .seg 16
.rlpf slider 0.5 .lpenv 2
```
Changes: (a) note pattern from `"0"` to `"<3@3 4 5 @3 6>*2"`, (b) add gains second octave `-21`, (c) `.seg 16` added.

### G.3 Lead chord voicing addition (`GWXCCBsOMSg`)

**t=1:56** — lead without extra voicing:
```javascript
n "@@2 <-7 [-5 -2]>@3 <0 -3 2 1>@3".add 7 .scale "g:minor"
```

**t=2:44** — lead with chord voicing:
```javascript
n "@@2 <-7 [-5 -2]>@3 <0 -3 2 1>@3".add 7
.add "<5 [4] 0 <0 2>>"
.scale "g:minor"
```

### G.4 FM addition (`GWXCCBsOMSg` and `iu5rnQkfO6M`)

**`GWXCCBsOMSg` t=4:31**:
- Before: lead has no FM
- After: `.fm .5 .fmwave "brown"` appended to lead chain

**`iu5rnQkfO6M` t=4:07**:
- Before: `.s("sawtooth").acidenv(slider(0.869)).delay(.4)...`
- After: `.fm(.5).fmwave('white')` inserted — note fmwave is `"white"` not `"brown"` in this session

### G.5 Kick beat pattern upgrade (`GWXCCBsOMSg`)

**t=0:50 – t=5:20**: kick is `s "tbd:2!4"` (simple 4-on-floor)

**t=5:20**: kick becomes `s "tbd:2!4" .beat "0,4,8,11,14",16` — syncopated trance kick

The beat pattern is retrofitted onto the kick partway through the session, not set from the start.

### G.6 Lead delay opening (`3fpx7Scysw4`)

**t=0:12–1:24**: lead delay slider stays near 0.585
**t=1:24**: delay slider = 0.773 (longer tail, more wash)
**t=3:18**: delay slider = 1.0 (maximum — completely washed out)
**t=3:47**: delay slider drops back to 0.438 (tight, short)
**t=4:00–4:30**: stays at 0.438 (tight)

The delay was opened all the way then deliberately reduced — a large variation that changes the character significantly.

### G.7 Notearp pattern in lead (`3fpx7Scysw4`)

The lead uses `.notearp("< <- - - -> 0 1@2 0 1 0 1>*16")`. This string is **consistent across all 128 snapshots of that session** — it does not change. This is a locked-in part of the sound identity for that session.

### G.8 Bass variation in `-pDO2RhcGhM`

**t=1:09**: bass pattern `"<0 2 -2 -1 -4 -2 5 -1>/2"` — `/2` means 2 octaves down
**Unchanged through t=7:58**: the bass note sequence is never modified

But at t=3:58 the `.rib(0,2)` becomes `.rib(8,8)`:
- `.rib(0,2)` = probabilistic muting, sparsely
- `.rib(8,8)` = denser, busier rhythm

And at t=7:55 the note string briefly changes to `"<0 2 -2 -2 -4 -2 5 -1>/2"` — the 4th note changes from -1 to -2 (a semitone lower). This is a very small melodic variation in a long session, suggesting she does occasionally edit the bass pattern but rarely.

---

## H. Mistakes and Corrections

### H.1 Double-pad in `GWXCCBsOMSg`

At t=0:50, there are TWO pad voice definitions visible:
```javascript
$: n "0".add -14 .scale "g:minor"
   .s "supersaw" .trancegate 1.5,45,1 .o 2
   .rlpf slider .5 .lpenv 2
$: n "0".add -14 .scale "g:minor"
   .s "supersaw" .trancegate 1.5,45,1 .o 2
   .rlpf slider amg .5 .lpenv 2
```
By t=1:07 only one pad line remains. The duplicate was deleted.

### H.2 Trancegate removal in `GWXCCBsOMSg`

At t=2:08, the pad's `.trancegate` line disappears briefly. The snapshot at t=2:08 shows:
```javascript
$: n "<3@3 4 5 @3 6>*2".add "-14,-21" .scale "g:minor"
   .rlpf slider 0.418 .lpenv 2
```
(No `.trancegate`). By t=2:48 the trancegate is back. This was likely an accidental deletion and recovery.

### H.3 VOX scrub pattern in `-pDO2RhcGhM`

At t=2:45, a scrub pattern is added to the VOX:
```javascript
.scrub("<4 - - <- [4]>>" .div(16)) .dly(.9)
```
At t=3:34, the `.rib(0,2)` is re-added to the bass after having been removed. This back-and-forth on `.rib` suggests she was experimenting with bass density.

At t=4:09–4:11, the VOX scrub pattern is commented out (`// .scrub(...)`) — she temporarily disables it, then it reappears. The scrub on/off is used as a textural switch.

### H.4 Lead comment in `3fpx7Scysw4`

At t=0:24 an extra line appears at the bottom of the lead block:
```javascript
.s("Sawtooth,white:[]:.4").o(5).pg(.7).asym("1:.9").detune(.3)
```
This is a different synthesis layer (sawtooth + white noise blend). It appears in multiple snapshots from t=0:24 onwards, suggesting it is intentional — a secondary oscillator blended into the lead sound. The `.asym("1:.9")` adds asymmetric waveshaping.

---

## I. Consistency Across Videos

### Elements present in ALL readable sessions:

| Element | Present in all 4 sessions | Notes |
|---------|--------------------------|-------|
| `setCpm(140/4)` | Yes | Always 140 BPM |
| `setScale('g:minor')` | Yes | Always G natural minor |
| Kick sample (tbd or bd) | Yes | Always TR-909 sample |
| Supersaw pad | Yes | `o 2` or orbit 2-3 |
| Lead melodic voice | Yes | Though architecture varies |
| `.trancegate 1.5,45,1` or `.tgate(.6,45,1)` | Yes (4/4) | Varies between 1.5 and 0.6 speed |
| `.rlpf slider` filter | Yes | Core dynamic control |
| `.delay` / `.dly` on lead | Yes | Always some delay on lead |
| g:minor scale | Yes | Never changes key |

Note: `.tgate(.6,45,1)` (speed 0.6) in `-pDO2RhcGhM` and `iu5rnQkfO6M` vs `.trancegate(1.5,45,1)` in `GWXCCBsOMSg` and `3fpx7Scysw4`. Slower tgate = slower breathing. The angle (45°) is always identical.

### Elements present in MOST but not all sessions:

| Element | Sessions | Notes |
|---------|---------|-------|
| Hi-hat `white!16` | 3fpx7Scysw4, GWXCCBsOMSg | Not in iu5rnQkfO6M, pDO2RhcGhM |
| Clap `jcp` | 3fpx7Scysw4, GWXCCBsOMSg | Not in iu5rnQkfO6M, pDO2RhcGhM |
| `.notearp()` pattern | 3fpx7Scysw4 only | Not seen in other sessions |
| `$GLITCH` layer | 3fpx7Scysw4 only | Unique to IV |
| VOX sample (`v_utada`) | pDO2RhcGhM only | Unique to YET AGAIN |
| Pulse texture | GWXCCBsOMSg, 3fpx7Scysw4 | |
| `.acidenv` (acid bass) | pDO2RhcGhM, iu5rnQkfO6M | Not in GWXCCBsOMSg, 3fpx7Scysw4 |
| Complex `bline`/`bstruct` | 3fpx7Scysw4 only | Pre-written bass pattern |

### Session-specific experiments:

- `3fpx7Scysw4`: most complex — pre-loaded skeleton, 8 named voices (`$KICK`, `$LEAD`, `$BASS`, `$BASSLAYER`, `$CLAP`, `$HAT`, `$GLITCH`, `$TOP`), `.notearp()` arpeggiator on lead, `.diode()` waveshaper on bass
- `-pDO2RhcGhM`: vocal sample, `nsc()` note-scale lookup, `.room(.7)` on melody, `break` sample late in session
- `iu5rnQkfO6M`: two-voice lead architecture (high/low sawtooth), `.detune(rand)` on the low voice, never adds drums until very late
- `GWXCCBsOMSg`: cleanest example of the "standard" session, best for implementation reference

---

## Practical Implications for Generator

### Timing of voice additions (in cycles, at 140 BPM = 35 cycles/minute):

- Kick: immediately or within first ~10 cycles
- Pad (single root): same time as kick or within 5 cycles
- Lead (single root): 5–15 cycles after pad
- Lead melody expansion: 20–40 cycles after lead appears
- Pad chord movement: ~40–60 cycles in
- Clap: ~80–100 cycles in
- FM on lead: ~100–120 cycles in
- Pulse/texture: ~110–130 cycles in
- Hi-hat: ~110–130 cycles in

### Filter cutoff arc (`.rlpf slider`):

```
0:00–1:00 → start at 0.4–0.5 (moderately dark)
1:00–2:30 → drift upward to 0.5–0.6
2:30–3:30 → hold or slight pullback (0.45–0.55)
3:30–5:00 → open further 0.6–0.75
5:00–end  → fully open 0.85–0.90
```
Occasional sharp pullbacks (drop to 0.3–0.4) at any point for texture contrast.

### FM depth arc (`.fm slider`):

```
0:00–3:00 → zero (no FM)
3:00–4:00 → open to 0.3–0.5 (subtle FM)
4:00–end  → stabilise at 0.5–0.65 (moderate FM, present but not harsh)
```

### Delay time arc (`.dly slider`):

```
0:00–1:30 → medium-short (0.4–0.6)
1:30–3:00 → open toward long (0.6–0.8)
3:00–3:30 → possible maximum (0.8–1.0) for "wash" section
3:30–end  → moderate (0.4–0.5) for clarity
```
This arc — open then close — is the main non-additive variation tool for the lead.

### AcidEnv arc (for acid-style sessions):

```
0:00–2:00 → moderate (0.44–0.60)
2:00–5:00 → open steadily (0.60–0.75)
5:00–end  → maximum brightness (0.85–0.90)
```
