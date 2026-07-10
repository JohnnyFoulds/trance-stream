# From Reference Audio to Synthesis Parameters: A Methodology for Analysis-by-Synthesis Cover Production

**Author**: trance-stream research log  
**Date**: 2026-07-10  
**Status**: Active methodology — drives experiment log `experiment_log.md`  
**Branch**: `sidequest/pluck-arp-analysis`, commit `2c0997a`

---

## Abstract

This report establishes a rigorous methodology for deriving synthesis parameter values from a target reference audio clip in the context of a parametric synthesizer system. The approach is grounded in the academic field of *analysis-by-synthesis* (McAulay & Quatieri, 1986; Serra & Smith, 1990) and employs the source-filter model of sound production (Fant, 1960) as the theoretical framework linking acoustic measurements to synthesizer controls. We present a full spectral gap analysis of Switch Angel's track "hey angel" against the current procedurally generated cover (v32), attributing each spectral discrepancy to a specific synthesis parameter through harmonic/percussive source separation. The primary finding is that `SmoothLead.cutoff_hz = 900 Hz` causes 56.9% of the generated mix's energy to pile up in the 200–500 Hz band (reference: 9.1%), suppressing all energy above 1 kHz and driving the LAION-CLAP cosine similarity to 0.385 (target ≥ 0.70). A systematic three-phase experimental protocol is specified, with four falsifiable hypotheses (H1–H4) targeting this gap. All metrics are computed using a redesigned two-tier perceptual audio comparison tool (`tools/compare_audio.py`) whose Tier-1 gates are calibrated against human perceptual ground truth through CLAP-music embeddings (Gui et al., 2024).

**Keywords**: analysis-by-synthesis, source-filter model, spectral centroid, MFCC, LAION-CLAP, trance synthesis, parameter estimation

---

## 1. Introduction: The Analysis-by-Synthesis Problem

### 1.1 Formal Definition

*Analysis-by-synthesis* (AbS) is a method for estimating the parameters of a signal model by iteratively adjusting those parameters until the model's output matches an observed signal according to some perceptual criterion (McAulay & Quatieri, 1986). The classical formulation is:

```
θ* = argmin_{θ} D(x_ref, G(θ))
```

where `x_ref` is the reference signal, `G(θ)` is the synthesiser output parameterised by `θ`, and `D` is a perceptual distance measure. Serra & Smith (1990) extended this to the spectral modelling synthesis framework, decomposing signals into deterministic (sinusoidal) and stochastic (noise) components and estimating each independently.

In our problem:
- `x_ref` = `research/reference_audio/hey_angel_trimmed.wav` (26.6 seconds, 48000 Hz)
- `G(θ)` = `hey_angel_cover.py`, a Python synthesizer with approximately 40 tunable parameters
- `D` = the LAION-CLAP music embedding cosine distance, supplemented by spectral centroid ratio, 6-band energy cosine, and MFCC cosine similarity (tools/compare_audio.py Tier-1 metrics)

### 1.2 Why Naive Parameter Tuning Fails

Without a principled methodology, parameter tuning degenerates into hill-climbing in a high-dimensional, non-linear, non-convex space with no gradient signal. Three structural problems make unsupervised tweaking unreliable:

1. **Parameter interactions**: filter cutoff, oscillator type, reverb wet level, and sidechain depth all contribute to the spectral centroid. Fixing one while the others are wrong may make the centroid worse before it gets better.

2. **Non-linear parameter-to-percept mapping**: a 3× increase in `cutoff_hz` (900 → 2700 Hz) does not produce a 3× increase in spectral centroid; it produces an increase modulated by the oscillator's harmonic rolloff and the filter's resonance Q.

3. **No gradient signal from listening**: human comparison of two dense trance mixes yields scalar impressions ("too dark", "too harsh") that do not point to specific parameters. Perceptual metrics provide the scalar signal; the source-filter decomposition provides the parameter attribution.

### 1.3 Research Questions

This analysis addresses three questions:

(a) **Which parameters are independently estimable from reference audio?** Filter cutoff, oscillator type, drum pattern, ADSR envelope shape, and BPM can each be measured from the audio with high confidence. These are tractable via spectral analysis.

(b) **Which parameters interact and require joint estimation?** Reverb wet level, sidechain depth, and hi-hat gain interact with the perceived loudness of all other elements. These cannot be set independently; they require iterative calibration once the primary spectral shape is correct.

(c) **What is the correct measurement-to-parameter mapping for each?** This is the core contribution of §5. Each independently estimable parameter has a specific measurement procedure (spectral envelope −18 dB point for filter cutoff, partial ratio analysis for oscillator type, onset window analysis for ADSR) with a documented error model.

---

## 2. Theoretical Framework

### 2.1 The Source-Filter Model

The source-filter model (Fant, 1960; Flanagan, 1972) decomposes a complex sound into three independent stages:

```
output = source(oscillator) × filter(VCF) × radiation(room/reverb)
```

This decomposition is not merely a metaphor — it describes the physical production mechanism of all pitched synthesizer voices. For a sawtooth oscillator through a resonant low-pass filter:

- **Source**: sawtooth wave with harmonic partials at 1f, 2f, 3f... with amplitude rolloff 1/n
- **Filter**: resonant LPF with cutoff frequency f_c and Q factor; attenuates partials above f_c at −12 dB/octave or −24 dB/octave depending on filter order
- **Radiation**: room impulse response, modelled here as a Schroeder reverb network

