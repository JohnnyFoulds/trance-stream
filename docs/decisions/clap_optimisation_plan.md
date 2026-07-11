# Plan: Fix CLAP + Resolve Uncertainty + Full Optimisation Run

## Context

Branch: `sidequest/pluck-arp-analysis`. Goal: all four Tier-1 metrics passing simultaneously:
CLAP ≥ 0.70, centroid_ratio ∈ [0.70, 1.30], band_energy_cosine ≥ 0.85, mfcc_cosine ≥ 0.80.

Current best (EXP-016): centroid ✓, band_energy ✓, mfcc=0.794 (0.006 below), CLAP=0.527.
ALL CLAP scores EXP-000 through EXP-016 are invalid — see BLOCKING-001/002 in
`experiment_log.md`. The fixes (`enable_fusion=True`, `N_BARS=16`) are already applied to
`tools/compare_audio.py` and `tools/optimize_hey_angel.py`.

**Do NOT merge to main until all four gates pass simultaneously.**

---

## Current code state (verified by read, 2026-07-10)

| File | Relevant state |
|---|---|
| `tools/compare_audio.py:91` | `enable_fusion=True` ← already fixed this session |
| `tools/optimize_hey_angel.py:50` | `N_BARS = 16` ← already fixed this session |
| `tools/optimize_hey_angel.py:100` | `enable_fusion=True` ← already fixed this session |
| `tools/optimize_hey_angel.py:181` | `from_params(..., n_bars=4)` — default unused; optimiser always passes `n_bars=N_BARS` explicitly |
| `song/theory.py:127` | `TRANCEGATE_FLOOR = 0.3` — deliberate departure from SA's 0.7; untested assumption |
| `synth/envelopes.py:64` | `trancegate()` — already binary (on/off per slot), NOT smooth cosine |
| `instruments/pad.py:196` | reads `TRANCEGATE_FLOOR` from `song.theory` at call time; fresh process picks up file changes |

---

## Known uncertainties — resolve via spikes before committing to long runs

| # | Uncertainty | Spike | Cost |
|---|---|---|---|
| U1 | What is the valid fusion CLAP baseline for EXP-016 params? | EXP-017 render + compare_audio | ~10 min |
| U2 | How slow is fusion CLAP per eval? (affects total run time estimate) | Timed in EXP-017 dry-run | ~5 min |
| U3 | Is CLAP ≥ 0.70 achievable at all with current architecture? | 50-iter CMA-ES probe | ~30–40 min |
| U4 | Does fixing trancegate floor (0.3→0.7) move mfcc? | EXP-018 single measurement | ~10 min |

**Critical sequencing**: If U4 confirms the trancegate floor is capping mfcc, the full
500-iter CMA-ES should run AFTER the fix — otherwise we're burning 500 evals against a
known structural ceiling.

---

## Phase 1 — Spike U1 + U2: re-baseline and timing

**Step A** — time one eval and get CLAP baseline (dry-run):
```bash
python tools/optimize_hey_angel.py --dry-run
```
Records: CLAP model load time, single-eval wall-clock time (render + inference), CLAP score.

**Step B** — full four-metric measurement (compare_audio.py on 16-bar render):
```bash
python hey_angel_cover.py --bars 16 --wav /tmp/ha_EXP017.wav
python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav /tmp/ha_EXP017.wav --bpm 140.0534
```
Records: all four Tier-1 metrics under corrected CLAP.

**Record as EXP-017** in `experiment_log.md`:
- Note: "re-baseline of EXP-016 params under corrected CLAP — enable_fusion=True, 16 bars"
- centroid_ratio and band_energy_cosine should still pass (they are unaffected by the CLAP fix)
- The new CLAP value becomes the valid starting point for all subsequent work

**Decision gates after EXP-017**:
- If CLAP ≥ 0.70 AND mfcc ≥ 0.80: all gates pass → skip remaining phases, merge unblocked.
- If CLAP < 0.30: unexpected — diagnose before proceeding.
- Otherwise (expected: CLAP somewhere in [0.40, 0.70]): proceed to Phase 2.

