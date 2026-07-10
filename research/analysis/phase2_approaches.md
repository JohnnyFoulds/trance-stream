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

**Hypothesis**: `saw_count` and `detune_cents` are constructor parameters of `SupersawPad`
(`instruments/pad.py` lines 35–37) with defaults of 5 voices and 60 cents, but are never
passed through `HeyAngelRenderer.from_params()` — functionally fixed during optimisation.
The JP-8000 supersaw (Szabo, 2010) has a character partly determined by the mix ratio
between a centre oscillator and the detuned satellite voices — our implementation uses
uniform summing across all voices (normalised by `1/sqrt(N)`), which may not match the
Roland hardware's weighting. Note: the JP-8000 uses 7 voices (1 centre + 6 detuned); SA's
`unison(5)` uses 5 — `centre_mix_ratio` is therefore a hypothesis to explore, not a
confirmed SA parameter. Adding `saw_count` and `detune_cents` to the CMA-ES space gives the
optimiser new axes regardless of centre-weighting.

`SmoothLead` has no `saw_count` or `detune_cents` parameters — it is a plain single-voice
sawtooth. Do not include `saw_count_lead` or `detune_cents_lead` in OPT-003; those rows
in the proposed parameter space are inapplicable (see Approach 2 retraction).

**Source for pad parameters**: SA's `unison(5).detune(.6)` comes from `research/strudel_debug.html`
(session GWXCCBsOMSg). It does not appear in `prebake.strudel` or `allscripts(deprecated).js`,
which only contain the `acid` register using `unison(1).detune(.5)`.

**What to add to OPT-003 parameter space**:
```
('saw_count_pad',    3,  9,   5)     # integer — round at decode time
('detune_cents_pad', 10, 120, 60)    # SA's 0.6 semitones = 60 cents
('centre_mix_pad',   0.0, 1.0, 0.5) # uniform vs centre-heavy weighting (hypothesis)
```

**Risk**: `saw_count` is integer-valued; CMA-ES operates on continuous space. Round to nearest
integer at decode time — works but produces discontinuous gradients, which CMA-ES handles less
efficiently than continuous parameters. Alternatively, treat `saw_count` as a categorical
choice and run separate CMA-ES instances for each value.

**Cost**: One 500-gen CMA-ES run per architecture variant (~60 min each). Low implementation
effort — `from_params()` in `HeyAngelRenderer` needs to pass these new params to `SupersawPad`.

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

**Verdict**: Do not implement. `SmoothLead` single-oscillator architecture is confirmed correct.

Note: the "minor actionable" about verifying `SmoothLead` uses 50 cents detune is inapplicable.
`SmoothLead` has no detune parameter at all (`smooth_lead.py` lines 35–40). SA's `detune(.5)`
with `unison(1)` has no acoustic effect in Strudel either (with only 1 voice, detuning does
nothing). There is nothing to check or correct.

---

### Approach 3: Fix the double-reverb on the master bus

**Confirmed finding** (no longer a hypothesis — verified by code inspection):

`HeyAngelRenderer` applies `SchroederReverb` to the **entire master mix** at
`hey_angel_cover.py` line 400: `mix_l, mix_r = self._reverb.process(mix_l, mix_r)`.
This mix already contains pad audio that `SupersawPad.render()` has already passed through
its internal `SimpleFDN` reverb (`instruments/pad.py` line 204). Every other instrument
(kick, hi-hat, bass, melody, pluck) also receives the outer reverb.

SA's `.room(.7)` is applied only to the pad pattern (`research/strudel_debug.html` line 42).
No other SA instrument has reverb. The architectural mismatch is:

- **SA**: pad only → single Freeverb/FDN reverb
- **Ours**: all instruments → double-reverb on pad; single reverb on kick, hi-hat, bass, lead, pluck

This is a confirmed bug, not a suspicion. The optimiser compensated by pushing `reverb_room=0.63`
and `reverb_wet=0.37` — wetter and larger than SA's `.room(.7)` baseline because the objective
was trying to correct for under-reverberation of the non-pad instruments while simultaneously
over-reverberating the pad.

