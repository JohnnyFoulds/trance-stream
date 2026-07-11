# SA Parameter Measurement Methodology

**Date:** 2026-07-10  
**Branch:** `sidequest/pluck-arp-analysis`  
**Author:** Johannes Foulds + Claude Code  
**Status:** Audit in progress — tools built, measurements pending execution

---

## 1. Symptom

Several constants in `song/theory.py` carry `# SA confirmed` annotations implying they were
measured from SA's actual audio output. An audit revealed they were only ever OCR'd from SA's
Strudel source code — readable parameter values, not output measurements. The distinction
matters because:

- A parameter value in source code (`duckdepth(.6)`) tells you the *input* to a synthesis
  algorithm. It does not tell you what the algorithm *produces* — that depends on the internal
  implementation of Strudel's `.duck()` function, which was never read.
- Temporal parameters (how the sidechain recovers over time, how the lpenv cutoff sweeps,
  what the trancegate envelope actually looks like) cannot be inferred from static parameter
  values alone.
- One assumption was found to be actively wrong: all project documentation described the
  trancegate as a "smooth cosine envelope," but the actual function source in
  `research/strudel_debug.html` reveals a probabilistic binary gate.

Additionally, two active bugs in the Python generator mean that even if the constants are
correct, the output is wrong:

1. `synth/effects.py:327` — IIR residuals are normalised per-block, permanently ducking the
   pad at 40% gain after the first kick, even between kicks.
2. `instruments/pad.py:91` — trancegate BPM hardcoded to 140; at other BPMs the gate phase
   drifts.

---

## 2. Diagnosis

### 2.1 Tracing every constant's source

We read `song/theory.py` in full and traced every `# Source:` annotation back to its origin.
The audit revealed three confidence tiers (full table in `research/analysis/v3_parameter_audit.md`):

- **High confidence:** Constants directly visible in SA's Strudel code across multiple OCR
  sessions — `trancegate(1.5, 45, 1)`, `duckattack(.16)`, `duckdepth(.6)`, `rlpf` slider
  values, kick step pattern, 140 BPM, G natural minor.
- **Medium confidence:** OCR from a single session, or values derived through an intermediate
  modelling decision — build order bar numbers (one session only: `GWXCCBsOMSg`), trancegate
  cosine shape (assumed from "angle=45=equal rise/fall," never verified).