---

## Phase 2 — Spike U4: Bug 2 trancegate floor (do BEFORE full optimiser run)

### What the bug actually is (verified in code)

The trancegate in `synth/envelopes.py:64` is already correct — it IS a binary 16-step-per-bar
gate (probabilistic on/off per slot, seeded random, P(on)=0.667). The algorithm is right.

The problem is **`TRANCEGATE_FLOOR = 0.3` in `song/theory.py:127`**.

SA's Strudel uses `.clip(.7)`: off-slots output at **0.7 amplitude** (a 30% dip).
Our code uses 0.3: off-slots output at **0.3 amplitude** (a 70% dip — more than 2× as deep).

Comment at `theory.py:127` explains the reasoning:
> `"SA uses 0.7 but 0.3 avoids FDN transients"`

This was a conservative assumption, never measured. With 16 bars = ~256 gate steps, each
off-slot drives the pad 2.3× lower than SA's version. MFCC encodes spectral envelope over
time — SA's subtle modulation (1.0→0.7→1.0) and our aggressive chop (1.0→0.3→1.0) produce
structurally different MFCC trajectories. This is a plausible explanation for the mfcc
plateau across 7 lead gain values (EXP-010 through EXP-016) with no improvement.

### Critical confound: mix balance

Raising `TRANCEGATE_FLOOR` from 0.3 to 0.7 increases the pad's average energy on off-slots
(from 0.3² to 0.7² = ~5.4× more energy in those slots). This will shift the overall mix
level and the 0–200 Hz band fraction. `band_energy_cosine` currently passes at 0.854 (just
above the 0.85 threshold). It must be monitored in EXP-018 — if it drops below 0.85, the
gain balance will need adjustment.

### Note: trancegate_floor is NOT in the CMA-ES search space

`optimize_hey_angel.py` `_SPACE` has 15 dimensions and does not include `trancegate_floor`.
This means the optimiser cannot discover the optimal floor value. Strategy: treat it as a
structural constant (spike it as EXP-018, keep it if confirmed), then run CMA-ES from
that corrected starting point. This is the right approach — the floor is an architectural
choice, not a continuous mixing parameter.

### The spike

1. Pre-specify hypothesis in `experiment_log.md` (required before any code change)
2. Change `TRANCEGATE_FLOOR = 0.3` → `0.7` in `song/theory.py:127`
3. Render 16 bars, run `compare_audio.py` with fixed CLAP, record as EXP-018:
```bash
python hey_angel_cover.py --bars 16 --wav /tmp/ha_EXP018.wav
python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav /tmp/ha_EXP018.wav --bpm 140.0534
```

**Hypothesis**: Raising `TRANCEGATE_FLOOR` from 0.3 to SA's 0.7 will increase mfcc_cosine
from the EXP-017 value by ≥ 0.01, and will not decrease band_energy_cosine below 0.85.

**Falsification**: If mfcc_cosine does not increase by ≥ 0.01 relative to EXP-017, reject
and revert to 0.3.

**Decision gates after EXP-018**:
- mfcc up ≥ 0.01 AND band_energy still ≥ 0.85: keep floor=0.7, proceed to Phase 3.
- mfcc up ≥ 0.01 BUT band_energy drops below 0.85: floor=0.7 is load-bearing for mfcc but
  breaks band energy — try intermediate floor (e.g. 0.5) as EXP-019, adjust pad gain down
  slightly to re-balance sub-bass. Then proceed to Phase 3 with corrected values.
- mfcc does not move: revert to 0.3. The mfcc ceiling is not in the trancegate floor.
  Proceed to Phase 3 — CMA-ES may find the headroom under fusion CLAP.

---

## Phase 3 — Spike U3 + Full CMA-ES optimisation

### Spike U3: 50-iter probe

Run before committing to 500 iters. Answers whether the loss landscape has useful gradient
signal from the warm-start.

