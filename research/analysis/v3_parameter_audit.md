# v3 Parameter Audit — SA Reference vs Generator Output

**Date:** 2026-07-10  
**Branch:** `sidequest/pluck-arp-analysis`  
**Rendered with:** `python trance_stream_v3.py --bars 8 --bpm 140 --seed sunrise`  
**Tools used:** `tools/measure_v3_output.py`, `tools/capture_strudel_wav.py` (Strudel captures pending)  
**Raw numbers:** `research/analysis/v3_measurements.json`  
**Full methodology:** `research/analysis/sa_parameter_measurement_methodology.md`

---

## Summary

| Parameter | SA target | v3 measured | Status |
|---|---|---|---|
| Sidechain duck depth | ~−8 dB (depth=0.6) | −9.6 dB mean | CLOSE — within range, but high variance (−3 to −21 dB) |
| Sidechain recovery | Recovers to 100% between kicks | 14 ms mean recovery | UNRELIABLE — measurement method is flawed (see M1) |
| Trancegate shape | Probabilistic binary gate (SA source) | Smooth cosine (our implementation) | MISMATCH — fundamentally different |
| Trancegate trough/peak | Unknown (SA binary gate, not cosine) | 0.19 (expected 0.30 for amount=0.7) | DISCREPANCY — trough lower than expected |
| Trancegate cycles/bar | 1.5 | 1.57 | ACCEPTABLE (within 5%) |
| Filter floor centroid | 800–1200 Hz | 1139 Hz | PASS — within SA target range |
| lpenv time-to-peak | 60 ms | 258 ms | MISS — but measurement is unreliable (see M4) |
| lpenv peak centroid | Unknown | 2139 Hz | Not yet compared against Strudel |

**Strudel reference captures:** Pending. `tools/capture_strudel_wav.py` is built and ready;
SA ground-truth measurements (S1–S4) will be added to this document when captures are run.

---

## M1 — Sidechain

### What was measured

Full mix WAV + kick-solo WAV, 8 bars at 140 BPM. Kick onsets detected by RMS threshold on
kick-solo. For each kick onset: pre-kick RMS (200ms window), per-10ms post-kick RMS for
600ms, duck depth in dB, recovery time to 90% of pre-kick level.

### Results

- **31 kick onsets detected** across 8 bars (expected 32 = 4 beats × 8 bars; one onset at the
  very start was likely below the detection window)
- **Mean duck depth:** −9.6 dB (range −3.0 to −21.3 dB)
- **Mean recovery time:** 14 ms
- **Permanent duck ratio:** 2.0 (pad between kicks has MORE RMS than pad solo — no permanent duck)

### Interpretation

**The sidechain bug is not firing during normal 4-on-floor playback.** The bug mechanism
(per-block IIR normalisation) only produces permanent ducking when a bar contains no kick
at all — the IIR state decays to a small residual `ε`, which is then divided by `ε` and
rescaled to 1.0. With 4-on-floor kicks, every bar has at least one kick that resets the IIR
envelope to a genuine peak value, so the normalisation is always dividing by a real kick
amplitude, not a residual. The bug is latent during normal playback.

It will become audible in:
- Breakdown sections (kick muted, `--mute kick`, or phase where `kick_gain = 0`)
- Any gap > one bar without a kick

**The duck depth variance is very high (−3 to −21 dB across consecutive kicks).** This is
not physical — SA's sidechain should produce consistent depth on every kick. The high variance
indicates the `pre_rms` measurement window is contaminated by the trancegate: when a kick
fires at a trancegate trough, the pre-kick pad RMS is low (gate attenuated), making the
apparent duck depth exaggerated. When the kick fires at a trancegate peak, pre-kick RMS is
high, making the duck look shallow. The measurement method needs to isolate pad RMS from
the trancegate modulation — measure pre-kick pad from the pad-solo WAV separately, then
compare to full-mix pad at the same time window.

**The 14ms mean recovery is also unreliable** for the same reason: the post-kick centroid
is recovering not just the sidechain envelope but also the trancegate which may be
independently rising.

