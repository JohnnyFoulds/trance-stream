# Audio Similarity Methodology

**Tool**: `tools/compare_audio.py`  
**Purpose**: Determine whether a synthesised cover WAV sounds like a reference recording.  
**Architecture decision**: `docs/decisions/compare_audio_redesign.md`

---

## 1. Problem Statement

The original tool (v1) measured rhythmic and harmonic structure correctly but reported OVERALL PASS on two audio clips that sound nothing alike. The root cause was the absence of any spectral or perceptual similarity gate. It was possible to pass with just two structural metrics (RMS envelope and chroma) while exhibiting catastrophic spectral mismatch (generated spectral centroid 1,940 Hz vs reference 3,427 Hz; virtually no energy above 1 kHz in the generated file).

The redesigned tool uses a **two-tier architecture** that separates perceptual similarity (which gates the verdict) from structural diagnostics (which guide synthesis iteration).

---

## 2. Architecture: Two-Tier Design

### Tier 1 — Perceptual Similarity (gates overall verdict)

All available Tier-1 metrics must pass for OVERALL PASS. These answer: "does this sound like that to a human listener?"

### Tier 2 — Structural Diagnostics (informational only)

These metrics correctly measure rhythm, onset timing, harmonic key, and energy trajectory. They do not gate the verdict. Their purpose is to indicate *where* synthesis needs iteration: is the rhythm right but the timbre wrong, or vice versa?

**Overall verdict logic:**
```python
tier1_available = [k for k in tier1_keys if values[k] is not None]
perceptual_pass = all(passes[k] for k in tier1_available)
structural_pass = sum(passes[k] for k in structural_high) >= 3
overall_pass    = perceptual_pass and structural_pass
```

---

## 3. Tier-1 Metrics

### 3.1 CLAP Cosine Similarity (Tier 1)

**What it measures**: Holistic perceptual similarity — timbre, semantics, style, and structure in a single scalar.

**Method**: Both audio files are embedded using LAION-CLAP (Wu et al., 2023), a transformer model trained on 633,526 audio-text pairs. Embeddings are L2-normalised 512-dimensional vectors; cosine similarity equals their dot product. Uses the music-fine-tuned checkpoint `music_audioset_epoch_15_esc_90.14.pt` via `laion_clap.CLAP_Module(enable_fusion=False, amodel='HTSAT-tiny')`.

**Academic validation**: Gui et al. (2024) compared eight embedding models — VGGish, PANNs, MERT-L4, EnCodec, DAC, CDPAM, L-CLAP-audio, and L-CLAP-music — against human MOS ratings for both acoustic quality and musical quality. L-CLAP-music achieved the highest Spearman correlation with human perceptual scores on both dimensions, outperforming all alternatives including CDPAM and PANNs. This makes it the current academic gold standard for music clip-to-clip similarity as of 2024–2025.

**Calibration**: Reference vs itself = 0.981; reference vs v32 cover (catastrophic spectral mismatch) = 0.385. The 0.70 threshold cleanly separates these.

**Availability**: Requires `pip install laion-clap torchvision`. If not installed, the metric returns `None` and the OVERALL verdict is computed from the remaining three Tier-1 metrics with a printed warning.

**Target**: ≥ 0.70

### 3.2 Spectral Centroid Ratio (Tier 1)

**What it measures**: Relative spectral brightness — whether the generated file is as bright (or dark) as the reference.

**Method**: `librosa.feature.spectral_centroid` computes the weighted mean frequency of the power spectrum per frame. The ratio `mean(centroid_gen) / mean(centroid_ref)` is a dimensionless brightness ratio independent of absolute loudness.

**Why it matters**: A synthesised cover can have correct rhythm and harmony but use a low-pass filter that kills all energy above 1 kHz. Aggregate statistics (chroma, tempogram) will not catch this; the centroid ratio catches it directly. Measured gap: gen/ref = 1,940/3,427 = 0.566 — catastrophic.

**Target**: 0.70–1.30 (ratio within ±30% of reference brightness)

### 3.3 6-Band Energy Cosine (Tier 1)

**What it measures**: Match of the spectral energy distribution across six perceptually motivated frequency bands.