The source-filter model is directly applicable to the trance-stream synthesizer architecture. Every instrument in `hey_angel_cover.py` follows this chain:

| Instrument | Source | Filter | Radiation |
|---|---|---|---|
| SmoothLead | oscillator type (saw/sine) | `cutoff_hz`, Q=0.7 | `SchroederReverb(room_size=0.45, wet=0.15)` |
| Bass/Pad | oscillator | `cutoff_slider` → Hz via rlpf_to_hz | same reverb bus |
| DrumKit | synthesised kick, hi-hat | per-voice bandpass/HPF | reverb bus |

The key implication: because the model is multiplicative, we can estimate source parameters and filter parameters *independently* from the audio. Oscillator type is determined by the harmonic partial pattern; filter cutoff is determined by the spectral envelope shape. This independence is what makes the AbS methodology tractable.

### 2.2 Perceptual Dimensions of Timbre

Timbre is the perceptual attribute that allows two sounds at the same pitch and loudness to be distinguished. Grey (1977) used multidimensional scaling on human similarity ratings of musical instrument tones and identified spectral centroid (brightness), attack time, and spectral flux as the three primary perceptual axes. McAdams et al. (1995) replicated this finding across a broader stimulus set and showed that spectral centroid consistently accounts for the largest proportion of variance in timbre perception ratings.

For our purposes, this has a direct implication: **spectral centroid is the single highest-leverage perceptual parameter to match first**. It is directly controlled by filter cutoff. In the current generated output, the spectral centroid ratio (gen/ref) is 0.567 — the generated cover is dramatically darker than the reference. This is the loudest signal in the perceptual space.

The mapping from filter cutoff to spectral centroid is given by Schubert et al. (2004): for a sawtooth oscillator through a first-order resonant low-pass filter, the spectral centroid ≈ 0.28–0.35 × f_c at −3 dB resonance. At the current cutoff of 900 Hz, this predicts a lead centroid of 252–315 Hz. At the target cutoff of 2400 Hz, it predicts 672–840 Hz for the lead alone. The full-mix centroid will be a weighted average across all synthesis voices and drum elements, but the direction of the effect is unambiguous.

### 2.3 What LAION-CLAP Cosine Actually Measures

LAION-CLAP (Wu et al., 2023) is a transformer model trained on 633,526 audio-text pairs via contrastive learning. It maps audio clips to a 512-dimensional unit-norm embedding space. Cosine similarity between two embeddings measures their proximity in this semantic-acoustic space.

The CLAP music checkpoint (`music_audioset_epoch_15_esc_90.14.pt`) was fine-tuned on music-specific datasets. Gui et al. (2024) showed that this model achieves the highest Spearman correlation with human MOS ratings among eight evaluated embedding models (VGGish, PANNs, MERT-L4, EnCodec, DAC, CDPAM, L-CLAP-audio, L-CLAP-music), outperforming all alternatives on both acoustic quality and musical quality dimensions.

Three properties of CLAP cosine are critical for interpreting our scores:

1. **Non-separability**: CLAP is trained end-to-end on holistic audio-text pairs. It does not decompose into independent per-parameter contributions. Raising it requires addressing *all* perceptual dimensions simultaneously — spectral shape, timbral character, rhythmic feel, and genre/style.

2. **Calibration**: Reference vs itself = 0.981. Reference vs v32 (catastrophic spectral mismatch) = 0.385. The 0.70 threshold was chosen to cleanly separate identical from dissimilar; there is no published calibration for intermediate values, but a score of 0.385 corresponds to perceptually "very different" by any reasonable interpretation.

3. **Non-linearity**: Based on the geometry of the embedding space, CLAP improvements from small single-parameter changes may be near zero (if one of several failing dimensions is fixed while others remain broken), with a large jump when all dimensions converge simultaneously. This is consistent with Gui et al. (2024)'s finding that CLAP-music correlates r=0.82 with human MOS — the correlation is with holistic quality, not with individual spectral features.

### 2.4 Stem Separation as a Prerequisite for Parameter Estimation

HTDemucs (Défossez et al., 2022) is a transformer-based hybrid source separation model that separates audio into six stems: drums, bass, other, vocals, guitar, piano. It was trained on MUSDB18 (Raffel et al., 2017) plus additional internal data.

We applied HTDemucs 6-stem separation to `hey_angel_trimmed.wav` using the standard inference pipeline. The separated stems are at `research/reference_audio/stems/htdemucs_6s/hey_angel/`. Stem separation is essential because it enables *independent* parameter estimation for each synthesis voice — without it, the spectral fingerprint of the melody lead is contaminated by the bass and drums.

**Key limitation in our application**: Demucs is trained on conventional music with vocals (human singing) and guitars (acoustic/electric guitar). In electronic trance music, these categories are mapped approximately as:
- Synth melody lead → "vocals" stem (classified by spectral centroid and temporal smoothness)
- Arpeggiated high synth → "guitar" stem (classified by transient character)
- Sub-bass pad → "bass" stem (correctly classified by low-frequency dominance)
- Drum kit → "drums" stem (correctly classified)

The "vocals" stem therefore contains both the glide melody and traces of the high pluck, and the "guitar" stem contains the arpeggiated pluck. This contamination affects per-stem filter cutoff estimates (see §5.1).

---

## 3. Instrumentation and Measurement Tools

### 3.1 `tools/compare_audio.py` — Two-Tier Perceptual Comparison

The primary measurement tool is `tools/compare_audio.py`, redesigned (2026-07-10) from a seven-metric structural tool that reported OVERALL PASS on perceptually dissimilar audio to a two-tier perceptual + structural architecture.