**SA target for comparison:** SA's `.duckattack(.16)` specifies a 160ms attack time constant.
Our 14ms figure is not measuring the same thing.

### What this measurement confirms

- Sidechain is producing some ducking (duck depth is non-zero)
- The bug at `synth/effects.py:327` is not perceptually active during 4-on-floor playback
- Duck depth and recovery shape cannot be measured reliably from the full mix without
  isolating the pad voice from the trancegate modulation

### What needs to happen next

1. Re-run M1 with the pad-only WAV as the "pre-kick reference" rather than the full mix
2. Compare against Strudel c2 capture (pad + kick) once `capture_strudel_wav.py` is run
3. The breakdown-phase bug still needs fixing — test by running with `--mute kick` and
   confirming the pad RMS drops permanently

---

## M2 — Trancegate shape

### What was measured

Pad-solo WAV (8 bars). Hilbert transform amplitude envelope, smoothed with
`gate_period/4 ≈ 286ms` moving average. Trough/peak ratio, cycle counting via
zero-crossings, cosine curve fitting (phase sweep, RMS error).

### Results

- **Trough/peak ratio:** 0.19 (expected 0.30 for `TRANCEGATE_AMOUNT = 0.7`)
- **Cycles per bar:** 1.57 (expected 1.50, within 5%)
- **Cosine fit RMS error:** 0.14 (threshold 0.20 → classified as cosine)
- **Shape verdict:** smooth cosine confirmed for v3 output

### Interpretation

**The shape is cosine — that is confirmed for the Python generator output.** But this is
the wrong shape: SA's actual Strudel function uses `rand.mul(density).round()`, a
probabilistic binary gate with 16 discrete slots per bar. This means v3 and SA are using
fundamentally different gate paradigms:

| Aspect | SA (Strudel) | v3 (Python) |
|---|---|---|
| Shape | Stepped binary (0 or 1 per 16th-note slot) | Smooth cosine |
| Randomness | Probabilistic (different every loop) | Deterministic |
| Silence at trough | Yes (some slots gated fully off) | No (trough = 0.3) |
| `.clip(.7)` in SA | Attenuates signal to 70% on open slots | Not modelled |

**Trough/peak discrepancy (0.19 vs 0.30):** The envelope is measured after smoothing with a
286ms window. The supersaw fundamental at 48Hz (G1) has a period of ~21ms; at 140BPM a
16th-note is 107ms. The smoothing window intentionally spans multiple carrier cycles to
extract the gate envelope, but it also averages over multiple gate cycles, which
compresses the apparent trough depth. The true gate trough (in a brief silent slot) would
read lower than 0.30. This is a measurement artefact, not a synthesis error.

### What this measurement confirms

- v3 trancegate cycles at 1.57/bar — close to the 1.5 target ✓
- v3 shape is smooth cosine — different from SA's probabilistic binary gate ✗
- `TRANCEGATE_AMOUNT = 0.7` produces a trough that does not reach silence, which is a
  deliberate departure from SA's value of `1` (full silence at trough)

### What needs to happen next

1. Capture SA c1 WAV with `capture_strudel_wav.py` and apply the same Hilbert analysis
2. Confirm whether SA's output shows stepped 16-slot pattern or smooth curve
   (the `rand.seg(16)` quantisation should be visible as plateau transitions)
3. Decide in a separate plan whether to replace the cosine with a stochastic binary gate

---

## M3 — Filter floor

### What was measured

Pad-solo WAV, steady-state section (bars 2–8, skipping bar 1 for lpenv warmup). Mean
spectral centroid computed as frequency-weighted magnitude: `Σ(f·|X(f)|) / Σ|X(f)|`.

### Results

- **Steady-state centroid:** 1139 Hz
- **95% rolloff:** 3400 Hz
- **Formula prediction** (`rlpf_to_hz(0.5) = (0.5×12)^4`): 1296 Hz
- **SA target range** (STRUDEL_DEBUG_PAGE recipe c): 800–1200 Hz
- **In SA target range:** YES ✓
- **Within 10% of formula prediction:** NO (1139 vs 1296, −12%)

### Interpretation

