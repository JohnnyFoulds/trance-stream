# Perceptual Evaluation Framework: Synthesis Style Matching

**Version**: 1.0  
**Date**: 2026-07-11  
**Scope**: Single-listener comparative evaluation of a synthesised output against a style
reference, for the purpose of diagnosing synthesis gaps and prioritising fixes. Designed for
30-second clips in the trance genre.

**Theoretical basis**: Multi-dimensional human evaluation approach used in synthesis matching
literature (Yee-King, 2011; Engel et al., 2020). Simplified from MUSHRA (ITU-R BS.1534-3)
for single-listener, single-session diagnostic use — MUSHRA's multi-listener, multi-stimulus
design is not required here because the goal is gap diagnosis, not statistical significance.

---

## 1. Shared Vocabulary

Precise shared vocabulary is required to ensure that gap descriptions written in one session
are interpretable in future sessions and by collaborators. Each term has three columns:
the term itself, what it means, and an unambiguous physical identifier to eliminate
interpretation drift.

| Term | Means | How to identify it unambiguously |
|---|---|---|
| **Transient** | The sharp initial attack of a percussive sound | The first 5–20 ms of a drum hit — the click before the tone. If you cut it off, the drum loses its knock. |
| **Tail** | The decay after a sound ends | The part you still hear after the note or hit stops. On a kick: the low-frequency ring. On reverb: the fading echo after the dry signal is gone. |
| **Dry** | No reverb applied | Sounds like it is in the same room as you, close and immediate. A dry kick sounds like a punch. Reference: a clap in open air. |
| **Wet** | Heavy reverb applied | Sounds distant and diffuse. The tail is longer than the source event. Individual hits blur into each other. Reference: a clap in a large tiled bathroom. |
| **Pump** | The mix volume drops on every kick hit then recovers | Caused by sidechain compression. The pad gets briefly quieter exactly when the kick hits, then rises back. The rhythm breathes in and out on every beat. Distinct from gate: pump is a volume envelope, not an on/off switch. |
| **Gate** | A sound switches between on and off in a rhythmic pattern | The pad has rhythmic silences chopped into it at 16th-note resolution. Distinct from pump: gate is a structural binary on/off; pump is a continuous volume envelope riding the kick. |
| **Sweep** | A filter cutoff moving up or down over time | Brightness changes over the duration of a note or bar. A low-pass sweep rising sounds like the sound opening up. Falling sounds like it closing down. Identifiable by ear as a continuous timbral change, not a static tone. |
| **Body** | The sustained mid-frequency content between the attack and the tail | After the transient, before the reverb tail — the meat of the sound. A kick with no body sounds like a click followed by sub. A pad with strong body fills the 200–2000 Hz range. |
| **Sub** | Frequency content below 80 Hz | Felt through the chest or a subwoofer more than heard through speakers. If you high-pass filter at 80 Hz and the sound loses weight, it had sub. On speakers without sub response, this dimension requires headphones or a subwoofer to evaluate accurately. |
| **Spread** | Stereo width — how far left and right a sound sits | Listen on headphones. A spread sound has different content in each ear. A mono sound is centred identically in both ears. A supersaw pad should sound wide; a kick should sound centred. |
| **Glue** | Mix elements sound like they belong in the same acoustic space | The opposite: instruments sound like they were recorded in different rooms. Glue comes from shared reverb, consistent dynamics, and complementary frequency ranges. Test: does removing one element make the rest sound unbalanced? |
| **Drive** | The forward rhythmic energy of the track | Does it make you want to move? Does it feel like it is pushing forward? Drive is lost when: the kick sounds weak, the sidechain pump is absent, or the tempo feels unsettled. |
| **Brightness** | The balance of high-frequency content | A bright sound has strong energy above 4 kHz — presence, air, shimmer. A dull sound has most energy below 2 kHz. Reference: the difference between an open hi-hat and a muted one. |
| **Density** | How much spectral and temporal content is present simultaneously | A dense mix has many things happening across the frequency range at once. A sparse mix has gaps — in time and in frequency. Reference: a full chord vs a single note. |
| **Character** | The distinctive timbral fingerprint of a specific instrument | What makes that instrument sound like itself and not a generic substitute. The TB-303 acid squeal is character. The JP-8000 supersaw chorus is character. Test: if you swapped it for a generic version of the same instrument type, would you immediately notice? |

---

## 2. Evaluation Dimensions

Six dimensions cover the perceptual space of a trance synthesis match. Each maps to one or
more synthesiser subsystems so that a gap rating translates directly into a code target.

| # | Dimension | What to listen for | Relevant subsystems |
|---|---|---|---|
| 1 | **Rhythm & Drive** | Kick weight and transient, hi-hat character, pump presence and depth | `synth/drums.py`, `synth/effects.py` Sidechain |
| 2 | **Pad character** | Gate rhythm, sweep shape and depth, body and tail, spread | `instruments/pad.py`, `synth/effects.py` SimpleFDN |
| 3 | **Lead character** | Brightness, filter sweep range, presence and character in the mix | `instruments/smooth_lead.py` |
| 4 | **Mix space** | Wet/dry balance, foreground/background separation, glue | `hey_angel_cover.py` master bus, reverb routing |
| 5 | **Sub & Bass** | Weight, tightness, how it sits under the kick and pad | `instruments/bass.py`, `synth/drums.py` kick sub |
| 6 | **Overall style fit** | Does it sound like SA? Would you identify it as her style within 15 seconds? | All — this is the integration score |