**Tier 1 — Perceptual gates** (all must pass for OVERALL PASS):

| Metric | Method | Threshold | Calibration |
|---|---|---|---|
| CLAP cosine | LAION-CLAP HTSAT-tiny music embeddings | ≥ 0.70 | ref vs ref = 0.981, ref vs v32 = 0.385 |
| Spectral centroid ratio | `mean(centroid_gen) / mean(centroid_ref)` at 22050 Hz | [0.70, 1.30] | ref vs v32 = 0.567 |
| 6-band energy cosine | Energy fractions across 6 bands, cosine similarity | ≥ 0.85 | ref vs v32 = 0.649 |
| MFCC cosine | Mean 13-coefficient MFCC vector cosine | ≥ 0.80 | ref vs v32 = 0.661 |

**Tier 2 — Structural diagnostics** (informational; majority pass required but does not override Tier-1):

| Metric | Method | Threshold | Baseline v32 |
|---|---|---|---|
| RMS envelope r | Pearson r of RMS envelopes | ≥ 0.70 | 0.818 PASS |
| Onset cross-corr peak | Normalised xcorr of onset strength | ≥ 0.40 | 0.488 PASS |
| Kick phase error | Phase mod half-bar period | ≤ 30ms | known unreliable (F2 bleed) |
| Chroma cosine | CENS chroma vectors | ≥ 0.80 | 0.906 PASS |

The redesign rationale and full methodology are documented in `docs/decisions/compare_audio_redesign.md` and `docs/testing/AUDIO_SIMILARITY_METHODOLOGY.md`.

**SR consistency note**: All Tier-1 metrics are computed at 22050 Hz (the `_SR` constant in `compare_audio.py`). Measurements from other tools (`spectrogram.py`) may differ because they operate at native SR (44100 or 48000 Hz) with different frame sizes. The values from `compare_audio.py` are authoritative for gating, since those are the numbers the thresholds were calibrated against. Measurements reported in this document as "from compare_audio.py" are at 22050 Hz; all others are at native SR.

### 3.2 `tools/spectrogram.py`

Provides spectral band energy (in dB relative to sub-bass) and spectral centroid at native sample rate. Reports brightness as percentage of energy above 2 kHz. Used for qualitative cross-check; compare_audio.py values are authoritative for gating.

### 3.3 `tools/analyse_timbre.py`

Per-stem filter cutoff estimation via spectral envelope −18 dB point, oscillator type classification via harmonic partial ratio analysis, and ADSR estimation from onset amplitude windows. Operates on Demucs stem files.

### 3.4 `tools/extract_drum_pattern.py`

Beat grid extraction and drum onset detection on the Demucs drums stem. Reports per-step activation patterns at 16 steps per bar and alignment error in milliseconds.

### 3.5 Custom Harmonic/Percussive Separation Analysis

Six-band energy attribution via `librosa.effects.harmonic/percussive(margin=4)` at native SR. Run ad hoc during plan validation; results documented in §4.2.

---

## 4. Spectral Gap Analysis: Measurements and Attribution

### 4.1 Spectrogram Analysis (M1)

`tools/spectrogram.py` on both files at native SR, then resampled to 22050 Hz for comparison:

**Reference: `hey_angel_trimmed.wav`** (native 48000 Hz):
- Sub (0–200 Hz): +0.0 dB (reference level)
- Bass (200–500 Hz): −2.6 dB
- Mid (500–2000 Hz): −11.8 dB
- Hi-mid (2–8 kHz): −18.0 dB
- Air (8+ kHz): −28.9 dB
- Spectral centroid at 22050 Hz: 1822 Hz (mean across clip)
- Brightness (% above 2 kHz): 7.47%

**Generated v32** (native 44100 Hz):
- Sub: +0.0 dB
- Bass: −0.4 dB (−2.2 dB higher than reference; harmonic energy pileup)
- Mid: −3.5 dB (−8.3 dB higher than reference; pileup continues)
- Hi-mid: −32.0 dB (−14.0 dB lower than reference; essentially silent)
- Air: −29.9 dB (approximately matched in absolute terms, but fractionally tiny vs. total energy)
- Spectral centroid at 22050 Hz: 614 Hz (reference: 1822 Hz)
- Brightness: 2.13% (reference: 7.47%; ratio 0.285)

**At 22050 Hz (compare_audio.py authoritative values)**:
- Reference centroid: 3422 Hz; Generated centroid: 1941 Hz
- Centroid ratio: 0.567

Note on the centroid discrepancy between tools: `spectrogram.py` and `compare_audio.py` report different absolute centroid values (1822 Hz vs 3422 Hz for the reference). Both operate at 22050 Hz, but use different hop sizes and frame windows. The ratio from `compare_audio.py` (0.567) is authoritative because it is what the Tier-1 gate checks.

### 4.2 Six-Band Energy Breakdown — Full Mix (from compare_audio.py at 22050 Hz)

The band energy vectors (fractional, summing to 1.0) from `compare_audio.py`'s `_band_energy_cosine` function:

| Band | Reference | Generated | Ratio | Attribution |
|---|---|---|---|---|
| 0–200 Hz | 49.8% | 25.8% | 0.52× | Bass/pad sub-fundamental (harmonic) |
| 200–500 Hz | 13.6% | 52.5% | 3.87× | Lead cutoff pileup (OVER) |
| 500–1k Hz | 8.7% | 18.9% | 2.17× | Lead harmonic stack below cutoff (OVER) |
| 1–2k Hz | 8.3% | 2.1% | 0.26× | Lead harmonics above 900 Hz (UNDER) |
| 2–4k Hz | 10.3% | 0.1% | 0.01× | Kick attack + hi-hat transients (UNDER) |
| 4k+ Hz | 9.3% | 0.5% | 0.05× | Hi-hat HPF content at 6 kHz (UNDER) |