Note: Strudel's `.room()` uses Freeverb (a Schroeder/comb+allpass design), not a custom FDN.
`SimpleFDN` is our Python approximation — architecturally similar but not identical.

**What to fix**:
1. Remove `SchroederReverb` from `HeyAngelRenderer`'s master bus (set `reverb_wet=0` or
   remove the `_reverb.process()` call at line 400 of `hey_angel_cover.py`)
2. Tune `SupersawPad`'s `SimpleFDN` parameters to reproduce SA's `.room(.7)` tail shape
3. Re-run `compare_audio.py` gate check — no CMA-ES run needed for the structural fix itself
4. Warm-start OPT-003 from the corrected baseline

**Cost**: 1–2 hours to fix and measure. This is potentially significant free CLAP gain
because the reverb character is one of the most perceptually salient dimensions in the mix.

**Verdict**: Fix this before OPT-003. Do not burn 4000 more evals against a known
architectural bug.

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
This step is removed entirely — see Approach 2 retraction. `SmoothLead` single-oscillator
is confirmed correct. No action required.

### Step 4 — OPT-003: expanded search space + widened bounds
After Steps 2–3, run OPT-003 with:
- Pad oscillator architecture params in the search space (`saw_count_pad`, `detune_cents_pad`, `centre_mix_pad`)
- Wider bounds on `kick_decay_s`, `reverb_room`, `reverb_wet`
- Remove or zero outer `SchroederReverb` from master bus before running (Step 2)
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

---

## Appendix A: Switch Angel Strudel Functions vs Python Implementation

**Sources verified 2026-07-11:**
- `github.com/switchangel/strudel-scripts/prebake.strudel` (fetched via gh CLI)
- `github.com/switchangel/strudel-scripts/allscripts(deprecated).js` (fetched via gh CLI)
- `research/strudel_debug.html` — pad pattern from SA's YouTube session GWXCCBsOMSg
- Strudel built-in function signatures from `controls.mjs`, `pattern.mjs`, `signal.mjs`
  (fetched from strudel.cc documentation)

---

### A.1 `trancegate`

#### SA's definition (prebake.strudel, lines 288–291)

```js
register('trancegate', (density, seed, length, x) => {
  density = reify(density).add(.5)
  return x.struct(rand.mul(density).round().seg(16).rib(seed, length)).fill().clip(.7)
})
```

Earlier version in `allscripts(deprecated).js` (lines 92–94) — no `.add(.5)`:
```js
register('trancegate', (density, seed, length, x) => {
  return x.struct(rand.mul(density).round().seg(16).rib(seed, length)).fill().clip(.7)
})
```

SA's call site (strudel_debug.html, session GWXCCBsOMSg):
```js
.trancegate(1.5, 45, 1)
```

#### What it does step by step

1. `density = reify(1.5).add(.5)` → **effective density = 2.0** (current prebake)
2. `rand` — Strudel's deterministic continuous random signal (0–1), seeded by playback position
3. `rand.mul(2.0)` → uniform random values in [0, 2) per cycle
4. `.round()` → rounds to 0 (gate off) or 1 (gate on); P(on) = P(rand × 2 ≥ 0.5) = **0.75**
5. `.seg(16)` — samples the rounded signal at 16 discrete slots per cycle (one per 16th note)
6. `.rib(45, 1)` — `ribbon(offset=45, cycles=1)`: cuts a 1-cycle loop starting at cycle 45 from
   the infinite random stream. The result is the same 16-slot pattern every bar (deterministic, seeded)
7. `.struct(...)` — applies the 16-slot binary pattern as rhythmic structure to `x`
8. `.fill()` — SA custom function: stretches each on-event forward to the next on-event's onset
   (legato; fills silence between gates)
9. `.clip(.7)` — Strudel `clip`/`legato`: trims each filled event to 70% of its filled duration,
   creating a slight gap before the next onset (prevents clicks; not a floor — off-slots are silence)

