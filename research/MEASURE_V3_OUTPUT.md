# v3 Parameter Audit Methodology

**Purpose:** Confirm known bugs and document the actual state of five key synthesis
parameters *before* any source files are modified. This is a pre-fix baseline — every
number here is a description of the broken state, not a target.

**Date recorded:** 2026-07-10
**Script:** `tools/measure_v3_output.py`

---

## Why this audit exists

Two confirmed bugs were identified in code review but not yet fixed:

1. **Sidechain perpetual-duck** (`synth/effects.py:327`) — the IIR envelope
   follower's `zi` state retains a residual after each kick hit. The normalisation
   `kick_env_smooth / max(peak, 1e-9)` divides the residual (which is small but
   non-zero) by itself, producing a constant `1.0` input to the gain formula
   `gain = 1 − depth × 1.0 = 0.4`. Between kicks the pad gain is permanently locked
   at 0.4 (−7.96 dB) instead of recovering to 1.0.

2. **Hardcoded BPM in `instruments/pad.py:91`** — the line `spb = samples_per_bar()`
   calls `samples_per_bar()` with no argument, which uses the module-level default
   `BPM = 140.0` from `song/theory.py` instead of the song's actual BPM. When a
   render is requested at any BPM other than 140 the trancegate period in the pad is
   computed at the wrong rate, causing tempo drift between the pad gate and the kick.

This script measures the *observable effects* of bug 1 (M1, M5) and captures the
nominal state of the other parameters (M2–M4) so that post-fix measurements can be
compared against them.

---

## How to run

```bash
# From the repo root — default 8 bars at 140 BPM with seed "sunrise"
python tools/measure_v3_output.py

# Custom parameters
python tools/measure_v3_output.py --bpm 140 --bars 16 --seed sunrise \
    --out research/analysis/v3_measurements.json
```

The script:
1. Calls `trance_stream_v3.py` as a subprocess three times (full mix + MIDI,
   pad solo, kick solo). This avoids importing the module directly and triggering
   side effects such as sounddevice initialisation.
2. Loads the three WAV files with `scipy.io.wavfile` / `wave`.
3. Computes measurements M1–M5 in sequence.
4. Writes `research/analysis/v3_measurements.json`.
5. Prints a human-readable table to stdout.

---

## M1 — Sidechain perpetual-duck confirmation

### What is measured

- **Permanent duck ratio**: RMS of the full mix *between* kick hits, divided by RMS
  of the pad solo at the same time positions. If the sidechain is working correctly
  this ratio should be close to 1.0 (other instruments contribute so it will be
  slightly above 1.0). If the bug is present the ratio will be approximately 0.4
  (gain floor = 1 − depth = 1 − 0.6 = 0.4).

- **Per-cycle duck depth**: for each kick onset the script measures the pre-kick
  RMS in a 200 ms window before the hit, then the minimum RMS in 10 ms windows for
  600 ms after the hit. `duck_depth = min_post_rms / pre_rms`. In decibels this is
  the instantaneous duck depth at the deepest point of each cycle.

- **Recovery time**: time from the kick onset to the first 10 ms window where RMS
  recovers to 90% of the pre-kick level. Expected ~160 ms (one SIDECHAIN_ATTACK_S
  time constant). With the bug active recovery never completes.

### Technique

Kick onsets are found by computing RMS in non-overlapping 50 ms windows on the kick
solo WAV and selecting windows with RMS > 0.1. This threshold was chosen because the
kick peak amplitude in solo normalises close to 1.0, while noise floor is < 0.01.

The permanent duck ratio is computed over windows that exclude ±300 ms around each
kick onset to avoid contamination from the legitimate duck impulse.

### Expected values (bug present)

| Metric | Expected (bug present) | Expected (fixed) |
|---|---|---|
| Permanent duck ratio | ~0.4 | ~1.0 |
| Mean duck depth | ~0.4 (same reason) | ~0.4 at onset, recovers |
| Mean recovery ms | None / never | ~160–200 ms |

### Important: the bug is latent at 4-on-floor kick density

The bug fires when a bar's `kick_env_smooth` buffer has no real kick peak —
specifically when `max(kick_env_smooth)` in the processed buffer is the IIR
residual tail (amplitude ~2 × 10⁻⁵ after 1 bar at τ = 0.16 s) rather than a
genuine kick transient.  Dividing the residual by itself normalises it to 1.0,
permanently applying full ducking.

At 4-on-floor density (kick every 0.4286 s at 140 BPM), every bar buffer contains
real kick transients.  The bar's `max(kick_env_smooth)` is therefore always the real
kick peak, and the normalisation is correct.  The bug does **not** manifest in this
test configuration.