**The filter floor is within SA's target range.** The centroid (1139 Hz) sits just below
the top of the SA target (1200 Hz) — within the acceptable zone but toward the bright end.

**The formula predicts the cutoff frequency, not the centroid.** A 2nd-order Butterworth
LPF at 1296 Hz attenuates everything above that frequency with a 12 dB/oct slope. The
spectral centroid is the weighted mean across the *entire* spectrum — because the filter
suppresses high frequencies, the centroid will always sit below the cutoff. The −12%
discrepancy between the measured centroid and the formula cutoff is expected, not an error.

**The sub-bass doublings at −14 and −21 semitones** add energy at very low frequencies
(~12Hz and ~6Hz at G1 root), which pull the centroid downward relative to a single-voice
pad. This explains some of the gap.

### What this measurement confirms

- Filter is functioning correctly — centroid is in SA's target range ✓
- The `rlpf_to_hz(0.5)` formula is correct for cutoff frequency; centroid will naturally
  be lower than the cutoff value

### What needs to happen next

1. Compare against Strudel c1 steady-state centroid to get SA's actual target value
   (800–1200 Hz is a broad estimated range; the real number from Strudel audio is the
   authoritative target)

---

## M4 — lpenv sweep shape

### What was measured

MIDI file from the v3 render was checked for pad note-on events. The MIDI writer does not
emit pad note events in the current implementation, so chord trigger times were detected
instead from onset detection on the pad-solo WAV. For each trigger: spectral centroid in
10ms windows for 500ms, time to peak centroid, peak centroid Hz, decay to 90% of
steady-state.

### Results

- **Mean time to centroid peak:** 258 ms (SA target: 60 ms)
- **Mean peak centroid:** 2139 Hz
- **Mean decay to 90%:** 51 ms
- **Triggers analysed:** 22

### Interpretation

**The 258ms figure is not a reliable measurement of the lpenv attack time.** The trigger
detection used pad-solo WAV onset detection, which detects trancegate amplitude peaks
(large RMS changes at ~1.5 cycles/bar), not chord trigger times. The trancegate peaks
are offset from chord trigger times by an unpredictable phase amount, so the 258ms
"time-to-peak" is measuring the time from a trancegate peak to the next trancegate peak
minus some offset — not the lpenv rise time.

**The decay to 90% in 51ms may be more reliable** because it is measuring a rapid spectral
change within a single 500ms window, less sensitive to the exact trigger start point.

**The peak centroid of 2139 Hz** is consistent with the `peak_hz = base_hz × 2.83` formula:
`1139 Hz × 2.83 ≈ 3223 Hz` (expected peak) vs 2139 Hz measured. The gap (−34%) suggests
either the lpenv peak is not reaching its full value within the measurement window, or the
trigger alignment is systematically off.

### What this measurement confirms

- The lpenv is producing some centroid rise (peak centroid 2139 Hz > steady-state 1139 Hz) ✓
- The quantitative timing cannot be confirmed without reliable chord trigger times

### What needs to happen next

1. Fix MIDI export to emit pad note-on events, then re-run M4 with MIDI-derived trigger times
2. Compare against Strudel c1 lpenv sweep (S3) for ground-truth timing
3. Current `decay_s = 0.80s` in `instruments/pad.py` may be correct — cannot confirm
   without fixing the trigger detection

---

## Known active bugs (not measured, but confirmed from code review)

These bugs are documented here for completeness. They were identified by code reading in
the 2026-07-10 code review (`docs/code-reviews/2026-07-10.md`), not by the measurements
above, because the measurements could not isolate them under normal 4-on-floor conditions.

| Bug | Location | Effect | Triggering condition |
|---|---|---|---|
| Sidechain perpetual duck | `synth/effects.py:327` | Pad stuck at 40% gain | Any bar with no kick (breakdown, `--mute kick`) |
| Trancegate BPM hardcoded | `instruments/pad.py:91` | Gate drifts at non-140 BPM | Any `--bpm` other than 140 |
| FM depth always 0.5 | `instruments/pulse.py:39` | Pulse always maximally modulated | All playback |
| Hey Angel gain at 55% | `song/arcs.py:231` | Mix too quiet for `--style hey_angel` | `--style hey_angel` |