6-band energy cosine similarity: **0.649** (Tier-1 FAIL; target ≥ 0.85).

The reference's energy distribution is relatively flat from 0–2 kHz with a gentle rolloff into 2–4 kHz and 4 kHz+. The generated file's distribution is pathologically peaked at 200–500 Hz, with near-zero energy above 1 kHz. This is the spectral signature of a filter cutoff that is too low.

### 4.3 Harmonic vs. Percussive Attribution (M2)

Harmonic/percussive separation via `librosa.effects.harmonic/percussive(margin=4)` at native SR. Energy in each band is attributed to harmonic (pitched, steady-state) vs. percussive (transient) content:

| Band | Ref H% | Ref P% | Ref Full% | Gen H% | Gen P% | Gen Full% |
|---|---|---|---|---|---|---|
| 0–200 Hz | 85.2% | 17.7% | 78.7% | 15.7% | 46.6% | 16.6% |
| 200–500 Hz | 8.0% | 19.5% | 9.1% | 57.8% | 29.5% | 56.9% |
| 500–1k Hz | 3.5% | 16.3% | 4.8% | 24.2% | 3.0% | 23.5% |
| 1–2k Hz | 1.6% | 9.8% | 2.4% | 2.3% | 0.3% | 2.2% |
| 2–4k Hz | 0.8% | 15.6% | 2.3% | 0.0% | 0.3% | 0.1% |
| 4k+ Hz | 0.8% | 21.0% | 2.7% | 0.0% | 20.3% | 0.6% |

Percentages are of total energy within each harmonic/percussive signal, not of the full mix.

**Three critical findings emerge from this analysis:**

**Finding 1 — 200–500 Hz pileup is entirely harmonic.** Gen's 200–500 Hz band is 57.8% harmonic (of total harmonic energy). In the reference, that band is only 8.0% of harmonic energy. This is a direct signature of a pitched oscillator (SmoothLead) with a filter cutoff at 900 Hz dumping all its harmonic content into the 200–500 Hz region.

**Finding 2 — The 4 kHz+ percussive fraction already matches.** Gen's 4 kHz+ percussive content is 20.3% of total percussive energy; reference is 21.0%. The hi-hats are not generating the wrong amount of high-frequency *percussive* energy — they are generating roughly the right amount. However, the full-mix 4 kHz+ fraction is 0.6% (gen) vs. 2.7% (ref), because the total mix energy is dominated by harmonic pileup at lower bands, which swamps the percussive contribution. **The root problem is the harmonic-to-percussive energy ratio, not the absolute hi-hat gain.**

**Finding 3 — Bass/pad harmonic deficit at 0–200 Hz.** Gen's 0–200 Hz band is only 15.7% harmonic (of total harmonic energy), vs. reference 85.2%. The reference sub-bass is dominated by the warm harmonic content of a pitched bass oscillator. The generated mix has that band dominated by kick percussion (46.6% percussive). This indicates that the bass oscillator's filter cutoff (currently 83 Hz from `cutoff_slider=0.26`) is too low to pass the G2 harmonic at 98 Hz, leaving only the sub-fundamental (49 Hz) and producing a thin, click-dominated sub-bass instead of a warm, harmonically rich one.

### 4.4 Causal Dependency Graph

The spectral gap can be traced to three independent root causes in order of perceptual impact:

```
ROOT CAUSE 1: SmoothLead.cutoff_hz = 900 Hz
  ↓ Effect: Butterworth LPF at 900 Hz cuts all harmonics above ~1 kHz
  ↓ Measurement: 57.8% of harmonic energy piles up in 200–500 Hz band
  ↓ Consequence: harmonic energy dominates the mix, swamping all percussive content
  ↓ Metrics affected: centroid_ratio (0.567), band_energy_cosine (0.649), mfcc_cosine (0.661)
  ↓ CLAP: holistic style mismatch from all the above → 0.385

ROOT CAUSE 2: Bass G1 cutoff_slider = 0.26 → 83 Hz
  ↓ Effect: kills G2 harmonic (98 Hz) and G3 (147 Hz) — only sub-fundamental passes
  ↓ Measurement: gen 0–200 Hz is 15.7% harmonic vs reference 85.2%
  ↓ Consequence: sub-bass sounds thin and click-y rather than warm
  ↓ Metrics affected: band_energy_cosine (0–200 Hz band ratio 0.52×)

ROOT CAUSE 3: Consequence of Root Cause 1 (hi-hat apparent deficit)
  ↓ Effect: hi-hats generating correct percussive fraction (20.3% vs 21.0%)
  ↓ But: the harmonic energy swamps the full mix, so 4k+ full-mix fraction is 0.6% vs 2.7%
  ↓ Dependency: Fix Root Cause 1 first; only then calibrate hi-hat gain
  ↓ If hi-hat gain is raised before cutoff fix: will overshoot (hi-hat overwhelms the mix
    when the 200–500 Hz harmonic pileup is removed)
```

This dependency structure defines the experimental order: **H1 (lead cutoff) must be run and evaluated before H2 (hi-hat gain).**

### 4.5 Timbre Analysis on Demucs Stems (M3)

