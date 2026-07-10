# Plan: Rebuild `tools/compare_audio.py` as an honest perceptual similarity tool

## Context — why the current tool is lying

`compare_audio.py` reports OVERALL PASS on two audio clips that sound nothing alike. This is a design flaw, not a calibration problem.

**Measured gap (confirmed):**

| Property | Reference | Generated | Gap |
|---|---|---|---|
| Spectral centroid | 3427 Hz | 1940 Hz | ratio 0.57 — catastrophic |
| 2–4 kHz band energy | 10.3% | 0.09% | ratio 0.009 — essentially zero |
| 4 kHz+ band energy | 9.2% | 0.5% | ratio 0.054 |
| 200–500 Hz energy | 13.5% | 52.5% | ratio 3.9× — muddy |
| MFCC cosine similarity | 1.000 (self) | 0.564 | should be > 0.90 |
| MFCC DTW normalised | threshold ≤ 0.30 | **178.2** | 593× over — metric is broken |

**Why spectral_contrast scored 0.955 despite catastrophic spectral mismatch:** spectral contrast measures peak-vs-valley *shape ratios* per band. The generated file has high contrast in low-frequency bands (strong bass against quiet troughs), whose direction in vector space coincidentally aligns with the reference's overall contrast vector under cosine similarity. Cosine is direction-only — it cannot detect that the reference has contrast in the *upper* bands while the generated file has essentially zero energy there.

**Why the tool passed overall:** The PASS criterion is 3/4 High-weight metrics. Kick phase is known-broken (F2 bass bleeds). Only two real metrics needed to pass. RMS envelope (structure) and chroma (key) both pass because the rhythm and harmonic content are correct — and they are correct. But "correct structure + correct key" is a necessary, not sufficient, condition for sounding like the reference.

---

## What the research says

Surveyed: MusicGen (Copet et al., 2023), AudioLDM-2 (Liu et al., 2023), MusicLM (Agostinelli et al., 2023), "Adapting FAD" (Gui et al., 2024), LAION-CLAP (Wu et al., 2023), CDPAM (Manocha et al., 2021).

**For comparing two individual ~30s clips (our exact use case):**

- **CLAP cosine similarity** — current best practice. LAION-CLAP maps audio to a 512-dim joint audio-text embedding space trained on 630k+ hours. Cosine similarity between two audio embeddings captures semantic + timbral + structural similarity in one scalar. Gui et al. (2024) showed CLAP embeddings outperform VGGish, PANNs, EnCodec, and CDPAM for correlating with human perceptual MOS ratings of both acoustic quality and musical quality. Available: `pip install laion-clap`.

- **FAD (Fréchet Audio Distance)** — NOT applicable. Distributional metric requiring many samples. Using it on two individual clips is statistically unsound.

- **CDPAM** — validated against human triplet comparisons, but only on speech data. Not validated for music full mixes.

- **mir_eval / BSS_eval / museval** — require symbolic annotations or isolated sources. Not applicable to raw audio similarity.

- **PESQ / STOI** — speech intelligibility metrics. Inapplicable.

- **ViSQOL-Audio** — measures codec/processing degradation, not content similarity between two different musical pieces.

**Conclusion:** CLAP cosine similarity is the academically warranted approach for this task. Complement with signal-level spectral diagnostics (centroid ratio, band energy cosine) that directly explain *why* clips differ spectrally.

---

## Design: restructured `tools/compare_audio.py`

### Two-tier architecture

**Tier 1 — Perceptual similarity (gates the overall verdict)**

These answer: "does this sound like that to a human?"

| Key | Metric | Method | Target | Rationale |
|---|---|---|---|---|
| `clap_cosine` | CLAP embedding cosine | LAION-CLAP audio embeddings, cosine sim | ≥ 0.70 | Academic gold standard for music clip similarity; captures timbre + semantics + structure holistically |
| `spectral_centroid_ratio` | Brightness match | `mean(centroid_gen) / mean(centroid_ref)` | 0.70–1.30 | Directly catches missing high frequencies; current gen would score 0.566 → FAIL |
| `band_energy_cosine` | Spectral shape match | 6-band energy-% vector (0–200, 200–500, 500–1k, 1–2k, 2–4k, 4k+ Hz) → cosine | ≥ 0.85 | Detects missing frequency shelves; current gen would score ≈ 0.30 → FAIL |
| `mfcc_cosine` | Timbral fingerprint | Mean 13-coeff MFCC vector cosine (replaces broken DTW) | ≥ 0.80 | Well-calibrated (0–1 range); current gen scores 0.564 → FAIL |