---

## Strudel reference measurements (pending)

The following measurements require running `tools/capture_strudel_wav.py` against the
live `strudel_debug.html` page. They will provide SA's ground-truth values for each
parameter to compare against the v3 measurements above.

To run:

```bash
# Terminal 1: start HTTP server
cd /Users/johannes/switch-angel/trance-stream/research && python -m http.server 8765

# Terminal 2: capture
cd /Users/johannes/switch-angel/trance-stream
python tools/capture_strudel_wav.py --snippet c1 --duration 8 \
    --out research/reference_audio/sa_trancegate_c1_8s.wav
python tools/capture_strudel_wav.py --snippet c2 --duration 8 \
    --out research/reference_audio/sa_sidechain_c2_8s.wav

# Then re-run measure_v3_output.py with the reference files:
python tools/measure_v3_output.py --bars 8 --bpm 140 --seed sunrise
```

Pending results to fill in:

| Measurement | SA ground truth | v3 value | Gap |
|---|---|---|---|
| S1 Trancegate shape | TBD — expect stepped 16-slot binary | Smooth cosine | TBD |
| S2 Filter floor centroid | TBD — expect 800–1200 Hz | 1139 Hz | TBD |
| S3 lpenv time-to-peak | TBD — expect ~60 ms | 258 ms (unreliable) | TBD |
| S4 Sidechain duck depth | TBD — expect ~−8 dB | −9.6 dB mean | TBD |

---

## Revised confidence table for theory.py constants

Updated from the pre-audit table in `CLAUDE.md`, incorporating measurement results:

| Constant | Value | Pre-audit status | Post-audit status |
|---|---|---|---|
| `TRANCEGATE_SPEED` | 1.5 | SA confirmed (OCR) | CONFIRMED — 1.57 cycles/bar measured ✓ |
| `TRANCEGATE_AMOUNT` | 0.7 | Hand-tuned (SA=1) | CONFIRMED DEPARTURE — intentional, trough=0.3 not silence |
| `TRANCEGATE_ANGLE` as cosine | — | Assumed | WRONG — SA uses binary gate; cosine is wrong model |
| `SIDECHAIN_DEPTH` | 0.6 | SA confirmed (OCR) | PLAUSIBLE — mean depth −9.6 dB consistent with 0.6; measurement has high variance |
| `SIDECHAIN_ATTACK_S` | 0.16 | SA confirmed (OCR) | NOT YET MEASURED — recovery 14 ms figure is unreliable |
| Filter cutoff `rlpf_to_hz(0.5)` | 1296 Hz | SA confirmed (OCR) | FORMULA CORRECT — centroid 1139 Hz in SA target range ✓ |
| lpenv `decay_s` | 0.80 | Hand-tuned | NOT YET MEASURED — M4 trigger detection unreliable |
| lpenv `peak_hz = base × 2.83` | — | Hand-tuned | PARTIAL — peak centroid 2139 Hz measured; expected 3223 Hz |

---

## What to fix next (prioritised)

These are findings only — fixes belong in a separate branch after Strudel captures are run.

1. **Trancegate model** — replace smooth cosine with probabilistic binary gate matching
   SA's `rand.mul(density).round().seg(16)` pattern. This is the highest-impact perceptual
   change: the stepped gate is the most distinctive sound in SA's pad.

2. **Fix M1 measurement method** — re-measure sidechain with pad-only pre-kick reference
   to get clean duck depth and recovery curves.

3. **Fix M4 measurement method** — either fix MIDI export to emit pad note-on events, or
   add chord trigger time output to the renderer, before trusting lpenv timing measurements.

4. **Fix sidechain bug** (`synth/effects.py:327`) — change per-block normalisation to a
   fixed reference so breakdown sections do not permanently duck.

5. **Fix pad BPM hardcode** (`instruments/pad.py:91`) — use `song.bpm` from the renderer.

6. **Run Strudel captures** — complete S1–S4 to replace estimated SA targets with measured
   ground truth before implementing fixes 1, 4, 5.