---

## 3. Rating Scale

| Score | Meaning |
|---|---|
| 5 | Indistinguishable from the reference |
| 4 | Close — minor differences, same character |
| 3 | Recognisable intent but clearly different in one specific identifiable way |
| 2 | Wrong in a fundamental way — same genre, wrong feel |
| 1 | Does not resemble the reference at all |

Scores 1 and 5 should be rare. Score 3 is the most informative — it requires naming the
specific difference, which is the diagnostic value of this framework.

---

## 4. Evaluation Procedure

### 4.1 Setup

- Use headphones, not laptop speakers. Sub evaluation requires over-ear headphones or a
  subwoofer.
- Listen to the reference first, full clip, uninterrupted.
- Listen to the generated output second, full clip, uninterrupted.
- Do not rate during playback. Listen completely, then score.

### 4.2 Per-session output format

For each of the six dimensions, write:

```
[Dimension]: [score]/5 — [one sentence describing the primary gap]
```

Then write:

```
Primary fix: [the single most important thing to address, in one sentence]
```

Example:
```
Rhythm & Drive: 3/5 — kick has no transient punch; body and tail are present but the
attack click is missing, making every beat land soft instead of sharp.

Pad character: 2/5 — no audible gate rhythm; pad is a continuous tone with no rhythmic
chop, where the reference has clear 16th-note gating.

Lead character: 3/5 — brightness is close but the sweep range is narrow; filter barely
opens compared to the reference's wide acid sweep.

Mix space: 2/5 — everything sits in the same wet reverberant space; reference has dry
kick and bass clearly in the foreground with wet pad behind.

Sub & Bass: 3/5 — sub weight is present but bass attack is soft; reference has a tighter
low-mid punch on each bass note.

Overall style fit: 2/5 — recognisable as electronic music but not identifiable as SA
within 15 seconds; the mix space and pad gating gaps are the primary reason.

Primary fix: remove master bus reverb so kick and bass are dry, restoring the
foreground/background separation that defines the genre.
```

### 4.3 Before/after sessions

When evaluating the effect of a specific fix, run the procedure twice:

1. **Before** — rate the output before the fix. Record scores and primary gap descriptions.
2. Apply the fix.
3. **After** — rate the output again. For each dimension, note whether the score changed and
   by how much.

The before/after delta is the evidence that the fix addressed the right problem. A fix that
improves the "Primary fix" dimension without moving other scores is a clean, targeted
improvement. A fix that moves multiple dimensions unexpectedly requires investigation.

---

## 5. Session log format

Each evaluation session should be recorded in `research/analysis/experiment_log.md` with:

```
### EVAL-NNN — [date] — [what changed since last eval]

Before/after: [before session ID if applicable]
Render: [file path or parameters used]

Rhythm & Drive:    [score]/5 — [gap description]
Pad character:     [score]/5 — [gap description]
Lead character:    [score]/5 — [gap description]
Mix space:         [score]/5 — [gap description]
Sub & Bass:        [score]/5 — [gap description]
Overall style fit: [score]/5 — [gap description]

Primary fix: [one sentence]
```

---

## 6. Relationship to objective metrics

This framework is complementary to, not a replacement for, the Tier-1 objective metrics
(CLAP, centroid_ratio, band_energy_cosine, mfcc_cosine). The relationship is:

- **Objective metrics** drive the optimiser and provide reproducible, automatable gates.
- **This framework** diagnoses what the objective metrics cannot see — perceptual character,
  mix space, drive, and style fit.

When objective metrics pass but perceptual evaluation scores are low (≤ 3 on Overall style
fit), the metrics are not capturing the relevant gap. When perceptual scores are high (≥ 4)
but objective metrics fail, the metrics may be too conservative for this reference/generator
pair — consider whether the bar should be adjusted.

The acceptance criterion for the SA phase is BR-1: *"a listener familiar with trance
identifies the output as Switch Angel's style within 15 seconds, without knowing it is
procedurally generated"* (`docs/feature-spec.md`). This corresponds to a score of 4 or 5
on the Overall style fit dimension.

---

## 7. References

Engel, J., Hantrakul, L., Gu, C., & Roberts, A. (2020). DDSP: Differentiable digital
signal processing. In *International Conference on Learning Representations (ICLR 2020)*.
https://arxiv.org/abs/2001.04643

International Telecommunication Union. (2015). *Method for the subjective assessment of
intermediate quality level of audio systems* (ITU-R BS.1534-3). ITU.
https://www.itu.int/rec/R-REC-BS.1534

Yee-King, M. (2011). *Automatic sound synthesiser programming: Techniques and applications*
[Doctoral dissertation, University of Sussex]. (Supervisor: Mark d'Inverno.)