**Old allscripts** (no `.add(.5)`): with density=1.5, P(on) = P(rand ≥ 0.5/1.5) = **0.667**.
The current prebake adds 0.5 to density before use, raising P(on) to 0.75.

#### Strudel built-in details used

- `rand`: deterministic continuous signal, 0–1, seeded by cycle position (`signal.mjs`)
- `segment`/`seg(n)`: samples a continuous signal at `n` events per cycle (`pattern.mjs`)
- `ribbon`/`rib(offset, cycles)`: loops a `cycles`-length segment of the time ribbon starting
  at `offset` — equivalent to `n.early(offset).restart(pure(1).slow(cycles))` (`pattern.mjs`)
- `struct(binary)`: applies a rhythmic gate pattern, keeping events where the binary is truthy
- `clip`/`legato(factor)`: multiplies event duration by `factor`; at 0.7 = 70% of filled length
- `fill`: SA custom register — extends each event to the next onset (legato fill, not built-in Strudel)

#### Our Python equivalent

`synth/envelopes.py`, `trancegate()`, lines 64–105; constants in `song/theory.py` lines 126–128:

```python
TRANCEGATE_DENSITY = 0.667   # P(slot on)
TRANCEGATE_FLOOR   = 0.7     # amplitude when gate is "off"
TRANCEGATE_SEED    = 45
```

Implementation: per-bar RNG seeded by `seed + bar_index`, 16 slots, each slot either
`1.0` (on) or `TRANCEGATE_FLOOR` (off). Pattern tiled and sliced to sample count.

#### Match quality: APPROXIMATE

| Dimension | SA (current prebake) | SA (old allscripts) | Our Python |
|---|---|---|---|
| P(slot on) | **0.75** (density+0.5=2.0) | 0.667 | 0.667 — matches old version only |
| Off-state amplitude | **0** (true silence) | 0 | `TRANCEGATE_FLOOR=0.7` — never silent |
| On-state amplitude | ≤ 0.7 (`.clip(.7)` trims duration, no amplitude cap) | ≤ 1.0 | 1.0 |
| Legato fill | `.fill()` extends events to next onset | same | Hard rectangular 16th-note slots |
| Reseed per bar | `.rib(45,1)` — same pattern every bar | same | `seed + bar_index` — changes every bar |
| Slot count | 16 | 16 | 16 ✓ |
| Seed | 45 | 45 | 45 ✓ |

**Primary gaps:**
- `TRANCEGATE_FLOOR=0.7` is inverted from SA's logic. SA's off-slot is **silence**; we keep
  a 0.7 floor. This means our pad never fully ducks between gate events — a continuous drone
  rather than a rhythmically gated sound.
- P(on)=0.667 matches the old allscripts formula, not the current prebake (0.75).
- `.fill()` legato: in SA, a run of consecutive on-slots sounds as a held note; in our
  rectangular implementation each slot is independent with a hard edge at the slot boundary.

---

### A.2 `rlpf`

#### SA's definition (prebake.strudel, line 397; identical in allscripts line 141)

```js
register('rlpf', (x, pat) => { return pat.lpf(pure(x).mul(12).pow(4)) })
```

#### What it does

Maps slider `x ∈ [0, 1]` to LP cutoff Hz: `cutoff_hz = (x × 12)^4`

| Slider | Hz |
|---|----|
| 0.25 | 20 |
| 0.45 | 265 |
| 0.50 | 1296 |
| 0.593 | 2563 |
| 0.70 | 7056 |
| 0.877 | 12267 |

#### Our Python equivalent (`song/theory.py`, lines 21–26)

```python
def rlpf_to_hz(slider: float) -> float:
    return (slider * 12.0) ** 4
```

#### Match quality: **EXACT**

---

### A.3 `acidenv`

#### SA's definition (prebake.strudel, lines 16–19)

```js
register('acidenv', (x, pat) => pat.lpf(100)
  .lpenv(x * 9).lps(.2).lpd(.12).lpq(2)
)
```