If `laion-clap` is not installed, Tier 1 uses P2–P4 only with a printed warning that semantic embedding similarity is unavailable.

**Tier 2 — Structural diagnostics (informational only)**

Keep all 7 existing metrics exactly as-is. These correctly measure rhythm, key, onset timing, and pump structure. They are *not* gates — they tell you what structural aspects are aligned or misaligned to guide synthesis iteration.

| Key | What it measures |
|---|---|
| `rms_envelope_r` | Sidechain pump phase alignment |
| `onset_xcorr_peak` | Rhythmic event timing |
| `kick_phase_err_ms` | Kick phase (known-unreliable on this song) |
| `chroma_cosine` | Harmonic key content |
| `mfcc_dtw_dist` | (Kept for continuity; reported but not used — see note) |
| `tempogram_cosine` | Rhythmic hierarchy |
| `spectral_contrast_cosine` | Kept but demoted; explained in output as unreliable |

**MFCC DTW note:** Keep the existing `_mfcc_dtw` function and its result in the output for historical continuity, but label it "(broken — do not use as gate)" in the report. The normalised cost of 178 for a ~26s clip shows the threshold of ≤ 0.30 was never calibrated against real audio. The new `mfcc_cosine` replaces it as the timbral gate.

**Overall verdict logic:**
```python
tier1_keys = ['clap_cosine', 'spectral_centroid_ratio', 'band_energy_cosine', 'mfcc_cosine']
# clap_cosine excluded from count if unavailable (not installed)
tier1_available = [k for k in tier1_keys if results[k] is not None]
tier1_passes = sum(passes[k] for k in tier1_available)
perceptual_pass = tier1_passes == len(tier1_available)  # ALL must pass

structural_high = ['rms_envelope_r', 'onset_xcorr_peak', 'kick_phase_err_ms', 'chroma_cosine']
structural_passes = sum(passes[k] for k in structural_high)
structural_pass = structural_passes >= 3  # existing logic preserved

overall_pass = perceptual_pass and structural_pass
```

---

## Implementation

### Step 0 — Move plan into repo

Copy this plan file to `docs/decisions/compare_audio_redesign.md` before making any code changes, so the reasoning is reproducible alongside the implementation.

### `tools/compare_audio.py` changes

1. **Add** `_clap_cosine(path_ref, path_gen)` — takes file paths not arrays (CLAP needs its own resampling). Try-imports laion_clap; returns `None` and prints warning if not installed. Downloads music-fine-tuned checkpoint (`music_audioset_epoch_15_esc_90.14.pt`) on first run.

2. **Add** `_spectral_centroid_ratio(y_ref, y_gen)` — scalar ratio, target in_range [0.70, 1.30].

3. **Add** `_band_energy_cosine(y_ref, y_gen)` — 6-band energy fraction vector cosine, target ≥ 0.85. Bands: 0–200, 200–500, 500–1k, 1–2k, 2–4k, 4k+ Hz using `librosa.stft` bin masking.

4. **Add** `_mfcc_cosine(y_ref, y_gen)` — mean 13-coeff MFCC vector cosine similarity. Target ≥ 0.80. Well-calibrated (0–1 range). Replaces DTW as timbral gate.

5. **Update** `_TARGETS` dict with new Tier-1 entries. Add `'in_range'` operator support alongside `'>='` and `'<='`. **Data structure:** `in_range` entries use a 4-tuple `('in_range', (low, high), weight)` — e.g. `('in_range', (0.70, 1.30), 'High')`. The pass computation loop must handle this case: `passes[key] = (low <= v <= high)`. The `None` guard must also be applied before any comparison: `passes[key] = False if v is None else <comparison>`.

6. **Update** `overall_pass` logic per above.

7. **Update** `_print_report` — two labelled sections: `── Perceptual (gates overall verdict) ──` and `── Structural diagnostics (informational) ──`. Mark `mfcc_dtw_dist` as `(broken — see mfcc_cosine)`.