**Method**: STFT power spectrum binned into six bands (0–200, 200–500, 500–1k, 1–2k, 2–4k, 4k+ Hz) using `librosa.stft` frequency masking. Each file's energy is converted to fractional values (summing to 1.0), then cosine similarity is computed between the two 6-element vectors.

**Why fractions, not absolute energy**: Normalising to fractions makes the metric loudness-invariant; it measures *shape* of the spectral distribution. A file that is identical but 6 dB quieter scores 1.0. A file missing the top two bands scores near 0.30.

**Why this catches what spectral_contrast_cosine misses**: Spectral contrast measures peak-vs-valley *shape ratios* per band, not energy fractions. Under cosine similarity it is direction-only — the generated file's high low-band contrast vector happened to align directionally with the reference's full-band contrast vector, scoring 0.955 despite having essentially zero energy above 1 kHz. Band energy cosine uses actual energy fractions, so missing bands score as missing.

**Target**: ≥ 0.85

### 3.4 MFCC Cosine (Tier 1)

**What it measures**: Timbral fingerprint similarity — does the generated file have the same characteristic sound colour as the reference?

**Method**: `librosa.feature.mfcc(n_mfcc=13)` on both files, mean collapsed over the time axis, cosine similarity between the two 13-element mean vectors (Davis & Mermelstein, 1980; McFee et al., 2015).

**Why this replaces MFCC DTW**: The DTW normalised cost was miscalibrated — threshold 0.30 was set without ever being measured against real audio. For a ~26s clip at hop=512/sr=22050 (≈1,111 frames), the raw accumulated Euclidean distance over 13 un-normalised MFCC coefficients is in the range 100,000–200,000; normalising by path length gives ≈170. The threshold of 0.30 is 593× off. The DTW metric is kept in Tier-2 output for historical continuity but labelled as broken.

**MFCC cosine is well-calibrated**: The 0–1 range is intrinsic (cosine similarity is bounded). Self-similarity = 1.000. Catastrophic mismatch ≈ 0.564.

**Target**: ≥ 0.80

---

## 4. Tier-2 Structural Diagnostics

All metrics are unchanged from v1. They are reported but do not gate the overall verdict.

### 4.1 RMS Envelope Pearson r (High)

**What it measures**: Whether energy rises, falls, and pumps at the same moments.

**Method**: `librosa.feature.rms(hop_length=512)`. Both envelopes truncated to the shorter length, compared with `scipy.stats.pearsonr`.

**Target**: r ≥ 0.70

### 4.2 Onset Cross-Correlation Peak (High)

**What it measures**: Whether rhythmic events land at the same times.

**Method**: `librosa.onset.onset_strength(hop_length=512)` on both files, zero-mean unit-variance normalised, `scipy.signal.correlate(mode='full')`. Reports normalised peak value and lag in ms.

**Target**: peak ≥ 0.40, lag within ±20ms (lag is informational, not gated)

### 4.3 Kick Phase Alignment (High)

**What it measures**: Whether the kick drum lands at the same beat phase within the half-note period.

**Method**: Bandpass 50–120 Hz, onset detection, `kick_times mod half_note_period`, mean phase comparison.

**Known limitation on this song**: F2 bass (87 Hz) bleeds into the 50–120 Hz bandpass and re-triggers phase detection. This metric is unreliable for hey_angel. Kept for other songs where this bleed does not occur.

**Target**: mean absolute phase error ≤ 30ms

### 4.4 Chroma Cosine (High)

**What it measures**: Whether both files are in the same key with similar harmonic content.

**Method**: Harmonic/percussive separation (`librosa.effects.harmonic(margin=8)`), `librosa.feature.chroma_cens(hop_length=512).mean(axis=1)`, cosine similarity (Müller & Ewert, 2011).

**Target**: ≥ 0.80

### 4.5 MFCC DTW Distance (Medium — broken, do not use as gate)

**What it measures**: Timbral trajectory similarity over time (intended).

**Why it is broken**: Threshold 0.30 was never calibrated against real audio. Actual normalised cost for a 26s dissimilar pair: 173.3. See §3.4 for diagnosis. Kept for historical continuity; replaced by `mfcc_cosine` as the timbral gate.

### 4.6 Tempogram Cosine (Medium)

**What it measures**: Similarity of the full rhythmic hierarchy — dominant BPM, half-time feel, double-time hi-hats.