Earlier version in allscripts (line 176):
```js
register('acidenv', (x, pat) => pat.rlpf(.25).lpenv(x * 9).lps(.2).lpd(.15))
```

SA's typical call: `.acidenv(trancearp(...))` passing values ~0.4–0.7.

#### What it does

Sets up a Strudel LP filter envelope. At `x=0.55`:

| Parameter | Strudel call | Value | Meaning |
|---|---|---|---|
| Base cutoff | `lpf(100)` | 100 Hz | Floor frequency (absolute) |
| Envelope depth | `lpenv(0.55 × 9 = 4.95)` | 4.95 | Depth scalar applied to ADSR envelope |
| Sustain level | `lps(0.2)` | 20% of peak | Filter held at 20% of peak modulation after decay |
| Decay time | `lpd(0.12)` | 120 ms | Time from peak cutoff to sustain level |
| Resonance Q | `lpq(2)` | Q = 2 | Moderate resonance (prebake); absent in allscripts |

**LP envelope signal path (Strudel built-ins):**
- Attack: cutoff rises from 100 Hz to `100 + lpenv_depth × (peak)` on note onset
- Decay: falls over 120 ms to sustain level = `100 + 0.2 × lpenv_depth × (peak)`
- Sustain: held there while note is active
- Release: returns to 100 Hz on note off

#### Our Python equivalent

`synth/envelopes.py` `acidenv()` lines 11–37; applied in `instruments/lead.py` lines 169–185.

```python
# attack 3ms linear, then exponential decay
tau = 0.08 * (0.3 + amount * 1.4)   # at amount=0.55: tau≈86ms
env = exp(-t_decay / tau)
```

Base cutoff in lead: `base_hz = cutoff_hz * 0.60` (≈ 1537 Hz at slider=0.593).
Q = 2.0 (lead), 2.5 (bass).

#### Match quality: CLOSE with notable gaps

| Dimension | SA (prebake) | Our Python | Match? |
|---|---|---|---|
| Decay time | 120 ms (`lpd(.12)`) | ~86 ms (`tau≈0.086s`) | **MISMATCH** — 30% shorter |
| Sustain level | 20% of peak (`lps(.2)`) | Decays toward 0 (no sustain) | **GAP** — SA holds filter open after decay |
| Base cutoff floor | 100 Hz absolute | Lead: ~1537 Hz (60% of slider cutoff) | **MISMATCH** — lead floor ~15× too high |
| Resonance Q | 2 | Lead: 2.0, Bass: 2.5 | Lead: ✓ EXACT |
| Envelope depth | `x × 9` octaves | Modulates from base to cutoff_hz | APPROXIMATE |

**Primary gaps:**
- Lead base cutoff: SA floors at absolute 100 Hz; our lead floors at ~1537 Hz (slider=0.593).
  SA's filter sweeps over a 32× range (100→3200 Hz at x=0.55); ours sweeps over ~1.7× (1537→2563 Hz).
  The acid envelope "scream" comes from this extreme sweep ratio. Our lead is far more closed.
- `lps(0.2)` sustain: our filter decays to near zero; SA's holds at 20% above base. For sustained
  acid lines this creates a continuously partially-open timbre vs our hard-closed between notes.

---

### A.4 `acid` register (the lead/bass preset)

#### SA's definition (prebake.strudel, lines 503–510; identical in allscripts lines 181–188)

```js
register('acid', (pat) => {
  return pat.s('supersaw')
    .detune(.5)
    .unison(1)
    .lpf(100)
    .lpsustain(0.2).lpd(.2).lpenv(2)
    .lpq(12)
})
```

#### What it does

A full TB-303-style chain applied to any note pattern:

| Parameter | Value | Meaning |
|---|---|---|
| `s('supersaw')` | — | Supersaw oscillator (AudioWorklet) |
| `.detune(.5)` | 0.5 semitones | Frequency spread — **no effect** with `unison(1)` |
| `.unison(1)` | 1 voice | Single oscillator (no stacking) |
| `.lpf(100)` | 100 Hz | LP base cutoff |
| `.lpsustain(0.2)` | 20% | LP envelope sustain level (after decay) |
| `.lpd(.2)` | 200 ms | LP envelope decay time |
| `.lpenv(2)` | 2 octaves | LP envelope depth: peak at 100 × 2² = 400 Hz |
| `.lpq(12)` | Q = 12 | **High resonance** — classic acid squeal |

Note: `lpenv(2)` = 2 octave scalar. Strudel's lpenv is a depth multiplier on the ADSR
envelope shape, not a direct frequency offset. Peak cutoff ≈ `base × 2^lpenv` = `100 × 4` = 400 Hz.

#### Our Python equivalent

`instruments/lead.py` `AcidLead`, character preset `'acid'`:
```python
_CHARACTERS = {
    'acid': (saw_count=3, detune_cents=30, decay_s=0.08, delay_wet=0.7, slider=0.593)
}
```

#### Match quality: MISMATCH

| Dimension | SA `acid` register | Our AcidLead 'acid' |
|---|---|---|
| Voice count | `unison(1)` = **1 voice** | `saw_count=3` = 3 voices |
| Detune spread | 0.5 semitones (no effect at unison=1) | 30 cents (3 voices) |
| Base cutoff | `lpf(100)` = 100 Hz | `base_hz = cutoff * 0.60` ≈ 1537 Hz |
| LP Q | `lpq(12)` | Q = 2.0 |
| LP decay | `lpd(.2)` = 200 ms | `decay_s=0.08` = 80 ms |
| LP sustain | `lps(0.2)` = 20% | None |
| LP depth | `lpenv(2)` = 2 octaves (100→400 Hz) | cutoff sweep ~1.7× (1537→2563 Hz) |

**Primary gaps:**
- **Q=12 is the defining characteristic of the acid sound.** Our Q=2 produces a mellow filtered
  saw; SA's Q=12 produces the resonant "scream" peak at the cutoff. This is the largest single
  timbral mismatch in the lead/bass.
- Our AcidLead uses 3 voices; SA uses 1. The 3-voice width and chorus are not present in SA's
  acid register. (SA may stack voices at the call site, but the register itself is single-voice.)
- The base cutoff floor is 15× too high, collapsing the usable sweep range.

---

### A.5 Pad supersaw chain

#### SA's code (strudel_debug.html, lines 38–43; session GWXCCBsOMSg)

```js
n("0").add(-14).scale("g:minor")
  .s("supersaw").unison(5).detune(.6)
  .trancegate(1.5, 45, 1)
  .rlpf(0.5)
  .lpenv(2)
  .room(.7)
  .o(2)
```

Note: this pattern does **not** appear in `prebake.strudel` or `allscripts(deprecated).js`.
It is from SA's live session source, captured in the debug page.

#### What it does

| Step | Call | Effect |
|---|---|---|
| 1 | `n("0").add(-14).scale("g:minor")` | Root note of G minor, −14 semitones → G1 ≈ 48 Hz |
| 2 | `.s("supersaw").unison(5).detune(.6)` | 5-voice supersaw, 0.6 semitone total spread |
| 3 | `.trancegate(1.5, 45, 1)` | Probabilistic gate (see §A.1), density=1.5, seed=45 |
| 4 | `.rlpf(0.5)` | LP cutoff = (0.5×12)^4 = **1296 Hz** |
| 5 | `.lpenv(2)` | LP envelope depth: 2 octaves; peak = 1296 × 4 = **5184 Hz** |
| 6 | `.room(.7)` | Freeverb reverb, room send level 0.7 |
| 7 | `.o(2)` | Route to orbit 2 (for sidechain duck target) |

**Signal chain order:** oscillator → trancegate → LP filter+env → reverb

