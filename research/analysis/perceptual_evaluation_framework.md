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

## 7. Ear Training

Use these samples to build familiarity with the shared vocabulary before conducting a
comparative evaluation. Each term in Section 1 has at least one audio demonstration.
Listen progressively: Group A first (isolated concepts), Group B last (comparative pairs).

All files live in `research/reference_audio/training/`. MP3s are committed to the repo.
To regenerate: `python tools/generate_training_samples.py`

### 8.1 How to use the training samples

1. Listen to the ON sample. Form an impression of what you hear.
2. Listen to the OFF sample. Note what changed — that change is the term.
3. Listen to both again. Confirm you can identify the term in isolation before moving on.
4. For Group B: listen to the Strudel file first (that is what SA's synthesis sounds like),
   then the Python file. Write down the most obvious difference using vocabulary from Section 1.

### 7.2 Group A — Vocabulary demonstrations (Python synthesis, isolated concepts)

Generated by `tools/generate_training_samples.py`. Each pair isolates one term by changing
exactly one thing between the ON and OFF version.

| Files | Term | What to listen for | The tell |
|---|---|---|---|
| [A01_transient_with.mp3](../reference_audio/training/A01_transient_with.mp3) vs [A02_transient_without.mp3](../reference_audio/training/A02_transient_without.mp3) | **transient** | A01 has a sharp click at the start of every kick hit. A02 has the same body and tail but the click is replaced by a 10 ms fade-in. | If you can hear the precise moment the kick starts, the transient is there. If it seems to "swell in", it's gone. |
| [A03_dry_kick.mp3](../reference_audio/training/A03_dry_kick.mp3) vs [A04_wet_kick.mp3](../reference_audio/training/A04_wet_kick.mp3) | **dry / wet** | A03 is close and immediate — each kick stops cleanly. A04 has a long reverb tail that bleeds into the gap before the next beat. | On A04, close your eyes and count the beats — the reverb tail makes the gaps feel shorter and the mix feels distant. |
| [A05_gate_on.mp3](../reference_audio/training/A05_gate_on.mp3) vs [A06_gate_off.mp3](../reference_audio/training/A06_gate_off.mp3) | **gate** | A05 has rhythmic silence chopped into the pad at 16th-note resolution. A06 is a continuous drone. | On A05, the pad has gaps — moments where you hear nothing (or near-nothing). On A06, it is always on. |
| [A07_sweep_on.mp3](../reference_audio/training/A07_sweep_on.mp3) vs [A08_sweep_off.mp3](../reference_audio/training/A08_sweep_off.mp3) | **sweep** | A07 has a filter that opens up (brightens) at the start of each bar then closes again. A08 has a fixed, static timbre throughout. | On A07, the brightness of the pad changes over time — it gets brighter then darker cyclically. On A08, brightness is constant. |
| [A09_pump_on.mp3](../reference_audio/training/A09_pump_on.mp3) vs [A10_pump_off.mp3](../reference_audio/training/A10_pump_off.mp3) | **pump** | A09: the pad volume briefly dips on every kick hit then recovers. A10: pad and kick are at fixed, independent volumes. | On A09, the pad seems to breathe in time with the kick — louder in the gaps, quieter on the beat. On A10, the pad is steady regardless of the kick. |
| [A11_spread_stereo.mp3](../reference_audio/training/A11_spread_stereo.mp3) vs [A12_spread_mono.mp3](../reference_audio/training/A12_spread_mono.mp3) | **spread** | A11: on headphones, the pad is wide — left and right ears hear different content. A12: identical centre image in both ears. | Put one headphone to your ear and pull the other away. On A11, the sound changes significantly. On A12, it does not. |
| [A13_sub_with.mp3](../reference_audio/training/A13_sub_with.mp3) vs [A14_sub_without.mp3](../reference_audio/training/A14_sub_without.mp3) | **sub** | A13 has weight below 80 Hz — felt in the chest on speakers, or as a low pressure on headphones. A14 has had the sub removed by a high-pass filter. | On A14, the bass feels thin and nasal compared to A13. If you turn the volume up and still feel no low-end pressure, the sub is gone. |

### 7.3 Group B — Comparative pairs (Strudel ground truth vs Python synthesis)

For each pair: the Strudel file is the known-good SA reference. The Python file is what our
current synthesis produces. The gap between them is what we are working to close.

| Strudel (ground truth) | Python (current) | Dimension | What to listen for |
|---|---|---|---|
| [B01_pad_strudel.mp3](../reference_audio/training/B01_pad_strudel.mp3) | [B02_pad_python.mp3](../reference_audio/training/B02_pad_python.mp3) | Pad character | Gate rhythm, sweep depth, body/tail, spread |
| [B03_kick_tr909.mp3](../reference_audio/training/B03_kick_tr909.mp3) | [B04_kick_python.mp3](../reference_audio/training/B04_kick_python.mp3) | Rhythm & Drive | Transient click, body, pitch sweep |
| [B05_sidechain_strudel.mp3](../reference_audio/training/B05_sidechain_strudel.mp3) | [B06_sidechain_python.mp3](../reference_audio/training/B06_sidechain_python.mp3) | Pump | Depth of duck, recovery time, kick/pad relationship |
| [B07_fullmix_sa.mp3](../reference_audio/training/B07_fullmix_sa.mp3) | [B08_fullmix_ours.mp3](../reference_audio/training/B08_fullmix_ours.mp3) | All dimensions | Full 27s comparison — use the evaluation form from Section 4 |

### 7.4 Strudel reference snippets (browser, real-time)

The Strudel debug page (`research/strudel_debug.html`) contains live-playable versions of
every ear training concept. These require a browser but are the authoritative SA synthesis
source for each term.

To capture any snippet as WAV:
```bash
python tools/capture_strudel_wav.py --snippet c6 --duration 8 \
    --out research/reference_audio/training/strudel_c6_gate_on.wav
```

| Snippet | Label | Term demonstrated |
|---|---|---|
| `c4` | acid lead | character, sweep (Q=12 acid resonance) |
| `c5` | noisehat | transient, brightness (full-spectrum white noise) |
| `c6` | gate ON | gate (trancegate active) |
| `c7` | gate OFF | gate (continuous pad, no trancegate) |
| `c8` | sweep ON | sweep (lpenv=2 octaves active) |
| `c9` | sweep OFF | sweep (static filter, no lpenv) |
| `c10` | kick dry | dry, transient (TR-909 kick, no reverb) |
| `c11` | kick wet | wet, tail (same kick with room=0.9) |
| `c12` | pump ON | pump (sidechain duck active) |
| `c13` | pump OFF | pump (no ducking — fixed volumes) |

---

## 8. References

Engel, J., Hantrakul, L., Gu, C., & Roberts, A. (2020). DDSP: Differentiable digital
signal processing. In *International Conference on Learning Representations (ICLR 2020)*.
https://arxiv.org/abs/2001.04643

International Telecommunication Union. (2015). *Method for the subjective assessment of
intermediate quality level of audio systems* (ITU-R BS.1534-3). ITU.
https://www.itu.int/rec/R-REC-BS.1534

Yee-King, M. (2011). *Automatic sound synthesiser programming: Techniques and applications*
[Doctoral dissertation, University of Sussex]. (Supervisor: Mark d'Inverno.)