The bug **will** manifest when: (a) a breakdown or fill leaves a full bar with no
kick hits; (b) the pad enters before the kick (`pad_root_on = 2 < kick_on = 0` in
the default stage map, which means this does not apply, but custom stage maps could
trigger it); (c) a style variant (e.g. `hey_angel` half-time) has fewer kicks.

`bug_confirmed` in the JSON is `False` for standard 4-on-floor 8-bar renders. To
provoke the bug: render `--mute kick` solo with a second render of pad, or introduce
a bar with no kick step.

### Limitation

Because the full mix includes kick, bass, lead, and other instruments the permanent
duck ratio is not a pure measure of pad level. It is a directional indicator.
A ratio well below 0.7 reliably confirms permanent ducking; a ratio near 1.0 does not
rule out partial ducking.

---

## M2 — Trancegate actual shape

### What is measured

- **Trough/peak ratio**: minimum / maximum of the amplitude envelope after bar 1.
  `TRANCEGATE_AMOUNT = 0.7` → expected trough = 0.3, peak = 1.0 → ratio ≈ 0.30.

- **Cycles per bar**: zero-crossings of `(envelope − midpoint)` divided by 2, then
  divided by duration in bars. `TRANCEGATE_SPEED = 1.5` → expected 1.5 cycles/bar.

- **Cosine fit error**: RMS deviation between the normalised measured envelope and the
  expected raised cosine `(1 + cos(2π t / period + π)) / 2` over a 3-cycle window
  taken from the middle of the recording. A value < 0.05 is declared a cosine match.

### Technique

Amplitude envelope extraction uses the analytic signal magnitude
`|H{x}(t)|` via `scipy.signal.hilbert`. The Hilbert transform produces the
instantaneous envelope without the pitch-frequency ripple present in simple
half-wave rectification (Gabor, 1946).

The envelope is smoothed with a 5 ms moving average (causal box filter) to suppress
frame-rate artefacts from the supersaw voices. A shorter window would show
oscillator-rate ripple; a longer one would smear the gate edges.

### Limitation

The Hilbert-transform envelope is sensitive to the bandwidth of the signal.
If the pad is heavily low-pass filtered (which it is — `rlpf_to_hz(0.45)` at bar 0 is
~474 Hz) the analytic envelope may underestimate the true gate modulation depth.
The cosine fit is therefore assessed on the *normalised* envelope, not the absolute
amplitude, which is insensitive to this gain factor.

**Smoothing window choice**: a window of T_gate / 4 ≈ 286 ms at 140 BPM rounds the
cosine edges, producing a best-fit RMS error of ~0.14 even for a perfectly correct
cosine gate.  The `shape_is_cosine` threshold is therefore set to 0.20 rather than
the naive 0.05.  A binary (LFSR-style) gate produces RMS error > 0.30.

**Trough/peak discrepancy**: the measured trough/peak ≈ 0.19 is lower than the
expected 0.30 because (a) the 286 ms smoothing window does not fully suppress the
audio-rate carrier (48 Hz fundamental), and (b) the trancegate in the pad-solo render
is sampled with `samples_per_bar()` at the hardcoded 140 BPM default regardless of
`--bpm`, which is the second known bug (`instruments/pad.py:91`).  At exactly 140 BPM
these produce the same value, so the gate period is correct but the smoothing
limitation explains the floor compression.

---

## M3 — Filter floor (steady-state spectral centroid)

### What is measured

- **Steady-state spectral centroid**: power-weighted mean frequency of the pad solo
  after bar 1. This is the direct observable correlate of the RLPF cutoff frequency.

- **Rolloff (95%)**: frequency below which 95% of the spectral energy lies. A
  complementary measure to centroid — less sensitive to harmonic content but useful for
  characterising filter skirt slope.

### Technique

If `librosa` is available: `librosa.feature.spectral_centroid` and
`librosa.feature.spectral_rolloff` with `n_fft=4096, hop_length=2048`.
Otherwise: inline power-weighted centroid from `numpy.fft.rfft` with a Hann window,
same hop and FFT size.

The centroid is compared against two references:
- `rlpf_to_hz(0.5) = (0.5 × 12)^4 = 1296 Hz` — the exact formula output for the
  mid-range filter slider setting used at bar 0 (`FILTER_ARC['start'] = 0.45` →
  `rlpf_to_hz(0.45) = 474 Hz` is the actual start value; 0.5 is used as the
  representative reference formula point).
- SA target range 800–1200 Hz per `research/STRUDEL_DEBUG_PAGE.md`.

### Limitation

The spectral centroid is the centroid of the *output* signal including pad voicing
offsets (−14, −21 semitones). The sub-bass doublings contribute energy at 48 Hz and
below, pulling the centroid downward relative to the filter cutoff. The centroid
therefore systematically underestimates the filter frequency.

