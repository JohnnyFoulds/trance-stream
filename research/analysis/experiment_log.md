# Synthesis Experiment Log

**Baseline**: `hey_angel_cover.py` on branch `sidequest/pluck-arp-analysis`, commit `2c0997a`  
**Reference**: `research/reference_audio/hey_angel_trimmed.wav`  
**Tool**: `tools/compare_audio.py` (two-tier architecture, redesigned 2026-07-10)  
**Methodology**: `research/analysis/synthesis_parameter_methodology.md`

---

## Log rules

- **Append-only**: rows are never edited after entry. Corrections get a new row referencing the original.
- **No changes without a pre-specified hypothesis and falsification criterion** (see methodology §7.3).
- **Every row must include the full reproducible command** — the log is the complete record.
- **Revert = new row**: if a hypothesis is rejected and the change is reverted, add a REVERT row referencing the rejected EXP-ID.
- **Metric values are numeric**, not just PASS/FAIL. Record the raw numbers.

---

## EXP-000 — Baseline (v32, no changes)

**Date**: 2026-07-10  
**Hypothesis**: N/A — baseline measurement  
**Parameters**: All at committed values
- `SmoothLead.cutoff_hz = 900.0` (instruments/smooth_lead.py)
- `_gain_hihat = GAIN_HIHAT × 0.5 = 0.25` (hey_angel_cover.py)
- Bass G1 `cutoff_slider = 0.26` → 83 Hz (hey_angel_cover.py)

**Reproducible command**:
```bash
python hey_angel_cover.py --bars 15 --wav /tmp/ha_EXP-000.wav
python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav /tmp/ha_EXP-000.wav --bpm 140.0534
```

**Results**:

| Metric | Value | Threshold | Pass? |
|---|---|---|---|
| **clap_cosine** | **0.385** | ≥ 0.70 | **FAIL** |
| **spectral_centroid_ratio** | **0.567** | 0.70–1.30 | **FAIL** |
| **band_energy_cosine** | **0.649** | ≥ 0.85 | **FAIL** |
| **mfcc_cosine** | **0.661** | ≥ 0.80 | **FAIL** |
| rms_envelope_r | 0.818 | ≥ 0.70 | PASS |
| onset_xcorr_peak | 0.488 | ≥ 0.40 | PASS |
| chroma_cosine | 0.906 | ≥ 0.80 | PASS |

**Overall**: **FAIL** — all Tier-1 gates fail

**Six-band energy breakdown** (reference vs generated, at 22050 Hz):

| Band | Reference | Generated | Ratio |
|---|---|---|---|
| 0–200 Hz | 49.8% | 25.8% | 0.52× |
| 200–500 Hz | 13.6% | 52.5% | 3.87× |
| 500–1k Hz | 8.7% | 18.9% | 2.17× |
| 1–2k Hz | 8.3% | 2.1% | 0.26× |
| 2–4k Hz | 10.3% | 0.1% | 0.01× |
| 4k+ Hz | 9.3% | 0.5% | 0.05× |

**Notes**: All Tier-1 metrics fail. Root cause: `SmoothLead.cutoff_hz = 900 Hz` dumps 52.5% of mix energy into 200–500 Hz band (reference: 13.6%). Harmonic/percussive separation confirms this is harmonic overflow (57.8% of harmonic energy in 200–500 Hz). The 4k+ percussive fraction (20.3%) already matches reference (21.0%) — hi-hat volume is not the primary problem; harmonic energy ratio is. See methodology §4.4 for full causal dependency graph.

---

## BUG-001 — Fix: Sidechain IIR replaced with instant-attack / exponential-release

**Date**: 2026-07-10  
**File**: `synth/effects.py`, `Sidechain` class  
**Root cause**: The original implementation used a one-pole IIR smoother (scipy `lfilter` with `zi=`) for both attack and release. At τ=0.16s and sr=44100, α ≈ 1.416e-4 — the envelope barely rises during a 20ms kick body (~0.28 of full amplitude), so effective duck depth was ~20% of the specified 72.1%.  
**What the code review described** was a per-block peak normalisation amplifying IIR residuals. That normalisation step was NOT present in the actual code — the code review described a stale or hypothetical version. The real bug was the symmetric attack/release time constant.  
**Fix applied**: Replaced IIR with an explicit sample loop: instant attack (peak-hold), exponential release at the same τ=0.16s. Also renamed `_attack_s` → `_release_s` to match SA's `.duckattack()` semantics (the parameter controls recovery, not onset).  
**Verification**:
```
t=0ms  gain: 0.279  (= 1 - 0.721, full duck on kick sample 0)  ✓
t=1.714s (one full bar silence): duck residual = 1.4e-5 ≈ 0  ✓
```

**Note on EXP-000 contamination**: EXP-000 baseline was rendered with the broken sidechain. With the slow IIR, pad energy was under-ducked (kick got ~20% attenuation instead of 72.1%). The EXP-000 band energy numbers reflect this contaminated state. EXP-001 must be re-run with the fixed sidechain as the new baseline before interpreting H1.

---

## EXP-001 — H1: Lead cutoff raise 900 Hz → 2400 Hz (PENDING)

**Pre-specified hypothesis**:  
Raising `SmoothLead.cutoff_hz` from 900 Hz to 2400 Hz will:
- Decrease 200–500 Hz band energy fraction (currently 52.5% → toward reference 13.6%)
- Increase 1–2 kHz band energy fraction (currently 2.1% → toward reference 8.3%)
- Increase `spectral_centroid_ratio` above 0.70 (currently 0.567)
- Increase `band_energy_cosine` above 0.70 (currently 0.649)