**Supersaw implementation (Strudel AudioWorklet):**
- `unison(5)` = 5 voices, stereo-spread by `spread` parameter (default 0.6)
- `detune(.6)` = 0.6 semitones total spread passed as `freqspread` to the worklet
- Per-voice gain: `1/sqrt(5)` normalisation (so 5 voices ≈ same loudness as 1)
- Panning: voices distributed across stereo field; alternating L/R bias

#### Our Python equivalent

`instruments/pad.py` `SupersawPad`, with signal chain:
`supersaw` → `lpenv/LPF` → `trancegate` → `SimpleFDN reverb`

#### Match quality: CLOSE with structural deviations

| Dimension | SA | Our Python | Match? |
|---|---|---|---|
| Voice count | `unison(5)` | `saw_count=5` | ✓ EXACT |
| Detune spread | `.detune(.6)` = 0.6 semitones | `detune_cents=60` | ✓ EXACT |
| Note root | `add(-14)` → G1 ≈ 48 Hz | `PAD_VOICING_OFFSETS` includes −14 | ✓ EXACT |
| LP base cutoff | `rlpf(0.5)` = 1296 Hz | `rlpf_to_hz(0.5)` = 1296 Hz | ✓ EXACT |
| LP env depth | `lpenv(2)` = 2 octaves (4×) → 5184 Hz peak | `peak_hz = cutoff * 2.83` = 1.5 oct → 3670 Hz | **MISMATCH** — 0.5 octave short |
| LP env decay | Strudel default ~300 ms | `decay_s=0.80 s` | **MISMATCH** — 2.7× too long |
| Reverb | `.room(.7)` Freeverb (pad only) | `SimpleFDN(room_size=0.7)` + outer `SchroederReverb` on master | **BUG** — double reverb (see Approach 3) |
| Signal chain order | gate → LP filter → reverb | LP filter → gate → reverb | **MISMATCH** — SA filters after gating |
| Sub-bass doubling | `add(-14)` only | `[0, −14, −21]` — extra −21 voice | **ADDITION** — −21 has no SA equivalent |

---

### A.6 Sidechain ducking

#### SA's usage (from session analysis and `docs/music_theory/02_sa_vocabulary_codified.md`)

```js
.duck("3:4:5").duckattack(0.16).duckdepth(0.6)
```

Applied to the pad pattern; the kick is on orbits 3/4/5.

#### Strudel built-in behaviour (from `controls.mjs`)

- `duck(orbit)` / `duckorbit(orbit)` — the pattern calling `.duck()` is the **trigger source**;
  the named orbits have their amplitude ducked on each trigger onset
