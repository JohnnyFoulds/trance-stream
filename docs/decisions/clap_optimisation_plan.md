# Plan: Fix CLAP + Resolve Uncertainty + Full Optimisation Run

## Context

We are on branch `sidequest/pluck-arp-analysis`. Goal: all four Tier-1 metrics passing
simultaneously: CLAP ≥ 0.70, centroid_ratio ∈ [0.70, 1.30], band_energy_cosine ≥ 0.85,
mfcc_cosine ≥ 0.80.

Current best (EXP-016): centroid ✓, band_energy ✓, mfcc=0.794 (0.006 below), CLAP=0.527.
But ALL CLAP scores EXP-000 through EXP-016 are invalid — see BLOCKING-001/002 in
`experiment_log.md`. The fixes (`enable_fusion=True`, `N_BARS=16`) are already applied.

**Do NOT merge to main until all four gates pass simultaneously.**

---

## Known uncertainties — resolve via spikes before committing to long runs

Four things we do not yet know that will materially change the execution path:

| # | Uncertainty | Spike | Cost |
|---|---|---|---|
| U1 | What does fusion CLAP actually score on EXP-016 params? | EXP-017 dry-run | ~5 min |
| U2 | How slow is fusion CLAP per eval? (determines total run time) | Time one eval in dry-run | ~5 min (same run as U1) |
| U3 | Is CLAP ≥ 0.70 achievable at all with current architecture? | 50-iter CMA-ES probe | ~30 min |
| U4 | Does fixing Bug 2 (trancegate shape) move mfcc? | Implement + one measurement | ~1 hour |

**Critical sequencing decision**: If U4 resolves as YES (Bug 2 fixes mfcc), the full
500-iter CMA-ES should run AFTER the bug fix, not before. Running 500 evals against a
known architectural ceiling is wasteful. Spikes U1/U2 and U3 can proceed in parallel with
U4 investigation.

---

## Phase 1 — Apply fixes + Spike U1 + U2: re-baseline and timing

**CLAP fixes already applied** (this session):
- `tools/compare_audio.py` line 91: `enable_fusion=True`
- `tools/optimize_hey_angel.py` line ~100: `enable_fusion=True`
- `tools/optimize_hey_angel.py` N_BARS: `16`

**Run**:
```bash
python tools/optimize_hey_angel.py --dry-run
```

This resolves U1 (new valid CLAP baseline) and U2 (timing per eval).

**Record as EXP-017** in `experiment_log.md`:
- All four Tier-1 metrics under corrected CLAP (fusion, 16 bars)
- Timing per eval (CLAP load time + inference time)

**Decision gates after EXP-017**:
- If CLAP ≥ 0.70 AND mfcc ≥ 0.80: all gates pass → merge is unblocked, skip remaining phases.
- If CLAP < 0.30: something unexpected — diagnose before proceeding.
- Otherwise (expected: CLAP in [0.40, 0.70]): proceed to Phase 2.

---

## Phase 2 — Spike U4: Bug 2 trancegate floor (do this BEFORE full optimiser run)

**Why first**: The mfcc plateau at 0.794 across EXP-010 through EXP-016 (7 different lead
gain values, no improvement) is not a parameter tuning problem. It is an amplitude envelope
character mismatch in the trancegate. CLAP and MFCC are correlated — if the trancegate is
capping mfcc, it is also capping CLAP. Running 500 CMA-ES evals against this ceiling wastes
the run.

**The bug**: The trancegate is already correctly implemented as a binary 16-step-per-bar
gate in `synth/envelopes.py` — this part is right. The problem is the **floor value**.

SA's Strudel code uses `.clip(.7)` on off-slots: the pad amplitude oscillates between
**1.0** (on) and **0.7** (off) — a gentle 30% dip per off-step.

Our implementation uses `TRANCEGATE_FLOOR = 0.3` in `song/theory.py:127` — the pad drops
to **0.3** on off-steps, a 70% dip, more than twice as aggressive.

The comment at line 127 explains why: `"SA uses 0.7 but 0.3 avoids FDN transients"`. This
was a conservative choice made to prevent the hard gate from causing artifacts in the FDN
reverb. That concern was never measured — it was just assumed.

**MFCC consequence**: MFCC coefficients encode the spectral envelope shape over time.
SA's pad has subtle rhythmic modulation (1.0 → 0.7 → 1.0). Ours has dramatic choppy cuts
(1.0 → 0.3 → 1.0). These produce structurally different MFCC trajectories regardless of
spectral content. The reference embedding reflects the subtle modulation; ours reflects
the aggressive one.

**The spike**:
1. Pre-specify hypothesis in `experiment_log.md` (required before touching code)
2. Change `TRANCEGATE_FLOOR = 0.3` → `0.7` in `song/theory.py:127`
3. Render 16 bars, run `compare_audio.py` with fixed CLAP
4. Record as EXP-018
5. Listen to the output for FDN transient artifacts (the original concern)

**Hypothesis to pre-specify**: Raising `TRANCEGATE_FLOOR` from 0.3 to SA's 0.7 will
increase mfcc_cosine from the EXP-017 value by ≥ 0.01, and increase CLAP_cosine, without
materially decreasing band_energy_cosine or centroid_ratio.

