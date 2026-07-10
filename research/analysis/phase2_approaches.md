# Phase 2 Approaches: Closing the CLAP Gap

**Date**: 2026-07-11  
**Context**: After two full CMA-ES runs (OPT-001, OPT-002) across a 15-dimensional mixing/gain/filter
parameter space, CLAP has plateaued at 0.622 against a target of 0.70. All three other Tier-1
metrics now pass simultaneously (OPT-002: centroid=0.731, band_energy=0.964, mfcc=0.832).
The remaining gap is 0.078 CLAP units. This document surveys possible approaches, their
theoretical basis, and the trade-offs, to inform planning for the next phase.

---

## 1. What the data tells us

### 1.1 The CMA-ES plateau is real

Two independent CMA-ES runs from different warm starts and different loss functions converged
to similar ceilings (0.635, 0.657 evaluated during optimisation; 0.582, 0.622 at gate check).
The gap between optimiser best and gate check CLAP is not regression — it's noise from the
optimiser sampling `xbest` rather than the single highest-scoring eval. Both runs show ~1000+
consecutive evaluations without improvement before terminating.

This is consistent with what Yee-King (c. 2011) observed for evolutionary synthesis matching:
optimisers converge to a local minimum that is spectrally close but perceptually audible as
different. The objective surface flattens before the perceptual gap closes.

### 1.2 What the optimiser found

The OPT-002 best params are diagnostic:
- `lead_cutoff_hz = 11444` (near 12000 upper bound — wants to go brighter)
- `pad_gain = 4.98` (near 5.0 upper bound — wants more sub-bass)
- `kick_decay_s = 0.499` (AT 0.50 upper bound — wants longer decay)
- `reverb_room = 0.63`, `reverb_wet = 0.37` (substantially larger and wetter than baseline)
- `hihat_decay_s = 0.005` (AT lower bound — wants very short hihat)

The optimiser is running into walls on 4–6 parameters. In CMA-ES, bound-hitting is a strong
signal that the global optimum lies outside the current search space. The synthesis architecture
is constraining what the optimiser can discover.

### 1.3 CLAP's ceiling as an objective

CLAP (Wu et al., 2023, ICASSP) is trained contrastively — it learns to separate semantically
different audio but is not trained to reconstruct fine spectral detail. Key limitations for
synthesis matching:

- **Temporal resolution**: CLAP's mel spectrogram features wash out structure below ~50ms.
  Attack transients, LFO modulation, and micro-timing are under-represented in the embedding.
- **Fine harmonic detail**: Sub-cent detuning differences and specific overtone ratios are not
  preserved as they are irrelevant to the contrastive pretraining objective.
- **Flat gradient near optimum**: As synthesis quality approaches the reference, the CLAP
  similarity surface becomes flat. CMA-ES stalls because the gradient signal vanishes before
  reaching perceptually distinguishable parameter regions. This is the "last mile" problem.

The consequence: the 0.622 gate CLAP may be closer to the true CLAP ceiling for this reference
than it appears. The remaining 0.078 gap may partly reflect CLAP's limited resolution near the
optimum, not a large perceptual gap. **A perceptual evaluation (listening test) should be done
before committing to more architecture work** — see Approach 5.

---

## 2. Candidate approaches

### Approach 1: Expand the CMA-ES search space with oscillator architecture parameters

**Hypothesis**: `saw_count` and `detune_cents` are currently hardcoded in `SupersawPad`
and `SmoothLead` at SA's confirmed values (5 voices, 60 cents). The JP-8000 supersaw
(Szabo, 2010) has a specific character determined by the mix ratio between the centre
oscillator and the 6 detuned voices — our implementation uses a uniform summing, which
may not match the Roland hardware's weighting. Adding `saw_count`, `detune_cents`, and
a `centre_mix_ratio` parameter to the CMA-ES space gives the optimiser a new axis to
explore.

**What to add to OPT-003 parameter space**:
```
('saw_count_pad',     3,  9,   5)    # integer — will need to round
('detune_cents_pad',  10, 120, 60)   # SA's 0.6 semitones = 60 cents
('centre_mix_pad',    0.0, 1.0, 0.5) # uniform vs centre-heavy weighting
('saw_count_lead',    1,  7,   1)    # SmoothLead currently single-voice
('detune_cents_lead', 0,  80,  0)
```

**Risk**: `saw_count` is integer-valued; CMA-ES operates on continuous space. Round to nearest
integer at decode time — works but produces discontinuous gradients, which CMA-ES handles less
efficiently than continuous parameters. Alternatively, treat `saw_count` as a categorical
choice and run separate CMA-ES instances for each value.

**Cost**: One 500-gen CMA-ES run per architecture variant (~60 min each). Low implementation
effort — `from_params()` in `HeyAngelRenderer` needs to pass these new params to
`SupersawPad` and `SmoothLead`.

**Verdict**: High value, low cost. The most direct path to giving the optimiser new axes.
SA's confirmed pad parameters are `unison(5).detune(.6)` — matching these is necessary but
not sufficient if the centre/detuned mix ratio differs.