**Falsification criterion**: If `band_energy_cosine` does not increase by ≥ 0.05 (to ≥ 0.70), H1 is rejected and the change is reverted.

**Confound risk**: Raising cutoff may expose upper harmonics that are perceptually harsh or diverge from the reference's filtered character. Monitor `mfcc_cosine` — if it drops by > 0.05 after the raise, reduce cutoff to an intermediate value (e.g. 1800 Hz) and re-run.

**Dependency**: H2 (hi-hat gain) must NOT be run until this experiment is evaluated — raising hi-hat gain before the lead cutoff fix would produce the wrong gain target (since the harmonic/percussive ratio will change when H1 is applied).

**Target parameter**: `SmoothLead.cutoff_hz` in `instruments/smooth_lead.py`, currently 900.0 → 2400.0

**Reproducible command**:
```bash
python hey_angel_cover.py --bars 15 --wav /tmp/ha_EXP-001.wav
python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav /tmp/ha_EXP-001.wav --bpm 140.0534 > /tmp/EXP-001_compare.txt
```

**Results**: (fill in after running)

| Metric | Value | Pass? | Delta from EXP-000 |
|---|---|---|---|
| clap_cosine | — | — | — |
| spectral_centroid_ratio | — | — | — |
| band_energy_cosine | — | — | — |
| mfcc_cosine | — | — | — |
| rms_envelope_r | — | — | — |
| onset_xcorr_peak | — | — | — |
| chroma_cosine | — | — | — |

**Overall**: PENDING  
**Outcome**: PENDING  
**Notes**: (fill in after running)

---

## EXP-002 — H2: Hi-hat gain calibration (0.25 → target) (BLOCKED on EXP-001)

**Pre-specified hypothesis**:  
Raising `_gain_hihat` from its current effective value of 0.25 to a calibrated target will:
- Increase 2–4 kHz and 4k+ Hz band energy fractions (currently 0.1% and 0.5% → toward reference 10.3% and 9.3%)
- Increase `band_energy_cosine`
- Not significantly affect `rms_envelope_r` or `chroma_cosine` (hi-hats are above the harmonic range)

**Falsification criterion**: If 4k+ band energy fraction does not at least double from its post-EXP-001 value, H2 is rejected.

**Dependency**: BLOCKED — must evaluate EXP-001 first. The target gain multiplier depends on the post-H1 percussive/harmonic ratio. Hi-hat gain must be calibrated against the mix after the lead cutoff is fixed.

**Target gain range**: approximately 1.0–1.5 (from 0.25 current). Exact target determined by measuring 4k+ band energy fraction after EXP-001 and calibrating proportionally.

**Reproducible command** (fill in after EXP-001 target is determined):
```bash
python hey_angel_cover.py --bars 15 --wav /tmp/ha_EXP-002.wav
python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav /tmp/ha_EXP-002.wav --bpm 140.0534 > /tmp/EXP-002_compare.txt
```

**Results**: PENDING — blocked on EXP-001

---

## EXP-003 — H3: Bass harmonic content (cutoff_slider 0.26 → 0.38) (BLOCKED on EXP-001)

**Pre-specified hypothesis**:  
Raising bass G1 note `cutoff_slider` from 0.26 (≈83 Hz, kills G2 at 98 Hz) to approximately 0.38 (≈350 Hz, passes G2 and G3) will:
- Increase 0–200 Hz band energy fraction (currently 25.8% → toward reference 49.8%)
- Not significantly affect kick phase error or chroma cosine

**Falsification criterion**: If 0–200 Hz fraction does not increase by ≥ 5 percentage points from its post-EXP-001 value, H3 is rejected.

**Confound risk**: Bass harmonic content may clash with kick sub-bass in the 50–120 Hz region. Monitor `rms_envelope_r` and the kick phase alignment.

**Dependency**: Run after EXP-001 to avoid confounded measurements of the 0–200 Hz band.

**Reproducible command** (fill in after EXP-001):
```bash
python hey_angel_cover.py --bars 15 --wav /tmp/ha_EXP-003.wav
python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav /tmp/ha_EXP-003.wav --bpm 140.0534 > /tmp/EXP-003_compare.txt
```

**Results**: PENDING — blocked on EXP-001

---

## EXP-004 — H4: Joint Phase 1 (H1 + H2 + H3 simultaneously) (BLOCKED on EXP-001–003)

**Pre-specified hypothesis**:  
Applying H1 + H2 + H3 simultaneously (Phase 1 complete: lead cutoff = 2400 Hz, hi-hat gain calibrated, bass cutoff raised) will push:
- `band_energy_cosine` above 0.85
- `spectral_centroid_ratio` into [0.70, 1.30]

**Falsification criterion**: If both metrics do not pass simultaneously, Phase 2 investigation begins — the residual mismatch is in oscillator type, resonance Q, or envelope character not captured by the filter cutoff changes.

**Dependency**: BLOCKED — H1, H2, H3 must be individually validated before joint application.

**Reproducible command** (fill in after EXP-001–003):
```bash
python hey_angel_cover.py --bars 15 --wav /tmp/ha_EXP-004.wav
python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav /tmp/ha_EXP-004.wav --bpm 140.0534 > /tmp/EXP-004_compare.txt
```

**Results**: PENDING
