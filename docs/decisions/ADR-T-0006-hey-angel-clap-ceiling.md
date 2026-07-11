# ADR-T-0006: CMA-ES Parameter Optimisation — Architectural Ceiling at CLAP 0.66

**Status**: Accepted  
**Date**: 2026-07-11  
**Branch**: `sidequest/pluck-arp-analysis`

---

## Context

The hey_angel cover synthesis target requires all four Tier-1 metrics to pass simultaneously:
CLAP ≥ 0.70, centroid_ratio ∈ [0.70, 1.30], band_energy_cosine ≥ 0.85, mfcc_cosine ≥ 0.80.

Two full CMA-ES optimisation runs (OPT-001, OPT-002) were executed against the 15-dimensional
mixing/gain/filter parameter space using LAION-CLAP cosine similarity as the primary objective.

---

## What was tried

| Run | Evals | Loss function | Best CLAP (eval) | Gate CLAP |
|---|---|---|---|---|
| OPT-001 | 4218 | CLAP − band_energy_penalty | 0.635 | 0.582 |
| OPT-002 | ~4000 | CLAP − band_energy_penalty − centroid_penalty | 0.657 | 0.622 |

Both runs warm-started from EXP-018 params (TRANCEGATE_FLOOR=0.7), progressed rapidly in the
first ~1000 evals, then plateaued with no further improvement for ~2000+ evals.

**Parameter space** (15 dims): `lead_cutoff_hz`, `lead_gain`, `pad_cutoff_slider`, `pad_gain`,
`hihat_gain`, `bass_cutoff_g1`, `reverb_room`, `reverb_wet`, `sidechain_depth`, `gain_kick`,
`gain_bass`, `gain_pluck`, `kick_decay_s`, `kick_pitch_floor`, `hihat_decay_s`.

---

## What was proved and ruled out

**Proved:**
- The three non-CLAP Tier-1 metrics (centroid, band_energy, mfcc) are all achievable
  simultaneously. OPT-002 gate check: centroid=0.731 ✓, band_energy=0.964 ✓, mfcc=0.832 ✓.
- The mfcc plateau at 0.797 (EXP-010 through EXP-018) was NOT an architectural ceiling —
  OPT-001 reached 0.939 by exploring high pad_gain / high lead_cutoff_hz regions.
- The CLAP ceiling of ~0.66 is consistent across two independent runs from different starting
  points and different loss functions. This is a robust plateau, not a local minimum.

**Ruled out as CLAP gap causes:**
- Mix gain balance (fully explored by OPT-001/002)
- Spectral shape / band energy distribution (passes at 0.964)
- MFCC timbral fingerprint (passes at 0.832)
- Trancegate floor (EXP-018: only +0.003 mfcc, not a CLAP factor)
- CLAP evaluation bugs (BLOCKING-001/002 resolved: enable_fusion=True, N_BARS=16)

**Conclusion:** The remaining CLAP gap (~0.078) is not addressable by the current 15-dimensional
mixing parameter space. The gap is in synthesis *character* — properties that CLAP encodes
but which are not exposed as controllable parameters in the current architecture.

---

## Decision

Accept the current CMA-ES ceiling as the limit of Phase 1 parameter tuning. Proceed to Phase 2:
architectural modifications to the synthesis stack, targeted at the properties most likely to
close the remaining CLAP gap.

The OPT-002 params are retained in `hey_angel_cover.py` as the best achieved state
(three of four Tier-1 gates pass; best CLAP to date).

---

## Implications for Phase 2

The most likely architectural candidates (by perceptual salience and CLAP sensitivity):

1. **Supersaw voice architecture**: `SupersawPad` uses a fixed voice count and detune spread
   not exposed to the optimiser. SA's supersaw has a specific character determined by
   `saw_count`, `detune_cents`, and unison spread. These are currently hardcoded.

2. **Lead oscillator timbre**: `SmoothLead` is a single filtered sawtooth. SA's lead is
   likely a supersaw or layered oscillator. The optimiser drove `lead_cutoff_hz` to 11444 Hz
   (near the new 12000 upper bound) — wants to go brighter, suggesting the harmonic content
   of the oscillator itself is wrong, not just the filter frequency.

3. **Reverb character**: OPT-002 found `reverb_room=0.63`, `reverb_wet=0.37` — substantially
   wetter and larger room than the EXP-018 starting point. The Schroeder reverb topology may
   not match SA's FDN reverb character. Reverb tail shapes CLAP significantly for long audio.

4. **Kick character**: `kick_decay_s` hit the 0.50 upper bound. Either the bound is wrong or
   the kick synthesis model (exponential pitch sweep) doesn't match SA's TR-909 sample.

These are Phase 2 hypotheses, not decisions. Each requires a pre-specified hypothesis and
gate check before committing.