---

### Approach 2: Fix the SmoothLead oscillator architecture

~~**Hypothesis**: SA's lead uses `.s("supersaw").unison(3).detune(0.3)` (3 voices, 0.3
semitone spread) — a narrower, thinner supersaw than the pad. `SmoothLead` is currently
a *single* filtered sawtooth. This is a structural mismatch.~~

**RETRACTED 2026-07-11 — hypothesis was wrong.**

SA's `acid` register (the lead function) in `prebake.strudel` is:
```js
register('acid', (pat) => {
  return pat.s('supersaw')
    .detune(.5)
    .unison(1)   // ← single voice
    ...
})
```
Verified directly from `github.com/switchangel/strudel-scripts/prebake.strudel` (line 504–506),
confirmed identically in `allscripts(deprecated).js` (line 182–184).

`SmoothLead` as a *single* filtered sawtooth is **architecturally correct**. The `unison(3)`
claim originated from `spinor`, a completely different wavetable synth in the same file.
The detune value is also wrong: SA uses `detune(.5)` (50 cents), not 0.3 semitones.

One actionable finding: SA's acid lead uses `detune(.5)` — 50 cents. If `SmoothLead`'s
detune is not 50 cents, that is worth checking and correcting, but it is a single parameter
tweak, not an architectural change.

**Verdict**: Do not implement. `SmoothLead` single-oscillator architecture is confirmed correct.

---

### Approach 3: Replace SchroederReverb with a better model

**Hypothesis**: OPT-002 found `reverb_room=0.63, reverb_wet=0.37` — the optimiser is
pushing toward a much larger, wetter room than the baseline. SA's Strudel uses a custom
FDN reverb (the `SimpleFDN` in our code). The `SchroederReverb` in the outer
`HeyAngelRenderer` chain is a second reverb on top of `SupersawPad`'s own `SimpleFDN`,
creating a double-reverb that may not match SA's single-FDN architecture.

**What to investigate**:
1. Check the signal chain: does `HeyAngelRenderer` apply `SchroederReverb` to the pad after
   `SupersawPad` has already applied `SimpleFDN` internally? If yes, this is a double-reverb.
2. If double-reverb: set outer reverb wet=0 and compensate with better FDN params.
3. Measure: render pad-only with SA's Strudel debug page, compare reverb tail shape.

**Cost**: Investigation first (1–2 hours), then targeted fix. No CMA-ES run needed —
this is a structural correctness check.

**Verdict**: Investigate before OPT-003. The double-reverb suspicion is worth verifying
cheaply before burning another 4000 evals.

---

### Approach 4: Widen remaining bound-hitting parameters for OPT-003

Even without architecture changes, OPT-002 hit `kick_decay_s` AT 0.50 and showed
`reverb_room` and `reverb_wet` well above their previous ranges. A third run with wider
bounds and warm-started from OPT-002 would cost ~60 min and might yield +0.01–0.02 CLAP.

**Specific changes**:
```
('kick_decay_s',     0.05, 0.80,  0.499)   # was 0.10–0.50
('reverb_room',      0.20, 0.99,  0.631)   # was 0.20–0.90
('reverb_wet',       0.05, 0.60,  0.371)   # was 0.05–0.45
```

**Verdict**: Low effort, marginal gain. Worth doing *alongside* Approach 1 (i.e., as part
of OPT-003) but not as a standalone run. Don't burn 4000 evals for +0.015.

---

### Approach 5: Perceptual evaluation before more optimisation

**Hypothesis**: CLAP cosine is a coarse metric. The 0.078 remaining gap may not correspond
to a perceptual gap of equivalent magnitude. It's possible that the OPT-002 output already
sounds convincingly like SA's style to a human listener, and further CLAP optimisation yields
diminishing perceptual returns.

**What to do**:
- Render 30s of OPT-002 best params
- Listen back-to-back with `hey_angel_trimmed.wav`
- Write down the single most obvious perceptual difference

This is a 10-minute task with high diagnostic value. If the gap is perceptually large and
obvious (wrong reverb character, wrong lead timbre, wrong rhythmic feel), that tells you
*where* to focus architecture work. If the gap is small or subtle, the CLAP ceiling may be
a metric limitation rather than a synthesis gap — and you're closer to the acceptance bar
(BR-1: "identifiable as SA's style within 15 seconds") than the numbers suggest.

**Verdict**: Do this first, before any code changes. It costs nothing and may redirect the
entire Phase 2 roadmap.

---

### Approach 6: Alternative objective function (multi-scale spectral loss)

CLAP is a semantic similarity metric. For the "last mile" of synthesis matching, it may be
useful to supplement CLAP with a signal-level objective that measures fine spectral shape
more sensitively.

Candidates:
- **Multi-scale STFT loss** (Engel et al., ICLR 2020 DDSP; Yamamoto et al.): sum of L1
  spectral magnitude losses at multiple FFT sizes (e.g. 512, 1024, 2048, 4096). This
  captures both time resolution and frequency resolution trade-offs.