```bash
python tools/optimize_hey_angel.py --iters 50 > /tmp/opt_probe.log 2>&1
tail -f /tmp/opt_probe.log
```

If CLAP does not improve at all after 50 evals: switch to `--use-scipy` (Differential
Evolution — more aggressive global exploration, different covariance structure than CMA-ES).

### Full run

**Formal problem**: θ* = argmax_θ CLAP(x_ref, G(θ)) where G is the hey_angel renderer
(non-differentiable numpy/scipy). Analysis-by-synthesis (AbS).

**Algorithm: CMA-ES** (Hansen, 2016; Hansen & Ostermeier, 2001): black-box optimiser for
10–100 continuous parameters. Adapts full covariance matrix; escapes elongated valleys.
Yee-King (2011): evolutionary strategies outperform gradient methods on synthesiser
parameter matching specifically.

**Loss function**:
```
score = CLAP(ref, gen) − max(0, 0.70 − band_energy_cosine) × 0.4
minimise −score
```
Spectral penalty prevents degenerate solutions (silence, sub-bass collapse) that accidentally
score high on CLAP.

**15-dimensional parameter space** (bounds in `tools/optimize_hey_angel.py` `_SPACE`):
`lead_cutoff_hz`, `lead_gain`, `pad_cutoff_slider`, `pad_gain`, `hihat_gain`,
`bass_cutoff_g1`, `reverb_room`, `reverb_wet`, `sidechain_depth`, `gain_kick`,
`gain_bass`, `gain_pluck`, `kick_decay_s`, `kick_pitch_floor`, `hihat_decay_s`.
All normalised to [0,1]^15.

**Warm start**: EXP-016 params (or EXP-018 values if trancegate fix was adopted).
σ₀=0.25, popsize=8, maxiter=500.

**Timing**: dry-run will give exact per-eval time (U2). Estimate: 16-bar render ~0.5s +
fusion CLAP ~4–6s → ~5–7s/eval → 500 evals ≈ 40–60 min.

```bash
python tools/optimize_hey_angel.py --iters 500 > /tmp/opt_run.log 2>&1 &
tail -f /tmp/opt_run.log
```

---

## Phase 4 — Apply best params and gate check

After optimiser completes, `best_params.json` has the best θ found.

1. Apply all 15 params to `hey_angel_cover.py` (update constants from `best_params.json`)
2. Render 16 bars, run `compare_audio.py` (fusion CLAP)
3. Record as OPT-001 in `experiment_log.md`
4. **Gate check**:
   - CLAP ≥ 0.70 ✓?
   - centroid_ratio ∈ [0.70, 1.30] ✓?
   - band_energy_cosine ≥ 0.85 ✓?
   - mfcc_cosine ≥ 0.80 ✓?

All four pass → merge unblocked.

**If still failing after optimiser + Bug 2 fix**: the gap is in oscillator architecture
(supersaw character, detune spread, saw_count), not reachable by the current parameter
space. Record as new ADR; plan Phase 2 work separately.

---

## Commit strategy

1. **Now** (CLAP fixes): `tools/compare_audio.py`, `tools/optimize_hey_angel.py`,
   `research/analysis/experiment_log.md`, `docs/decisions/clap_optimisation_plan.md`
   Message: "Fix CLAP evaluation: enable_fusion=True, N_BARS=16 — resolves BLOCKING-001/002"

2. **After EXP-017**: `research/analysis/experiment_log.md`
   Message: "EXP-017: re-baseline under corrected CLAP (fusion, 16 bars)"

3. **After EXP-018** (if trancegate fix retained): `song/theory.py`,
   `research/analysis/experiment_log.md`
   Message: "EXP-018: raise TRANCEGATE_FLOOR 0.3→0.7 to match SA's .clip(.7)"

4. **After OPT-001**: `hey_angel_cover.py`, `best_params.json`,
   `research/analysis/experiment_log.md`
   Message: "OPT-001: apply CMA-ES best params to hey_angel_cover.py"