- `duckdepth(d)` — duck amount 0–1; at 0.6, gain drops from 1.0 to 0.4 (−8 dB)
- `duckattack(t)` — **recovery time** in seconds (confusingly named; this is the release/return-to-unity,
  not the compressor's attack onset). Duck is instantaneous on trigger; recovery takes `t` seconds

#### Our Python equivalent

`synth/effects.py` `Sidechain` class, lines 271–329. One-pole IIR follower on the kick signal,
applied to pad + bass + lead simultaneously from shared state.

```python
SIDECHAIN_DEPTH    = 0.6    # gain floor = 1 - 0.6 = 0.4
SIDECHAIN_ATTACK_S = 0.16   # recovery time constant
```

#### Match quality: CLOSE

| Dimension | SA | Our Python | Match? |
|---|---|---|---|
| Depth | 0.6 | 0.6 | ✓ EXACT |
| Recovery time | 0.16 s | 0.16 s | ✓ EXACT |
| Gain floor | 0.4 | 0.4 | ✓ EXACT |
| Duck onset | Instantaneous on trigger | Instantaneous (rectified kick amplitude) | ✓ CLOSE |
| Applied to | Pad only | Pad + bass + lead (shared state) | APPROXIMATE |

---

### A.7 `noisehat`

#### SA's definition (prebake.strudel, line 953)

```js
registerFunc('noisehat', (seg = 16, modu = tri, speed = 4, min = .05, max = .12) =>
  s('white').seg(seg).dec(modu.fast(4).range(min, max))
)
```

#### What it does

- `s('white')` — white noise oscillator (full spectrum, no filtering)
- `.seg(16)` — retriggered 16 times per cycle (every 16th note)
- `.dec(modu.fast(4).range(.05, .12))` — amplitude decay time modulated by a triangle LFO
  (`tri`) running at `speed=4` cycles per bar, sweeping between 50 ms and 120 ms
- The triangle LFO creates alternating short and long decays: the hi-hat breathes rhythmically
- **No high-pass filter** — raw white noise is the intended sound

#### Our Python equivalent

`synth/drums.py` `hihat()` lines 106–135:

```python
noise    = rng.standard_normal(n_samples)
filtered = _butter_filter(noise, cutoff_hz=6000.0, btype="high", order=2)
amp      = np.exp(-t / decay_s)   # fixed decay_s per call
```

#### Match quality: MISMATCH

| Dimension | SA `noisehat` | Our Python | Match? |
|---|---|---|---|
| Spectral shape | Raw white noise (no filter) | 6 kHz high-pass filtered | **MISMATCH** |
| Decay modulation | Triangle LFO 50–120 ms per hit | Fixed `decay_s=0.08` per hit | **MISMATCH** |
| Decay range | 50–120 ms | Constants defined (50–120 ms) but LFO not implemented | PARTIAL |

**To match SA exactly:** remove the 6 kHz HPF; implement triangle LFO varying `decay_s`
between 0.05–0.12 s at 4 cycles per bar (alternating ~9.3 Hz at 140 BPM).

---

### A.8 Kick (`bd`)

#### SA's usage (session scripts)

```js
s("bd:2!4").bank("RolandTR909").dec(.3)
// syncopated variant:
s("bd").n("[0 4 8 11 14]")
```

SA uses **TR-909 sample playback** — no synthesis. `dec(.3)` = 30% of sample length (~120–300 ms
depending on the BD sample variant). Our no-sample constraint requires synthesis.

#### Our Python equivalent

`synth/drums.py` `kick()` lines 61–103: sine sweep + noise click, constants fitted to
TR-909 zero-crossing measurements.

#### Match quality: APPROXIMATE (synthesis approximation of sample)

| Dimension | SA (TR-909 sample) | Our Python | Match? |
|---|---|---|---|
| Pitch start | ~285 Hz (measured) | 285 Hz | ✓ EXACT (fitted) |
| Pitch end | ~50 Hz (measured) | `pitch_floor=50.0` Hz | ✓ EXACT (fitted) |
| Pitch sweep τ | 31 ms (measured) | `pitch_decay=0.031` | ✓ EXACT (fitted) |
| Amplitude decay | ~120–300 ms | `decay_s=0.12` = 120 ms | CLOSE |
| Harmonic content | TR-909 circuit character above 300 Hz | Sine fundamental only | APPROXIMATE |
| Rhythm pattern | Steps `[0,4,8,11,14]` | `KICK_STEPS_SYNCOPATED` = same | ✓ EXACT |

---

### A.9 Strudel built-in reference summary

This table summarises the Strudel built-in functions SA uses, for quick reference when
reading her patterns or comparing against our Python implementation.

| Function | Alias | Type | Parameter(s) | Notes |
|---|---|---|---|---|
| `lpf` | `cutoff`, `ctf`, `lp` | Audio | Hz, 0–20000 | LP filter cutoff |
| `lpq` | `resonance` | Audio | 0–50 | LP filter Q/resonance |
| `lpenv` | `lpe` | Audio | depth scalar | LP envelope depth; negative inverts sweep |
| `lpattack` | `lpa` | Audio | seconds | LP envelope attack time |
| `lpdecay` | `lpd` | Audio | seconds | LP envelope decay time |
| `lpsustain` | `lps` | Audio | 0–1 | LP envelope sustain level |
| `lprelease` | `lpr` | Audio | seconds | LP envelope release time |
| `decay` | `dec` | Audio | seconds | Amplitude envelope decay time |
| `room` | — | Audio | 0–1 wet level | Reverb send to Freeverb |
| `roomsize` | `rsize`, `sz` | Audio | 0–10 | Reverb IR room size (expensive to change) |
| `unison` | — | Synth | integer 1–100 (def. 5) | Voice count for supersaw |
| `detune` | `det` | Synth | semitones (def. 0.18) | Frequency spread across voices |
| `spread` | — | Synth | 0–1 (def. 0.6) | Stereo pan spread across voices |
| `segment` | `seg` | Pattern | events/cycle | Discretise continuous signal to N steps/cycle |
| `struct` | — | Pattern | binary pattern | Gate a pattern by rhythmic structure |
| `ribbon` | `rib` | Pattern | offset, cycles | Deterministic loop of `cycles` length starting at `offset` |
| `fill` | — | Pattern (SA custom) | none | Extend events to fill gaps (legato) — not a Strudel built-in |
| `clip` | `legato` | Audio | ≥ 0 multiplier | Scale event duration; values <1 = staccato |
| `duck`/`duckorbit` | `duck` | Audio | orbit number(s) | Sidechain trigger source |
| `duckdepth` | — | Audio | 0–1 | Sidechain duck amount at trigger |
| `duckattack` | `duckatt`, `datt` | Audio | seconds | Sidechain **recovery** time (not onset — duck is instantaneous) |
| `rand` | — | Signal | continuous 0–1 | Deterministic pseudo-random, seeded by playback position |

---

### A.10 Priority gaps for perceptual improvement (ranked by estimated audibility)

Based on the comparisons above, the following gaps are most likely to affect the CLAP score
and listener perception, ranked roughly by estimated audibility:

1. **Trancegate off-state is silence in SA; our floor=0.7 is near-continuous.**
   SA: off-slot → 0 (silence). Ours: off-slot → 0.7. The pad never fully quiets between gate
   events. Fix: set `TRANCEGATE_FLOOR = 0.0` and adjust gain compensation if needed.

2. **Double reverb on master bus** (Approach 3 — confirmed bug).
   Every instrument receives `SchroederReverb`; SA only applies `.room(.7)` to the pad.
   Fix: remove outer `SchroederReverb` from `HeyAngelRenderer`; tune `SimpleFDN` in pad.

3. **Pad lpenv depth: 1.5 octaves vs SA's 2 octaves.**
   Peak cutoff: ours 3670 Hz vs SA's 5184 Hz. Fix: `peak_hz = cutoff_hz * 4.0`.

4. **Pad lpenv decay: 800 ms vs SA's ~300 ms.**
   Our filter swell is 2.7× too slow. Fix: `decay_s = 0.30`.

5. **Lead/bass acidenv base floor: ~1537 Hz vs SA's 100 Hz.**
   SA sweeps the filter over a 32× range; ours sweeps ~1.7×. This is the acid envelope
   character gap. Fix: `base_hz = 100.0` in `instruments/lead.py`.

6. **Acid Q=2 vs SA's Q=12.**
   Q=12 creates the acid resonant peak ("squeal"). Our Q=2 is a mellow soft filter.
   Fix: increase Q in `instruments/lead.py` and `instruments/bass.py`.

7. **Hi-hat: SA uses raw white noise; we add a 6 kHz HPF.**
   SA's hat is full-spectrum white noise with variable decay. Fix: remove HPF; add triangle
   LFO decay modulation [0.05, 0.12 s] at 4 cycles/bar.

8. **Pad signal chain order: SA gates before LP filtering; we filter before gating.**
   SA: trancegate → rlpf → lpenv → room. Ours: lpenv → rlpf → trancegate → reverb.
   The difference: SA's gate edge passes through the filter and is softened; ours passes
   raw gate edges directly into reverb.

9. **Trancegate P(on): 0.667 (old allscripts) vs SA's 0.75 (current prebake).**
   Minor rhythmic density difference. Fix: `TRANCEGATE_DENSITY = 0.75`.