- **Mel-spectrogram cosine over 16 sub-windows**: rather than collapsing the whole 27s
  to one embedding, measure mel cosine across aligned 1.7s windows (1 bar at 140 BPM) and
  average. More sensitive to temporal structure than a single global embedding.
- **Composite objective**: `score = α·CLAP + β·mel_window_cosine + γ·mfcc_cosine`, with
  the three terms capturing different temporal scales.

**Risk**: The mel-window and multi-scale STFT approaches are computationally cheap relative
to CLAP inference (~2x total eval cost). However, they optimise toward signal-level
similarity, which may overfit to the specific reference clip rather than to SA's general
style. CLAP's semantic abstraction is actually a feature for style matching — it generalises
beyond the specific recording.

**Verdict**: Interesting but complex. Defer until after perceptual evaluation (Approach 5)
clarifies what kind of gap remains.

---

## 3. Recommended Phase 2 sequence

### Step 1 — Listen (immediate, 10 min)
Render OPT-002 params and listen back-to-back with the reference. Write down the primary
perceptual difference. This anchors all subsequent work.

### Step 2 — Investigate double-reverb (1–2 hours)
Check whether `HeyAngelRenderer.SchroederReverb` is applied after `SupersawPad.SimpleFDN`.
If double-reverb confirmed, fix structurally and re-measure with `compare_audio.py`. This
is potentially free CLAP gain with no optimisation needed.

### Step 3 — ~~Fix SmoothLead to 3-voice supersaw~~ (retracted)
~~SA's confirmed lead is `unison(3).detune(0.3)`.~~ This step is removed — see Approach 2
retraction above. `SmoothLead` single-oscillator is confirmed correct. Minor actionable:
verify `SmoothLead` uses 50 cents detune (`detune(.5)` per SA's source), not 30 cents.

### Step 4 — OPT-003: expanded search space + widened bounds
After Steps 2–3, run OPT-003 with:
- Oscillator architecture params in the search space (`saw_count`, `detune_cents`, `centre_mix`)
- Wider bounds on `kick_decay_s`, `reverb_room`, `reverb_wet`
- Warm-start from OPT-002 best

### Step 5 — If CLAP ≥ 0.70: gate check + merge
### Step 5 — If CLAP still plateaued at ~0.66: declare synthesis layer validated

If three CMA-ES runs across increasingly rich parameter spaces all plateau at 0.62–0.66,
the CLAP ceiling is likely a metric limitation for this reference/generator pair rather
than a perceptual gap. At that point, the synthesis stack is validated and the project
advances to the arrangement arc (build structure, arrangement stages, filter automation).

---

## 4. References

Davis, S. B., & Mermelstein, P. (1980). Comparison of parametric representations for
monosyllabic word recognition in continuously spoken sentences. *IEEE Transactions on
Acoustics, Speech, and Signal Processing*, 28(4), 357–366.
https://doi.org/10.1109/TASSP.1980.1163420

Engel, J., Hantrakul, L., Gu, C., & Roberts, A. (2020). DDSP: Differentiable digital
signal processing. In *International Conference on Learning Representations (ICLR 2020)*.
https://arxiv.org/abs/2001.04643

Esling, P., Chemla-Romeu-Santos, A., & Bitton, A. (2020). Generative timbre spaces with
variational audio synthesis. *Transactions of the International Society for Music
Information Retrieval (TISMIR)*. (Note: verify exact citation for the flow synthesiser work.)

Hansen, N. (2016). *The CMA evolution strategy: A tutorial*. arXiv:1604.00772.
https://arxiv.org/abs/1604.00772

Hansen, N., & Ostermeier, A. (2001). Completely derandomized self-adaptation in evolution
strategies. *Evolutionary Computation*, 9(2), 159–195.
https://doi.org/10.1162/106365601750190398

McFee, B., Raffel, C., Liang, D., Ellis, D. P. W., McVicar, M., Battenberg, E., &
Nieto, O. (2015). librosa: Audio and music signal analysis in Python. In *Proceedings
of the 14th Python in Science Conference* (pp. 18–25).
https://doi.org/10.25080/Majora-7b98e3ed-003

Szabo, A. (2010). *How to emulate a Roland JP-8000 supersaw* [Technical report].
http://www.nada.kth.se/utbildning/grukth/exjobb/rapportlistor/2010/rapporter10/szabo_adam_10131.pdf

Wu, Y., Chen, K., Zhang, T., Hui, Y., Berg-Kirkpatrick, T., & Dubnov, S. (2023).
Large-scale contrastive language-audio pretraining with feature fusion and keyword-to-caption
augmentation. In *Proceedings of ICASSP 2023*.
https://doi.org/10.1109/ICASSP49357.2023.10095969

Yee-King, M. (2011). *Automatic sound synthesiser programming: Techniques and applications*
[Doctoral dissertation, University of Sussex]. (Supervisor: Mark d'Inverno.)