8. **No signature change needed.** `compare_audio(ref_path, gen_path, bpm)` already receives file paths as its first two arguments. `_clap_cosine` receives those existing path parameters directly.

9. Return dict gains: `clap_cosine`, `spectral_centroid_ratio`, `band_energy_cosine`, `mfcc_cosine`. Existing keys unchanged.

### `docs/testing/AUDIO_SIMILARITY_METHODOLOGY.md` changes

- New sections for each Tier-1 metric with full rationale and APA 7th citations
- Updated OVERALL PASS criterion section
- Updated Known Limitations: what is still not measured (phase, stereo width, dynamics, absolute loudness, microtonality, production style)
- Document the MFCC DTW calibration failure and why it was replaced

---

## Verification

```bash
# Install CLAP
pip install laion-clap

# 1. Sanity: ref vs itself — all Tier-1 scores must be ~1.0 / in-range, OVERALL PASS
python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav \
    research/reference_audio/hey_angel_trimmed.wav --bpm 140.0534

# 2. CLAP threshold calibration — measure actual score on current cover first,
#    then use that to confirm ≥ 0.70 is the right cut.
#    Expected CLAP score on /tmp/ha_v32.wav vs reference: likely 0.3–0.5 (catastrophic mismatch).
#    If ref-vs-ref = 1.0 and cover = ~0.4, the 0.70 threshold correctly separates them.
#    If the gap is smaller than expected, adjust threshold before shipping.

# 3. Current cover — must FAIL on all Tier-1 metrics
python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav \
    /tmp/ha_v32.wav --bpm 140.0534

# Expected: centroid_ratio=0.566 FAIL, band_energy_cosine≈0.30 FAIL,
#           mfcc_cosine=0.564 FAIL, clap_cosine<0.70 FAIL, OVERALL FAIL
```

After the tool is honest, the synthesis iteration resumes: fix `SmoothLead` cutoff (currently 900 Hz, needs to pass harmonics to ~3–4 kHz), then re-run compare_audio to get real feedback. That is a separate task.

---

## Citations (APA 7th, required by CLAUDE.md)

Wu, Y., Chen, K., Zhang, T., Hui, Y., Berg-Kirkpatrick, T., & Dubnov, S. (2023). Large-scale contrastive language-audio pretraining with feature fusion and keyword-to-caption augmentation. In *Proceedings of the IEEE International Conference on Acoustics, Speech and Signal Processing* (pp. 1–5). IEEE. https://doi.org/10.1109/ICASSP49357.2023.10095969

Gui, H., Evans, N., & Wisdom, S. (2024). Adapting Fréchet audio distance for generative music evaluation. *arXiv preprint*. https://arxiv.org/abs/2311.01616

Copet, J., Kreuk, F., Gat, I., Remez, T., Kant, D., Synnaeve, G., Adi, Y., & Défossez, A. (2023). Simple and controllable music generation. In *Advances in Neural Information Processing Systems*, *36*. https://arxiv.org/abs/2306.05284

Manocha, P., Finkelstein, A., Zhang, R., Bryan, N. J., Mysore, G. J., & Jin, Z. (2021). CDPAM: Contrastive learning for perceptual audio similarity. In *Proceedings of the IEEE International Conference on Acoustics, Speech and Signal Processing* (pp. 196–200). IEEE. https://arxiv.org/abs/2102.05109

Kilgour, K., Zuluaga, M., Roblek, D., & Sharifi, M. (2019). Fréchet audio distance: A reference-free metric for evaluating music enhancement algorithms. In *Proceedings of Interspeech 2019* (pp. 2350–2354). https://arxiv.org/abs/1812.08466

Davis, S., & Mermelstein, P. (1980). Comparison of parametric representations for monosyllabic word recognition. *IEEE Transactions on Acoustics, Speech, and Signal Processing*, *28*(4), 357–366. https://doi.org/10.1109/TASSP.1980.1163420

McFee, B., Raffel, C., Liang, D., Ellis, D. P. W., McVicar, M., Battenberg, E., & Nieto, O. (2015). librosa: Audio and music signal analysis in Python. In *Proceedings of the 14th Python in Science Conference* (pp. 18–24). https://doi.org/10.25080/Majora-7b98e3ed-003