- **Low confidence / hand-tuned:** `TRANCEGATE_AMOUNT=0.7` (SA's value is `1`; 0.7 is an FDN
  compensation hack), `GAIN_PAD=1.50` (SA's value is `.pg(.5)=0.5`), lpenv `decay_s=0.80`
  and `peak_hz = base * 2.83` (no SA source — hand-tuned).

### 2.2 The trancegate finding

SA's actual Strudel function source, as inlined in `research/strudel_debug.html`:

```javascript
register('trancegate', (density, seed, length, x) => {
  density = reify(density).add(.5);
  return x.struct(rand.mul(density).round().seg(16).rib(seed, length)).fill().clip(.7);
});
```

This is `rand.mul(density).round()` — a **probabilistic binary gate**. `rand` produces
uniform random values in [0,1]; `.mul(density)` scales them; `.round()` snaps to 0 or 1.
With `density=1.5` (SA's value, after `.add(.5)` applied to the `1` argument), the mean of
`rand * 1.5` is 0.75, so most steps round to 1 (gate open) with some randomly gated.
`.seg(16)` quantises to 16 steps per bar. `.rib(seed, length)` makes the pattern repeatable
given the same seed. `.clip(.7)` attenuates the gated signal to 70%, not to silence.

The Python implementation (`synth/envelopes.py:64–94`) uses a **deterministic raised cosine**:

```python
cosine_01 = (1.0 + np.cos(phase + np.pi)) / 2.0
floor = 1.0 - amount
env = floor + cosine_01 * amount
```

This is a fundamentally different waveform. SA's gate is stochastic and stepped (16
discrete on/off slots per bar); ours is smooth and deterministic. The "angle=45=cosine"
interpretation in `docs/music_theory/02_sa_vocabulary_codified.md §2.2` and
`docs/music_theory/05_pad_and_lead_reference.md §2.5` is an incorrect inference.

**Implication:** After measurements confirm SA's gate shape from audio, a separate branch
will need to decide whether to replace the cosine with a probabilistic binary gate, or
to treat the cosine as an acceptable stylistic approximation. This document does not make
that decision — it documents the discrepancy.

### 2.3 Tool inventory for temporal measurements

Existing tools can measure point-in-time spectral properties but not temporal profiles:

| Tool | Temporal capability |
|---|---|
| `tools/analyse_audio.py` | None — all stats are file-wide means |
| `tools/spectrogram.py` | Visual only (PNG) |
| `tools/health_check.py` | LFO rate from centroid FFT (indirect) |
| `tools/compare_audio.py` | RMS envelope Pearson r (23ms hop) — closest to temporal |
| `tools/validate_hey_angel.py` | 50ms windows for sidechain (global peak/trough only) |

No existing tool produces: per-cycle sidechain depth + recovery curve, trancegate envelope
shape as a waveform, or spectral centroid over time aligned to chord triggers.

New tools required:
- `tools/capture_strudel_wav.py` — WAV capture from `strudel_debug.html` via Playwright
- `tools/measure_v3_output.py` — v3 render + temporal parameter measurement

---

## 3. Measurements taken

### M1 — Sidechain perpetual-duck confirmation

**Purpose:** Confirm the `synth/effects.py:327` bug produces measurable permanent ducking.

**Technique:** RMS envelope in 50ms non-overlapping windows, aligned to kick onset times
detected from the kick-solo WAV. Measure pad RMS pre-kick (200ms window) vs. between-kick
(200ms window 500ms after kick). Ratio should be ~1.0 if sidechain recovers; ~0.4 if bug
is active (IIR normalisation holds it at `1 - SIDECHAIN_DEPTH = 0.4`).

**Tools:** `scipy.signal` RMS, `scipy.io.wavfile` for WAV loading.

**Expected (buggy state):** `between_kick_rms / solo_pad_rms ≈ 0.40`

**SA target:** `between_kick_rms / solo_pad_rms ≈ 1.0`, `peak_duck_depth ≈ 0.40` (i.e. at the
kick hit the pad ducks to 40%, then recovers fully).

**Results:** → See `research/analysis/v3_measurements.json` §M1

---

### M2 — Trancegate actual shape

**Purpose:** Measure whether the Python trancegate output is a smooth cosine or a stepped
binary gate; confirm trough/peak ratio and cycles/bar against the constants.

**Technique:** Hilbert transform envelope extraction on pad-solo WAV, followed by:
1. Trough/peak ratio measurement
2. Cycle counting via zero-crossings of `(envelope - midpoint)`
3. Raised cosine curve fitting — RMS error between measured envelope and ideal cosine

The Hilbert transform provides the instantaneous amplitude (analytic signal magnitude),
which gives a smooth amplitude envelope without windowing artefacts (Gabor, 1946).

**Tools:** `scipy.signal.hilbert`, `numpy`.

**Expected:** `trough/peak ≈ 0.30` (for `TRANCEGATE_AMOUNT=0.7`), `cycles/bar ≈ 1.50`,
cosine fit RMS error < 0.05 (smooth), shape is NOT stepped 16-slot binary gate.

**Results:** → See `research/analysis/v3_measurements.json` §M2

---

### M3 — Filter floor (pad centroid at rest)

**Purpose:** Verify that `rlpf_to_hz(0.5) = (0.5 × 12)^4 = 1296 Hz` produces the expected
steady-state spectral centroid in the rendered output, and compare against SA's target range.

**Technique:** Short-time Fourier transform spectral centroid on steady-state section of pad
solo (bars 2–8, skipping bar 1 where lpenv swell is active). Centroid computed as
frequency-weighted mean: `centroid = Σ(f · |X(f)|) / Σ|X(f)|` (McFee et al., 2015).

**Tools:** `librosa.feature.spectral_centroid` or inline numpy STFT.

**Expected:**
- Formula prediction: 1296 Hz
- SA target (from `research/STRUDEL_DEBUG_PAGE.md` recipe c): 800–1200 Hz centroid
- Note: these disagree — the formula predicts the *cutoff* frequency, not the centroid.
  A 2nd-order Butterworth LPF at 1296 Hz will produce a centroid significantly below 1296
  Hz because all energy above 1296 Hz is attenuated. The centroid is a weighted mean over
  the entire spectrum. Confirming which prediction is right is the point of this measurement.

**Results:** → See `research/analysis/v3_measurements.json` §M3

---

### M4 — lpenv sweep shape (temporal centroid)

**Purpose:** Measure whether the lpenv in `instruments/pad.py` produces the expected
centroid rise after each chord trigger, and whether the timing matches the 60ms target
in `research/STRUDEL_DEBUG_PAGE.md` recipe d.

**Technique:** Parse MIDI file for pad note-on events (chord trigger times). For each
trigger, compute spectral centroid in 10ms windows for 500ms post-onset. Measure:
- Time to centroid peak (onset to maximum centroid)
- Peak centroid Hz
- Decay time: time from peak back to 90% of steady-state centroid

**Tools:** `mido` (MIDI parsing), `librosa.feature.spectral_centroid` with short hop_length.

**Expected:**
- Time to peak: ~60ms (STRUDEL_DEBUG_PAGE recipe d target)
- Peak centroid: `base * 2.83` Hz above steady-state (matching `peak_hz = cutoff * 2.83`)
- Current `decay_s = 0.80` in `instruments/pad.py` → 90% decay at ~1.84 s (`0.80 × ln(10) ≈ 1.84s`)

**Results:** → See `research/analysis/v3_measurements.json` §M4

---

### M5 — Sidechain depth per-cycle (temporal trace)

**Purpose:** Produce a per-kick-cycle sidechain profile: not just one global measurement
but a time-series showing duck depth and recovery shape across every kick in 8 bars.

**Technique:** Same kick onset detection as M1, then per-cycle:
- Pre-kick reference RMS (200ms window before onset)
- Duck depth: minimum RMS in 0–200ms post-onset, expressed as `20 * log10(min/pre)` dB
- Recovery curve: RMS at 10ms intervals for 600ms, normalised to pre-kick level
- Attack time: time from onset to minimum RMS
- Recovery time: time from minimum to 90% of pre-kick level

**Tools:** `scipy.io.wavfile`, `numpy`.

**Expected (with SA's parameters, bug fixed):**
- Duck depth: ~-8 dB (matching `duckdepth(.6)` → `gain = 0.4 → -7.96 dB`)
- Attack: `SIDECHAIN_ATTACK_S = 0.16s` → IIR time constant
- Recovery: exponential recovery with same tau
- **With current bug active:** attack depth flat at -8 dB across all bars, no recovery

**Results:** → See `research/analysis/v3_measurements.json` §M5

---

### S1–S4 — Strudel reference measurements

After `tools/capture_strudel_wav.py` is built, the same measurements (M2–M5) are applied
to WAV audio captured directly from `strudel_debug.html` running SA's Strudel code.

This produces ground-truth SA values for each parameter — not OCR'd constants but actual
measured audio properties of the running synthesis. These are committed as:
- `research/reference_audio/sa_trancegate_c1_8s.wav` — c1 snippet: pad only, 8s
- `research/reference_audio/sa_sidechain_c2_8s.wav` — c2 snippet: pad + kick, 8s

---

## 4. Root cause summary

| Parameter | Claimed status | Actual status | Root cause of gap |
|---|---|---|---|
| Trancegate shape | SA confirmed cosine | Wrong — SA uses probabilistic binary gate | "angle=45=cosine" was inference, not source-code read |
| Trancegate amount | SA confirmed 1.0 | `TRANCEGATE_AMOUNT=0.7` in code | Developer override for FDN compensation, not annotated |
| Sidechain depth | SA confirmed 0.6 | Constant correct; output wrong | `synth/effects.py:327` IIR normalisation bug |
| Sidechain recovery | Not measured | Unknown | No temporal measurement tool existed |
| Filter floor | Formula confirmed | Centroid prediction wrong | Confusing cutoff Hz with spectral centroid Hz |
| lpenv timing | 60ms target | Not measured | No temporal centroid tool existed |
| BPM in pad | N/A | Hardcoded 140 | `instruments/pad.py:91` literal not using `song.bpm` |

---

## 5. How to reproduce this audit

### Prerequisites

```bash
pip install numpy scipy librosa mido soundfile playwright
playwright install chromium
```

### Step 1: v3 measurements (no server needed)

```bash
cd /Users/johannes/switch-angel/trance-stream
python tools/measure_v3_output.py --bars 8 --bpm 140 --seed sunrise
# Output: research/analysis/v3_measurements.json + printed table
```

### Step 2: Strudel reference captures (requires HTTP server)

```bash
# Terminal 1:
cd /Users/johannes/switch-angel/trance-stream/research
python -m http.server 8765

# Terminal 2:
cd /Users/johannes/switch-angel/trance-stream
python tools/capture_strudel_wav.py --snippet c1 --duration 8 \
    --out research/reference_audio/sa_trancegate_c1_8s.wav
python tools/capture_strudel_wav.py --snippet c2 --duration 8 \
    --out research/reference_audio/sa_sidechain_c2_8s.wav
```

### Step 3: Apply same analysis to Strudel captures

```bash
python tools/measure_v3_output.py --ref-trancegate research/reference_audio/sa_trancegate_c1_8s.wav \
                                  --ref-sidechain  research/reference_audio/sa_sidechain_c2_8s.wav
```

---

## 6. References

Gabor, D. (1946). Theory of communication. *Journal of the Institution of Electrical
Engineers*, *93*(26), 429–441. https://doi.org/10.1049/ji-3-2.1946.0074

McFee, B., Raffel, C., Liang, D., Ellis, D. P. W., McVicar, M., Battenberg, E., & Nieto, O.
(2015). librosa: Audio and music signal analysis in Python. In *Proceedings of the 14th
Python in Science Conference* (pp. 18–25). https://doi.org/10.25080/Majora-7b98e3ed-003

Virtanen, P., Gommers, R., Oliphant, T. E., Haberland, M., Reddy, T., Cournapeau, D.,
Burovski, E., Peterson, P., Weckesser, W., Bright, J., van der Walt, S. J., Brett, M.,
Wilson, J., Millman, K. J., Mayorov, N., Nelson, A. R. J., Jones, E., Kern, R., Larson, E.,
... van Mulbregt, P. (2020). SciPy 1.0: Fundamental algorithms for scientific computing in
Python. *Nature Methods*, *17*(3), 261–272. https://doi.org/10.1038/s41592-019-0686-2

Microsoft. (2020). Playwright (Version 1.x) [Software]. Microsoft. https://playwright.dev

World Wide Web Consortium. (2021). *Web Audio API*. W3C Recommendation.
https://www.w3.org/TR/webaudio/