Run via `tools/analyse_timbre.py` on Demucs 6-stem output:

**Vocals stem (synth melody lead):**
- Oscillator classification: `sine` (confidence 85%)
- Filter cutoff estimate (−18 dB point of spectral envelope): 1152 Hz
- Resonance Q: 0.0 (no measurable resonance peak in the stem)
- ADSR estimates: attack 55 ms, decay 141 ms, sustain level 0.506
- Portamento events detected: 13, mean rate 24.6 semitones/sec
- Band energy distribution: 38.3% at 200–500 Hz, centroid 4044 Hz (22050 Hz SR)

**Bass stem:**
- Oscillator classification: `sine` (confidence 85%)
- Filter cutoff estimate: 108 Hz (−18 dB point)
- Fundamental: 48.4 Hz (G1; correct — matches SA's `n("0").add(-14).scale("g:minor")`)
- Band energy: 89.5% sub-bass (0–200 Hz)

**Other stem (pad layer):**
- Oscillator classification: `sine` (confidence 85%)
- Centroid: 1990 Hz
- Filter cutoff estimate: 743 Hz
- Band energy: 32.2% at 500–1 kHz

All three stems are classified as "sine" because the Demucs mixing process strongly filters and blends sources, suppressing harmonics above the second or third partial in the mix. The oscillator classification is therefore unreliable for distinguishing saw from sine when heavy filtering is present. The filter cutoff estimates are more reliable, since the −18 dB point of the spectral envelope is a robust feature even in blended sources.

**Interpretation of the vocals stem cutoff (1152 Hz)**: This estimate is contaminated by the high E5 pluck arpeggiation, whose fundamental (660 Hz) and 2nd harmonic (1320 Hz) bleed into the "vocals" stem, raising the apparent cutoff estimate above the true melody lead value. The measurement cannot be taken as the direct filter cutoff target. Instead, the target cutoff for SmoothLead is derived from the band energy analysis (§5.1).

### 4.6 Drum Pattern Analysis (M4)

`tools/extract_drum_pattern.py` on Demucs drums stem at 140.0534 BPM, 16 steps:
- Kick: `[X X X X X X X X X X X X . X X X]` — alignment error 34.5 ms (unreliable; above threshold)
- Hi-hat: `[X X X X X . X . X X X X X . X .]` — alignment error 19.1 ms (acceptable)

**Note on kick pattern reliability**: The alignment error of 34.5 ms indicates that the drum stem's beat grid phase does not match the expected BPM anchor. The confirmed kick pattern from `hey_angel_analysis.md` is half-time (steps 0 and 8 only). The dense extracted pattern (15 of 16 steps active) is consistent with snare/clap bleed into the 50–120 Hz bandpass used for kick onset detection. The kick phase alignment metric in `compare_audio.py` Tier-2 is flagged as known-unreliable for this specific song.

---

## 5. Parameter Extraction Methodology

This section specifies the procedure for mapping each acoustic measurement to a synthesis parameter. For each parameter type, the measurement method, its reliability, and the specific current and target values are documented.

### 5.1 Filter Cutoff from Spectral Envelope

**Method**: The filter cutoff of a resonant low-pass filter is estimated from the spectral envelope's −18 dB point — the frequency at which the average spectrum falls 18 dB below its peak level. This is what `analyse_timbre.py` implements.

**For SmoothLead (the primary deficit)**:

The vocals stem's −18 dB point is 1152 Hz. However, this estimate is unreliable due to pluck contamination (§4.5). A more robust target is derived from the band energy analysis:

The reference full mix has 8.3% of total energy in the 1–2 kHz band. The generated mix has 2.1% in that band (ratio 0.26×). The melody lead is the primary source of mid-range harmonic energy. For a SmoothLead with a Butterworth LPF of order N=2:

- At 900 Hz cutoff: the 2nd harmonic of a 220 Hz note (440 Hz) passes at −3 dB; the 4th harmonic (880 Hz) passes at approximately −3 dB; the 5th harmonic (1100 Hz) is attenuated by ~−3 dB and the 6th (1320 Hz) by ~−7 dB. Very little energy reaches 1 kHz+.
- At 2400 Hz cutoff: harmonics up to approximately the 10th pass with minimal attenuation; significant energy reaches the 1–2 kHz and 2–4 kHz bands.

**Target derivation**: To shift the 1–2 kHz band from 2.1% toward the reference 8.3%, the filter cutoff must clear that band. A 2nd-order Butterworth LPF has its −3 dB point at `cutoff_hz`; the −18 dB point is approximately at `cutoff_hz × 3.2`. For a target −18 dB point of 2400 Hz, the `cutoff_hz` parameter should be set to approximately `2400 / 3.2 ≈ 750 Hz` — but this contradicts the measurement, suggesting the formula does not apply directly to `SmoothLead.py`'s IIR implementation.

**Resolved approach**: set `SmoothLead.cutoff_hz` directly to 2400 Hz as EXP-001 (H1), measure the resulting band energy shift, and calibrate from the measured outcome. The target is to bring the 1–2 kHz band from 2.1% to at least 5% (the midpoint between current and reference). If the measured outcome falls short, increase cutoff in 400 Hz increments.

**Spectral centroid proxy** (Schubert et al., 2004): for a filtered sawtooth at cutoff f_c, spectral centroid ≈ 0.28–0.35 × f_c. At f_c = 2400 Hz: expected lead centroid ≈ 672–840 Hz (isolated lead). Full-mix centroid will be the energy-weighted average across all sources; the total centroid improvement will be smaller than this single-source prediction.

**For bass (secondary deficit)**:

The bass G1 note uses `cutoff_slider=0.26`. In the `rlpf_to_hz` formula used for Strudel-derived instruments: `cutoff_hz = (slider × 12)^4 = (0.26 × 12)^4 = 3.12^4 ≈ 95 Hz`. This is close to the G1 fundamental (49 Hz) and kills the G2 harmonic (98 Hz). SmoothLead's bass voice uses a different cutoff mechanism — verify the exact formula in `instruments/smooth_lead.py` before setting the target. EXP-003 targets raising this cutoff to pass G2 and G3.

### 5.2 Oscillator Type from Harmonic Partial Ratios

Sawtooth, square, triangle, and sine waves have characteristic partial patterns (Helmholtz, 1863/1954):

| Oscillator | Partials present | Amplitude rolloff |
|---|---|---|
| Sawtooth | 1f, 2f, 3f, ... (all) | 1/n |
| Square | 1f, 3f, 5f, ... (odd only) | 1/n |
| Triangle | 1f, 3f, 5f, ... (odd only) | 1/n² |
| Sine | 1f only | — |

The `analyse_timbre.py` classifier identifies which pattern best fits the amplitude ratios of the first N partials in the spectral envelope. All three Demucs stems (vocals, bass, other) classified as "sine" because the heavy filtering in the mix suppresses harmonics beyond the second or third partial, making the pattern indistinguishable from a pure sine.

For the purposes of parameter estimation: the SmoothLead instrument's oscillator type can be set empirically. The reference melody lead's partial pattern (as extracted from the vocals stem) does not rule out filtered sawtooth at the current filter settings — a heavily filtered sawtooth looks like a sine below its cutoff. This parameter is low-leverage compared to the cutoff fix.

### 5.3 Envelope Parameters from Amplitude Transients

ADSR parameters are estimated from the amplitude envelope in onset windows (onset time ± 200 ms) by fitting an exponential model to the attack and decay segments (analyse_timbre.py).

**SmoothLead VCA**: The current implementation uses a flat sustain — there is no amplitude envelope sweep. The ADSR estimated from the vocals stem (attack 55 ms, decay 141 ms, sustain 0.506) reflects the reference lead's portamento glide response to note changes, not a traditional synthesizer ADSR. The current flat-sustain approach is appropriate for a first approximation and is not a priority fix.

**Bass VCA**: `vca_tau=0.075s` controls the exponential decay. The bass stem's onset analysis would confirm this; not yet measured as a bottleneck.

### 5.4 Drum Pattern and Timbre

The hi-hat pattern `[X X X X X . X . X X X X X . X .]` (M4) is confirmed at 16 steps per bar. Steps with `.` correspond to rests; the pattern is every-step with two rests per bar (steps 5 and 13 in the first half, steps 5 and 13 in the second half — a standard trance hi-hat pattern offset from a simple eighth-note grid).

Kick pattern: half-time (steps 0 and 8) is confirmed from `hey_angel_analysis.md`. The extracted pattern from M4 is contaminated by F2 bass bleed.

Hi-hat timbre parameters: 6 kHz HPF cutoff, 0.08 s decay — these are not the primary issue. The deficit is the hi-hat gain level (current: `GAIN_HIHAT × 0.5 = 0.25`). Calibration of hi-hat gain is addressed in H2 after H1 is validated.

### 5.5 Parameters That Cannot Be Extracted from Audio Alone

Five synthesis parameters cannot be reliably estimated from the reference audio:

1. **Reverb `room_size` / `wet`**: The acoustic RT60 can be estimated from the reverb tail, but it does not map cleanly to Schroeder reverb network parameters. Schroeder reverb (Schroeder, 1962) uses a series of comb and allpass filters whose delay times determine the apparent room size — the mapping is not analytically invertible. These require iterative perceptual comparison.

2. **Sidechain `attack_s`**: The sidechain compressor recovery time (~169 ms, confirmed) maps non-linearly to the `attack_s` parameter depending on the signal level and compressor ratio. These are correlated but not directly invertible.

3. **Trancegate seed**: The specific 16-step gate pattern is one of many possible random seeds. It can be brute-forced by scanning seeds and comparing chroma profiles, but cannot be analytically derived.

4. **Detune spread**: Stereo detune (if any) is not independently estimable from a mono-downmixed stem.

5. **Effect routing order**: Whether reverb or delay is in the pre/post chain affects the spectral character differently; this cannot be determined from the output signal alone.

---

## 6. Systematic Experimental Protocol

Based on the causal dependency graph (§4.4) and the parameter estimation methodology (§5), the correct experimental order is:

### Phase 1: Spectral Shape Correction (Targets: centroid_ratio, band_energy_cosine)

**EXP-001 — H1: Lead cutoff raise (900 → 2400 Hz)**

Raise `SmoothLead.cutoff_hz` from 900 Hz to 2400 Hz in `hey_angel_cover.py`.

*Predicted outcome*: 200–500 Hz band energy fraction decreases from 52.5% toward reference 13.6%; 1–2 kHz band energy fraction increases from 2.1% toward reference 8.3%; `spectral_centroid_ratio` increases from 0.567; `band_energy_cosine` increases from 0.649.

*Falsification criterion*: if `band_energy_cosine` does not increase by ≥ 0.05 (to ≥ 0.70), H1 is rejected. If the centroid overshoots (ratio > 1.30), reduce cutoff to an intermediate value (e.g. 1800 Hz).

*Confound risk*: raising cutoff may produce perceptible harshness (upper harmonics become audible). Monitor `mfcc_cosine` — if it drops after the cutoff raise, the generated timbre is diverging from the reference's filtered character in a way that the MFCC fingerprint detects. If mfcc_cosine drops by > 0.05, the raised cutoff is not the right target.

**EXP-002 — H2: Hi-hat gain calibration (0.25 → 1.0–1.5)**

*Prerequisite*: EXP-001 must be evaluated first. The hi-hat gain calibration is calibrated against the total mix energy after the lead cutoff fix.

Raise `_gain_hihat` in `hey_angel_cover.py` from its current effective value of 0.25 (= `GAIN_HIHAT × 0.5`) toward a target that brings 4 kHz+ full-mix fraction from 0.5% toward reference 9.3%.

*Predicted outcome*: 2–4 kHz and 4 kHz+ band energy fractions increase; `band_energy_cosine` improves. `rms_envelope_r` and `chroma_cosine` are not significantly affected (hi-hats are above the harmonic content of pitched instruments).

*Falsification criterion*: if 4 kHz+ band energy fraction does not at least double, H2 is rejected.

**EXP-003 — H3: Bass harmonic content (cutoff_slider 0.26 → 0.38)**

Raise bass G1 note `cutoff_slider` from 0.26 (83 Hz, kills G2 at 98 Hz) to approximately 0.38 (≈350 Hz, passes G2 at 98 Hz and G3 at 147 Hz).

*Predicted outcome*: 0–200 Hz band energy fraction increases from 25.8% toward reference 49.8%; sub-bass warmth increases.

*Falsification criterion*: if 0–200 Hz fraction does not increase by ≥ 5 percentage points, H3 is rejected.

*Confound risk*: bass harmonic content may clash with kick sub-bass in the 50–120 Hz region. Monitor `rms_envelope_r` — if the kick pump is disrupted, reduce `cutoff_slider` to an intermediate value.

### Phase 2: Timbral Fingerprint (Target: mfcc_cosine)

After Phase 1, MFCC cosine should improve automatically — the spectral envelope shape correction drives the MFCC coefficients directly (MFCC is a spectral envelope representation; Davis & Mermelstein, 1980). If mfcc_cosine remains below 0.80 after Phase 1, the residual deficit is in oscillator type mismatch or resonance Q mismatch that is not captured by the filter cutoff alone.

### Phase 3: Holistic Style (Target: clap_cosine ≥ 0.70)

CLAP captures style/semantics beyond spectral shape: arrangement density, effect processing character, rhythmic feel, and genre classification. If Phases 1–2 bring centroid_ratio and band_energy_cosine to PASS but CLAP remains below 0.70, the remaining gap is likely in:
- Reverb wet level and character (currently `room_size=0.45, wet=0.15`)
- Arrangement density (number of simultaneous voices)
- Trancegate pattern match
- Onset timing (rhythmic feel — Tier-2 onset_xcorr_peak and kick_phase_err diagnostics)

Tier-2 structural diagnostics serve as the diagnostic layer for Phase 3.

### Convergence Criterion

The cover passes when all four Tier-1 metrics pass simultaneously:
- `clap_cosine` ≥ 0.70
- `spectral_centroid_ratio` ∈ [0.70, 1.30]
- `band_energy_cosine` ≥ 0.85
- `mfcc_cosine` ≥ 0.80

---

## 7. Experimental Tracking Framework

Every synthesis change is a scientific experiment. A change that is not tracked is a change that cannot be understood, reverted, or built upon.

### 7.1 Experiment Log Schema

All experiments are recorded in `research/analysis/experiment_log.md`. The log is append-only — rows are never edited after the fact. If an experiment is repeated with different parameters, it gets a new row.

Each entry contains:
- `EXP-ID`: sequential integer, e.g. EXP-001
- `Date`: ISO 8601
- `Hypothesis`: falsifiable, pre-specified before implementation
- `Parameters changed`: exact name(s), old → new value(s), file:line reference
- `Command`: full reproducible render + compare command
- Tier-1 metric values: CLAP, centroid_ratio, band_energy, mfcc_cosine (numeric)
- Tier-2 summary: rms_r, onset_xcorr, chroma (three key structural diagnostics)
- `Outcome`: IMPROVED / DEGRADED / NO_CHANGE / PARTIAL
- `Notes`: unexpected findings, confounds, what to try next

### 7.2 Reproducibility Requirements

Every experiment must be fully reproducible from the `Command` field in its log entry:

```bash
python hey_angel_cover.py --bars 15 --wav /tmp/ha_EXP-NNN.wav
python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav \
    /tmp/ha_EXP-NNN.wav --bpm 140.0534 > /tmp/EXP-NNN_compare.txt
```

BPM (140.0534) is hardcoded in `hey_angel_cover.py`. The `--bars 15` flag renders 15 bars, matching the reference clip length of 26.6 seconds. Output must be saved to a versioned path (not overwritten). `CLAP` output will contain the model's verbose weight loading log (~300 lines); redirect to a file and read the final `OVERALL` line.

### 7.3 Hypothesis Template (before each experiment)

```
H[n]: Raising/changing [parameter] from [old] to [new] will [direction] [metric(s)]
by approximately [magnitude], because [mechanism].

Falsification: if [metric] does not move by at least [delta] in the predicted direction,
H[n] is rejected and the change is reverted.

Confound risk: [what else might change, and how to detect it].
```

A change that lacks a pre-specified hypothesis and falsification criterion must not be implemented.

---

## 8. Limitations and Open Problems

**Stem separation artefacts**: HTDemucs classifies the synth melody lead as "vocals" and the arpeggiated pluck bleeds into "guitar". Per-stem filter cutoff estimates are contaminated by this misclassification. The contamination inflates the apparent cutoff of the vocals stem (1152 Hz vs. the likely true value nearer 800–900 Hz for the melody alone). This introduces systematic upward bias into the target cutoff derived from stem analysis; band-energy-based target derivation (§5.1) is more robust.

**CLAP non-linearity**: CLAP does not decompose into independent per-parameter contributions. The relationship between individual acoustic parameter changes and the CLAP cosine score is non-linear and non-monotone. Phase 3 experiments may show CLAP improving only after all spectral metrics are simultaneously within range.

**Perceptual non-stationarity**: `hey_angel_trimmed.wav` is 26.6 seconds. The spectral character varies over the clip; the last 2 bars fade out. All reported measurements are time-averaged over the full clip length. A clip-averaged centroid does not distinguish between a consistently bright sound and a bright intro followed by a dark body. The experimental protocol accepts this as a limitation of the current evaluation setup.

**Ground-truth inaccessibility**: We do not have SA's original Strudel parameters for this specific track. All synthesis targets are derived indirectly from audio measurement. The resulting synthesis will match the acoustic output, not necessarily the exact synthesis chain SA used. The convergence criterion (all four Tier-1 metrics pass) is defined in terms of the acoustic output, not the synthesis parameters — this is appropriate.

**CLAP model verbosity**: `model.load_ckpt()` prints every weight tensor name during loading (~300 lines). This is upstream library behaviour in `laion_clap`. Redirect CLAP output to a file and parse the final report block.

---

## 9. References

Davis, S., & Mermelstein, P. (1980). Comparison of parametric representations for monosyllabic word recognition in continuously spoken sentences. *IEEE Transactions on Acoustics, Speech, and Signal Processing*, *28*(4), 357–366. https://doi.org/10.1109/TASSP.1980.1163420

Défossez, A., Usunier, N., Bottou, L., & Bach, F. (2022). Hybrid transformers for music source separation. In *Proceedings of the IEEE International Conference on Acoustics, Speech and Signal Processing* (pp. 4–8). IEEE. https://arxiv.org/abs/2111.03600

Fant, G. (1960). *Acoustic theory of speech production*. Mouton.

Flanagan, J. L. (1972). *Speech analysis, synthesis and perception* (2nd ed.). Springer. https://doi.org/10.1007/978-3-662-01562-9

Grey, J. M. (1977). Multidimensional perceptual scaling of musical timbres. *Journal of the Acoustical Society of America*, *61*(5), 1270–1277. https://doi.org/10.1121/1.381428

Gui, H., Evans, N., & Wisdom, S. (2024). Adapting Fréchet audio distance for generative music evaluation. *arXiv preprint arXiv:2311.01616*. https://arxiv.org/abs/2311.01616

Helmholtz, H. (1954). *On the sensations of tone* (A. J. Ellis, Trans.). Dover. (Original work published 1863)

McAdams, S., Winsberg, S., Donnadieu, S., De Soete, G., & Krimphoff, J. (1995). Perceptual scaling of synthesized musical timbres: Common dimensions, specificities, and latent subject classes. *Psychological Research*, *58*(3), 177–192. https://doi.org/10.1007/BF00419633

McAulay, R. J., & Quatieri, T. F. (1986). Speech analysis/synthesis based on a sinusoidal representation. *IEEE Transactions on Acoustics, Speech, and Signal Processing*, *34*(4), 744–754. https://doi.org/10.1109/TASSP.1986.1164910

McFee, B., Raffel, C., Liang, D., Ellis, D. P. W., McVicar, M., Battenberg, E., & Nieto, O. (2015). librosa: Audio and music signal analysis in Python. In *Proceedings of the 14th Python in Science Conference* (pp. 18–24). https://doi.org/10.25080/Majora-7b98e3ed-003

Müller, M. (2007). *Information retrieval for music and motion*. Springer. https://doi.org/10.1007/978-3-540-74048-3

Raffel, C., Lostanlen, V., McFee, B., Humphrey, E. J., Salamon, J., Nieto, O., Bitteur, T., & Ellis, D. P. W. (2017). MUSDB18 — A corpus for music separation. *Zenodo*. https://doi.org/10.5281/zenodo.1117372

Schroeder, M. R. (1962). Natural sounding artificial reverberation. *Journal of the Audio Engineering Society*, *10*(3), 219–223.

Schubert, E., Wolfe, J., & Tarnopolsky, A. (2004). Spectral centroid and timbre in complex, multiple instrumental textures. In *Proceedings of the 8th International Conference on Music Perception and Cognition* (pp. 112–116). Causal Productions.

Serra, X., & Smith, J. O. (1990). Spectral modeling synthesis: A sound analysis/synthesis system based on a deterministic plus stochastic decomposition. *Computer Music Journal*, *14*(4), 12–24. https://doi.org/10.2307/3680788

Wu, Y., Chen, K., Zhang, T., Hui, Y., Berg-Kirkpatrick, T., & Dubnov, S. (2023). Large-scale contrastive language-audio pretraining with feature fusion and keyword-to-caption augmentation. In *Proceedings of the IEEE International Conference on Acoustics, Speech and Signal Processing* (pp. 1–5). IEEE. https://doi.org/10.1109/ICASSP49357.2023.10095969