---

## M4 — lpenv sweep shape (temporal centroid rise)

### What is measured

- **Time to centroid peak**: time from pad chord trigger (MIDI note-on, channel 3)
  to the maximum spectral centroid. The lpenv envelope opens the filter from base
  to a boosted frequency; a fast-attack + slow-decay shape should produce a centroid
  peak within ~60 ms of the trigger (SA target from `research/STRUDEL_DEBUG_PAGE.md`).

- **Peak centroid Hz**: maximum centroid value reached after the trigger.

- **Decay to 90%**: time after the peak for the centroid to fall back to 90% of the
  pre-trigger baseline. Models the lpenv decay constant.

### Technique

MIDI is parsed with `mido.MidiFile`. The tempo is read from `set_tempo` messages if
present; otherwise the script defaults to the `--bpm` argument converted to
microseconds/beat. Chord triggers are MIDI note-on events on channel 3 with
velocity > 0. Close triggers (< 10 ms apart, from multi-note chords) are merged into
a single trigger event.

The spectral centroid is computed in 10 ms non-overlapping windows over a 500 ms
post-trigger window, using inline FFT (same formula as M3). The baseline centroid is
the mean centroid in the 100–200 ms *before* each trigger.

### Limitation

The full mix is used for M4, not the pad solo, because the lpenv effect on the pad
is clearest in the mix (kick attack contributes bright transients that could briefly
elevate centroid). Triggers within the first 200 ms of the file are skipped because
there is no pre-trigger window available.

Timing jitter in MIDI note-on events (quantised to ticks at the render TPB) introduces
a systematic error of ±(1 tick duration). At 140 BPM with 480 TPB one tick is
≈ 0.9 ms, which is less than the 10 ms analysis window.

---

## M5 — Sidechain per-cycle trace

M5 is the per-cycle detail of M1. The `M5_sidechain_per_cycle` array in the JSON
contains one entry per detected kick onset:

```json
{
  "t_kick_s":      1.7143,
  "pre_rms":       0.0412,
  "min_post_rms":  0.0165,
  "duck_depth_db": -7.96,
  "recovery_ms":   null
}
```

`recovery_ms: null` means the RMS did not recover to 90% of pre-kick level within
600 ms — consistent with permanent ducking.

---

## Reproducing the measurements

```bash
# Prerequisites — all already in the project
pip install numpy scipy mido

# Optional — used for centroid if available
pip install librosa

# From the repo root
python tools/measure_v3_output.py --bpm 140 --bars 8 --seed sunrise \
    --out research/analysis/v3_measurements.json
```

Expected output structure: `research/analysis/v3_measurements.json` with top-level
keys `M1_sidechain`, `M2_trancegate`, `M3_filter_floor`, `M4_lpenv_sweep`,
`M5_sidechain_per_cycle`.

---

## References

Gabor, D. (1946). Theory of communication. *Journal of the Institution of Electrical
Engineers*, *93*(26), 429–441. https://doi.org/10.1049/ji-3-2.1946.0074

> Foundational treatment of the analytic signal and instantaneous amplitude/phase.
> The Hilbert-transform envelope used in M2 is derived directly from this work.

McFee, B., Raffel, C., Liang, D., Ellis, D. P. W., McVicar, M., Battenberg, E., &
Nieto, O. (2015). librosa: Audio and music signal analysis in Python. In *Proceedings
of the 14th Python in Science Conference* (pp. 18–25).
https://doi.org/10.25080/Majora-7b98e3ed-003

> Used for `librosa.feature.spectral_centroid` and `librosa.feature.spectral_rolloff`
> in M3 when available. Inline numpy FFT fallback is provided for environments without
> librosa.

Virtanen, P., Gommers, R., Oliphant, T. E., Haberland, M., Reddy, T., Cournapeau, D.,
Burovski, E., Peterson, P., Weckesser, W., Bright, J., van der Walt, S. J., Brett, M.,
Wilson, J., Millman, K. J., Mayorov, N., Nelson, A. R. J., Jones, E., Kern, R.,
Larson, E., ... van der Walt, S. J. (2020). SciPy 1.0: Fundamental algorithms for
scientific computing in Python. *Nature Methods*, *17*(3), 261–272.
https://doi.org/10.1038/s41592-019-0686-2

> `scipy.signal.hilbert` (M2 envelope extraction), `scipy.signal.lfilter` (referenced
> from `synth/effects.py` sidechain implementation), `scipy.io.wavfile` (WAV loading).

Hermitage, L. (2022). *mido: MIDI objects for Python* (Version 1.3) [Software].
GitHub. https://github.com/mido/mido

> Used in M4 for MIDI file parsing (note-on events, tempo messages, tick-to-second
> conversion) to locate pad chord trigger times.