**Method**: `librosa.feature.tempogram` on onset strength, mean across time, cosine similarity.

**Target**: ≥ 0.80

### 4.7 Spectral Contrast Cosine (Medium — unreliable for missing frequency bands)

**What it measures**: Peak-vs-valley shape ratios per sub-band (intended to measure perceived punch/presence).

**Why it is unreliable for detecting missing bands**: Spectral contrast is direction-only under cosine similarity. The generated file scored 0.955 despite having essentially zero energy above 1 kHz, because its high low-band contrast vector happened to align directionally with the reference's vector. Use `band_energy_cosine` instead for detecting missing frequency shelves.

**Target**: ≥ 0.70 (informational)

---

## 5. Overall Pass Criterion

A cover **passes** if and only if:
1. **All available Tier-1 perceptual metrics pass** their individual targets, AND
2. **At least 3 of 4 High-weight structural metrics pass** (RMS envelope r, onset cross-corr, kick phase, chroma cosine)

If CLAP is unavailable (laion-clap not installed), Tier-1 is evaluated on the remaining three metrics with a warning.

---

## 6. How to Run

```bash
# Install perceptual dependencies (first run downloads ~150 MB CLAP checkpoint)
pip install laion-clap torchvision

# Sanity check: ref vs itself — all Tier-1 must be ~1.0, OVERALL PASS
python tools/compare_audio.py reference.wav reference.wav --bpm 140.0534

# Cover evaluation
python tools/compare_audio.py reference.wav generated.wav --bpm 140.0534

# Exit code: 0 = PASS, 1 = FAIL
```

---

## 7. Known Limitations

- **CLAP model verbosity**: The `load_ckpt()` call prints every weight tensor name during loading (~300 lines). This is upstream library behaviour; it does not affect correctness.
- **CLAP first-run download**: Downloads `music_audioset_epoch_15_esc_90.14.pt` (~150 MB) on first run. Subsequent runs use the cached checkpoint.
- **Length mismatch**: Files are internally truncated to the shorter length for envelope and spectral metrics. If the generated file is substantially shorter, metrics may be computed over a non-representative window.
- **Tempo drift**: DTW handles small drift; other metrics assume both files are at the same BPM. Significant BPM mismatch will cause onset cross-correlation lag to be large.
- **Not measured**: Phase coherence, stereo width, absolute loudness, microtonality, production EQ curve, reverb tail similarity, dynamic range.

---

## 8. References

Davis, S., & Mermelstein, P. (1980). Comparison of parametric representations for monosyllabic word recognition in continuously spoken sentences. *IEEE Transactions on Acoustics, Speech, and Signal Processing*, *28*(4), 357–366. https://doi.org/10.1109/TASSP.1980.1163420

Fujishima, T. (1999). Realtime chord recognition of musical sound: A system using Common Lisp Music. In *Proceedings of the International Computer Music Conference* (pp. 464–467). International Computer Music Association.

Gui, H., Evans, N., & Wisdom, S. (2024). Adapting Fréchet audio distance for generative music evaluation. *arXiv preprint arXiv:2311.01616*. https://arxiv.org/abs/2311.01616

McFee, B., Raffel, C., Liang, D., Ellis, D. P. W., McVicar, M., Battenberg, E., & Nieto, O. (2015). librosa: Audio and music signal analysis in Python. In *Proceedings of the 14th Python in Science Conference* (pp. 18–24). https://doi.org/10.25080/Majora-7b98e3ed-003

Müller, M. (2007). *Information retrieval for music and motion*. Springer. https://doi.org/10.1007/978-3-540-74048-3

Müller, M., & Ewert, S. (2011). Chroma Toolbox: MATLAB implementations of various chroma feature representations. In *Proceedings of the 12th International Society for Music Information Retrieval Conference* (pp. 215–220). ISMIR.

Wu, Y., Chen, K., Zhang, T., Hui, Y., Berg-Kirkpatrick, T., & Dubnov, S. (2023). Large-scale contrastive language-audio pretraining with feature fusion and keyword-to-caption augmentation. In *Proceedings of the IEEE International Conference on Acoustics, Speech and Signal Processing* (pp. 1–5). IEEE. https://doi.org/10.1109/ICASSP49357.2023.10095969