**Falsification criterion**: If mfcc_cosine does not increase by ≥ 0.01 relative to
EXP-017, the hypothesis is rejected and the floor is reverted to 0.3.

**Decision gate after EXP-018**:
- If mfcc increases ≥ 0.01 and no audible FDN artifacts: fix confirmed. Keep floor=0.7,
  proceed to Phase 3 from this better starting point.
- If mfcc increases but audible FDN artifacts appear: the FDN concern was real. Set floor
  to an intermediate value (e.g. 0.5) and re-test as EXP-019 before Phase 3.
- If mfcc does not move: revert to 0.3. The mfcc ceiling is elsewhere. Proceed to Phase 3
  and let CMA-ES explore — the ceiling may be higher than we think under fusion CLAP.

---

## Phase 3 — Spike U3 + Full CMA-ES optimisation

### Spike U3: 50-iter probe (runs fast, answers whether the objective is alive)

```bash
python tools/optimize_hey_angel.py --iters 50 > /tmp/opt_probe.log 2>&1
```

Watch for monotonically increasing "new best" lines. If CLAP is not moving after 50 evals
(all scores within ±0.01 of starting point), the loss landscape is flat or the warm-start
is already at a local optimum — switch to `--use-scipy` (Differential Evolution) which
explores more aggressively.

### Full run (launch only after probe shows improvement is possible)

**Formal problem**: θ* = argmax_θ CLAP(x_ref, G(θ)) where G is the hey_angel renderer
(non-differentiable numpy/scipy). This is analysis-by-synthesis (AbS).

**Algorithm: CMA-ES** (Hansen, 2016; Hansen & Ostermeier, 2001): de facto standard for
black-box optimisation of 10–100 continuous parameters. Adapts a full covariance matrix
over the search distribution. Yee-King (2011) showed evolutionary strategies outperform
gradient methods on synthesiser parameter matching.

**Loss function**:
```
score = CLAP(ref, gen) − max(0, 0.70 − band_energy_cosine) × 0.4
CMA-ES minimises −score
```
The spectral penalty prevents degenerate solutions that achieve high CLAP by accident
(e.g. sub-bass collapse or silence).

**15-dimensional parameter space** (full bounds in `tools/optimize_hey_angel.py` `_SPACE`):
lead_cutoff_hz, lead_gain, pad_cutoff_slider, pad_gain, hihat_gain, bass_cutoff_g1,
reverb_room, reverb_wet, sidechain_depth, gain_kick, gain_bass, gain_pluck, kick_decay_s,
kick_pitch_floor, hihat_decay_s. All normalised to [0,1]^15.

**Configuration**: warm-start from EXP-016 (or EXP-018 if Bug 2 was fixed), σ₀=0.25,
popsize=8, maxiter=500.

**Timing estimate**: 16-bar render ≈ 0.5s + fusion CLAP inference ≈ 4–6s (to be confirmed
by EXP-017 timing) → ~5–7s/eval → 500 evals ≈ 40–60 min.

```bash
python tools/optimize_hey_angel.py --iters 500 > /tmp/opt_run.log 2>&1 &
tail -f /tmp/opt_run.log
```

Fallback if CMA-ES stalls: `--use-scipy` (Differential Evolution — different search
dynamics, more aggressive global exploration, useful if CMA-ES is stuck in a valley).

---

## Phase 4 — Apply best params and gate check

After optimiser completes, `best_params.json` contains the best θ found.

1. Apply params to `hey_angel_cover.py`
2. Render 16 bars, run `compare_audio.py` (fusion CLAP)
3. Record as OPT-001 in `experiment_log.md`
4. **Gate check** (all must pass simultaneously):
   - CLAP ≥ 0.70 ✓?
   - centroid_ratio ∈ [0.70, 1.30] ✓?
   - band_energy_cosine ≥ 0.85 ✓?
   - mfcc_cosine ≥ 0.80 ✓?

**If all pass** → merge `sidequest/pluck-arp-analysis` to main is unblocked.

**If CLAP or mfcc still fails** after optimiser + Bug 2 fix: the remaining gap is in
oscillator type (supersaw vs. the actual SA oscillator stack). This is Phase 2 work
(oscillator architecture), not parameter tuning. Record as a new ADR and plan separately.

---

## Commit strategy

1. **Now**: "Fix CLAP evaluation: enable_fusion=True, N_BARS=16 — resolves BLOCKING-001/002"
   - `tools/compare_audio.py`, `tools/optimize_hey_angel.py`, `research/analysis/experiment_log.md`
2. **After EXP-017**: "EXP-017: re-baseline under corrected CLAP (fusion, 16 bars)"
   - `research/analysis/experiment_log.md`
3. **After EXP-018** (if trancegate fix retained): "EXP-018: binary trancegate — Bug 2 fix"
   - `instruments/pad.py`, `research/analysis/experiment_log.md`
4. **After OPT-001**: "OPT-001: apply CMA-ES best params to hey_angel_cover.py"
   - `hey_angel_cover.py`, `best_params.json`, `research/analysis/experiment_log.md`
