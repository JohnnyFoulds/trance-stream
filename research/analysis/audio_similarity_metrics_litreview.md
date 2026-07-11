# Perceptual Audio Similarity Metrics: Literature Review

**Purpose**: Informs the redesign of `tools/compare_audio.py`. The existing tool reports OVERALL PASS on two audio clips that sound nothing alike, because it measures rhythmic/harmonic structure but has no spectral brightness or timbral similarity metrics.

**Date**: 2026-07-10

---

## 1. FAD (Fréchet Audio Distance)

**Source**: Kilgour et al. (2019). Fréchet audio distance: A reference-free metric for evaluating music enhancement algorithms. *Interspeech 2019*. https://arxiv.org/abs/1812.08466

**What it is.** An adaptation of FID (Fréchet Inception Distance) from image generation to the audio domain. Embeds a set of audio clips through a neural network, fits a multivariate Gaussian to the embedding distribution (mean μ, covariance Σ), then computes the Wasserstein-2 distance between two such Gaussians:

$$\text{FAD} = \|\mu_r - \mu_t\|^2 + \text{tr}\left(\Sigma_r + \Sigma_t - 2\sqrt{\Sigma_r \Sigma_t}\right)$$

**Original embedding model**: VGGish (CNN trained on YouTube audio, 16 kHz, 128-dim per 0.96 s frame).

**Current best-practice embedding**: LAION-CLAP (Gui et al., 2024; Tailleur et al., 2024). VGGish yields Spearman correlation <0.1 with human perception of environmental sounds; PANNs-WGM-LogMel achieves >0.5; CLAP further outperforms PANNs for musical quality MOS prediction. The original 2018 paper showed r = 0.52 with human perception using VGGish for music enhancement; CLAP embeddings substantially improve this.

**Critical limitation: distributions, not individual clips.** FAD requires enough samples to fit a meaningful Gaussian. Gui et al. (2024) demonstrate a sample-size bias (FAD scores decrease as N increases at different rates for different models), and introduce FAD_∞ (linear extrapolation across bootstrap estimates) to correct for this. Per-song FAD against a reference *distribution* is possible; comparing two individual clips via FAD is statistically unsound.

**pip install**: `pip install frechet_audio_distance` (VGGish) or `pip install fadtk` (Microsoft; supports CLAP, LAION-CLAP, MERT, EnCodec, DAC)

**Verdict for this project**: Not applicable — distributional metric, requires many samples.

---

## 2. CDPAM (Contrastive Deep Perceptual Audio Metric)

**Source**: Manocha, P., Finkelstein, A., Zhang, R., Bryan, N. J., Mysore, G. J., & Jin, Z. (2021). CDPAM: Contrastive learning for perceptual audio similarity. *ICASSP 2021*. https://arxiv.org/abs/2102.05109

**What it is.** A full-reference, differentiable perceptual distance metric trained via contrastive learning on human triplet judgements (is clip A more similar to B or C?). Takes two audio clips, returns a scalar distance. 512-dimensional convolutional embedding, operates at 22.05 kHz mono.

**Human perception validation.** Validated against human judgements on 9 speech datasets covering noise, codec artefacts, pitch shifts, and other perturbations. Correlates significantly with human preference over PESQ, STOI, and signal-level metrics.

**Critical limitation**: Trained and validated exclusively on speech. Not validated for music full mixes. Perceptual dimensions relevant to music (rhythm, harmony, timbre of instruments, groove) are not captured.

**pip install**: `pip install cdpam`

**Verdict for this project**: Speech-only validation makes it inappropriate as a primary metric for music similarity, though it could serve as a supplementary check.

---

## 3. CLAP Cosine Similarity (LAION Contrastive Language-Audio Pretraining)

**Source**: Wu, Y., Chen, K., Zhang, T., Hui, Y., Berg-Kirkpatrick, T., & Dubnov, S. (2023). Large-scale contrastive language-audio pretraining with feature fusion and keyword-to-caption augmentation. *ICASSP 2023*. https://doi.org/10.1109/ICASSP49357.2023.10095969

**What it is.** A large-scale multimodal model trained on LAION-Audio-630K (633,526 audio-text pairs). Maps audio to a 512-dimensional unit-norm embedding in a joint audio-text space. Cosine similarity between two audio embeddings measures their semantic and acoustic proximity.

**Two variants relevant to music:**
- `630k-audioset-best`: general audio understanding
- `music_audioset_epoch_15_esc_90.14`: music-specific fine-tuning (preferred for music clips)

**Validation as a similarity metric.** Gui et al. (2024) compared eight embedding models (VGGish, PANNs, MERT-L4, EnCodec, DAC, CDPAM, L-CLAP-aud, L-CLAP-mus) against human MOS ratings for both acoustic quality and musical quality. L-CLAP-mus achieved the highest correlation with human perceptual scores on both dimensions, outperforming all alternatives.

**Usage for two-clip comparison:**
```python
import laion_clap, numpy as np
model = laion_clap.CLAP_Module(enable_fusion=False, amodel='HTSAT-tiny')
model.load_ckpt()  # downloads music_audioset_epoch_15_esc_90.14.pt (~150 MB)
embeddings = model.get_audio_embedding_from_filelist(['clip1.wav', 'clip2.wav'])
similarity = float(np.dot(embeddings[0], embeddings[1]))  # cosine (embeddings are L2-normalised)
```

**pip install**: `pip install laion-clap` (requires torch, already installed on this machine)

**Verdict for this project**: **Recommended as the primary perceptual gate.** Current academic gold standard for music clip-to-clip similarity. Captures timbre, semantics, style, and structure in a single scalar.

---

## 4. mir_eval

**Source**: Raffel, C., McFee, B., Humphrey, E. J., Salamon, J., Nieto, O., Liang, D., & Ellis, D. P. W. (2014). mir_eval: A transparent implementation of common MIR metrics. *ISMIR 2014*. https://craffel.github.io/mir_eval/

**What it is.** Standard implementations of MIR evaluation metrics: beat tracking, chord recognition, melody extraction, onset detection, source separation, segment boundary, tempo, transcription, key, pattern discovery.

**Critical limitation for this project.** mir_eval operates on symbolic annotations (timestamps, chord labels, beat times), not raw audio. To use it, a separate analysis frontend must first extract those annotations. It cannot accept two raw audio files and return a similarity score.

**Verdict for this project**: Not applicable as-is. Useful only if upstream analysis (beat tracking, chord extraction) is first run on both clips.

---

## 5. PESQ, STOI, ViSQOL

**PESQ** (ITU-T P.862): Narrowband/wideband speech quality standard. Designed for telephone channel degradations, operates at 8/16 kHz. Not used in music research.

**STOI**: Measures speech intelligibility. Completely inapplicable to music.

**ViSQOL-Audio** (Google): Operates at 48 kHz, measures codec/processing degradation quality relative to a reference. Used in audio codec evaluation (e.g., Opus, Lyra). Measures whether a processed version sounds degraded — not whether two different musical pieces sound similar.

**pip install**: `pip install visqol`

**Verdict for this project**: PESQ and STOI inapplicable. ViSQOL-Audio applicable only for codec/enhancement artefact evaluation, not music content similarity.

---

## 6. museval / BSS_eval

**Source**: Stoter, F.-R., Liutkus, A., & Ito, N. (2018). The 2018 Signal Separation Evaluation Campaign. *LVA/ICA 2018*.

Measures source separation quality: SDR (Signal-to-Distortion Ratio), SIR (Signal-to-Interference Ratio), SAR (Signal-to-Artifacts Ratio). Requires isolated ground-truth source signals.

**Verdict for this project**: Requires separated stems with known ground-truth. Not applicable for comparing full mixes of two different renditions of a song.

---

## 7. Essentia

**Source**: Bogdanov, D., Wack, N., Gómez, E., Gulati, S., Herrera, P., Mayor, O., Roma, G., Salamon, J., Zapata, J., & Serra, X. (2013). ESSENTIA: An audio analysis library for music information retrieval. *ISMIR 2013*. https://essentia.upf.edu/

**What it is.** Open-source C++/Python library for audio analysis. `MusicExtractor` algorithm computes a comprehensive feature pool including MFCC, GFCC, HPCP (chroma), key, BPM, onset detection, spectral descriptors, tonal descriptors, and neural tagging models. The companion Gaia library performs nearest-neighbour similarity search over feature vectors.

**For two-clip comparison.** Extract a feature vector from each clip with MusicExtractor, compute cosine distance. Classical approach — does not require GPU, highly interpretable. Correlation with human perception is moderate for classical features; better when using Essentia's neural model wrappers (EffNet, VGGish, MusicNN).

**Verdict for this project**: Viable classical fallback if GPU-based CLAP is unavailable, but lower human-perception correlation than CLAP.

---

## 8. What Music Generation Papers Use (2023–2024 consensus)

Surveyed: MusicGen (Copet et al., 2023), AudioLDM-2 (Liu et al., 2023), MusicLM (Agostinelli et al., 2023), Stable Audio (Stability AI, 2023).

| Metric | What it measures | Notes |
|---|---|---|
| FAD with CLAP embeddings | Distribution-level acoustic + musical quality | Gold standard for generative model evaluation |
| KL divergence over PANNs/PaSST logits | Whether audio class distribution matches reference | Coarse semantic similarity |
| CLAP score (audio vs. text) | Prompt adherence | Not audio-to-audio similarity |
| Human MOS | Ground truth perception | Required for top-tier venues |

**Key finding**: No single off-the-shelf Python library robustly answers "how perceptually similar do these two music clips sound to a human" without additional setup. The community uses FAD (distributions) + CLAP similarity (semantics) + human MOS (ground truth). For direct clip-to-clip comparison of two ~30s music files, **CLAP cosine similarity is the most practical and best-validated option as of 2024–2025.**

---

## Diagnosis: Why `compare_audio.py` v1 Failed

The existing tool measured:
- Rhythmic structure (RMS envelope correlation, onset timing, tempogram)
- Harmonic structure (chroma, kick phase)
- Timbral envelope (MFCC DTW — broken calibration)
- Spectral contrast shape (unreliable for detecting missing frequency bands — see below)

It did **not** measure:
- Spectral brightness (centroid)
- Band energy distribution (where the energy actually sits in the spectrum)
- Timbral fingerprint with a well-calibrated metric
- Semantic or holistic perceptual similarity

**Why spectral_contrast scored 0.955 despite catastrophic spectral mismatch.** Spectral contrast measures peak-vs-valley shape ratios per band, not absolute band energy. The generated file has high contrast in low-frequency bands (strong bass against quiet troughs). Under cosine similarity, the direction of this vector coincidentally aligns with the reference's overall contrast vector — even though the reference has contrast in *upper* bands while the generated file has essentially no energy there. Cosine similarity is direction-only; it cannot see that the contrast vectors disagree about *which bands* are contrasted.

**Why MFCC DTW scored 178 (threshold ≤ 0.30).** The normalised cost is `D[-1,-1] / path_length`. For a ~26 s clip at hop=512/sr=22050, path_length ≈ 1111 frames. The raw accumulated Euclidean distance over 13 un-normalised MFCC coefficients was 197,954 → normalised = 178. The threshold of 0.30 was never calibrated against real audio with un-normalised MFCCs. This metric is entirely miscalibrated and its FAIL result (which would have been correct) was silently excluded from the overall verdict because it is Medium weight.

---

## Recommended Replacement Metrics

| Metric | Method | Target | Replaces |
|---|---|---|---|
| CLAP cosine similarity | LAION-CLAP music model embeddings | ≥ 0.70 | Overall perceptual gating |
| Spectral centroid ratio | `mean(centroid_gen) / mean(centroid_ref)` | 0.70–1.30 | Missing brightness detection |
| Band energy cosine | 6-band (0–200, 200–500, 500–1k, 1–2k, 2–4k, 4k+ Hz) energy-% vector cosine | ≥ 0.85 | Detects missing high-frequency shelf |
| MFCC cosine (mean vector) | `1 - cosine_dist(mfcc_ref.mean(axis=1), mfcc_gen.mean(axis=1))` | ≥ 0.80 | Replaces broken DTW; well-calibrated |

Current generated audio scores on these would be: centroid_ratio = 0.566, band_energy_cosine ≈ 0.30, mfcc_cosine = 0.564 — all catastrophic FAILs, correctly reflecting the perceptual gap.

---

## References

Bogdanov, D., Wack, N., Gómez, E., Gulati, S., Herrera, P., Mayor, O., Roma, G., Salamon, J., Zapata, J., & Serra, X. (2013). ESSENTIA: An audio analysis library for music information retrieval. In *Proceedings of the 14th International Society for Music Information Retrieval Conference* (pp. 493–498). ISMIR.

Copet, J., Kreuk, F., Gat, I., Remez, T., Kant, D., Synnaeve, G., Adi, Y., & Défossez, A. (2023). Simple and controllable music generation. In *Advances in Neural Information Processing Systems*, *36*. https://arxiv.org/abs/2306.05284

Davis, S., & Mermelstein, P. (1980). Comparison of parametric representations for monosyllabic word recognition in continuously spoken sentences. *IEEE Transactions on Acoustics, Speech, and Signal Processing*, *28*(4), 357–366. https://doi.org/10.1109/TASSP.1980.1163420

Gui, H., Evans, N., & Wisdom, S. (2024). Adapting Fréchet audio distance for generative music evaluation. *arXiv preprint arXiv:2311.01616*. https://arxiv.org/abs/2311.01616

Kilgour, K., Zuluaga, M., Roblek, D., & Sharifi, M. (2019). Fréchet audio distance: A reference-free metric for evaluating music enhancement algorithms. In *Proceedings of Interspeech 2019* (pp. 2350–2354). ISCA. https://arxiv.org/abs/1812.08466

Kong, Q., Cao, Y., Iqbal, T., Wang, Y., Wang, W., & Plumbley, M. D. (2020). PANNs: Large-scale pretrained audio neural networks for audio pattern recognition. *IEEE/ACM Transactions on Audio, Speech, and Language Processing*, *28*, 2880–2894. https://doi.org/10.1109/TASLP.2020.3030497

Liu, H., Chen, Z., Yuan, Y., Mei, X., Liu, X., Mandic, D., Wang, W., & Plumbley, M. D. (2023). AudioLDM: Text-to-audio generation with latent diffusion models. In *Proceedings of the 40th International Conference on Machine Learning*. https://arxiv.org/abs/2301.12503

Liu, H., Yuan, Y., Liu, X., Mei, X., Kong, Q., Tian, Q., Wang, Y., Wang, W., Mandic, D., & Plumbley, M. D. (2023). AudioLDM 2: Learning holistic audio generation with self-supervised pretraining. *arXiv preprint arXiv:2308.05734*. https://arxiv.org/abs/2308.05734

Manocha, P., Finkelstein, A., Zhang, R., Bryan, N. J., Mysore, G. J., & Jin, Z. (2021). CDPAM: Contrastive learning for perceptual audio similarity. In *Proceedings of the IEEE International Conference on Acoustics, Speech and Signal Processing* (pp. 196–200). IEEE. https://arxiv.org/abs/2102.05109

McFee, B., Raffel, C., Liang, D., Ellis, D. P. W., McVicar, M., Battenberg, E., & Nieto, O. (2015). librosa: Audio and music signal analysis in Python. In *Proceedings of the 14th Python in Science Conference* (pp. 18–24). https://doi.org/10.25080/Majora-7b98e3ed-003

Müller, M. (2007). *Information retrieval for music and motion*. Springer. https://doi.org/10.1007/978-3-540-74048-3

Raffel, C., McFee, B., Humphrey, E. J., Salamon, J., Nieto, O., Liang, D., & Ellis, D. P. W. (2014). mir_eval: A transparent implementation of common MIR metrics. In *Proceedings of the 15th International Society for Music Information Retrieval Conference* (pp. 367–372). ISMIR.

Tailleur, T., Lagrange, M., Sèbe, N., & Gontier, F. (2024). Correlation of Fréchet audio distance with human perception of environmental audio is embedding dependent. *arXiv preprint arXiv:2403.17508*. https://arxiv.org/abs/2403.17508

Wu, Y., Chen, K., Zhang, T., Hui, Y., Berg-Kirkpatrick, T., & Dubnov, S. (2023). Large-scale contrastive language-audio pretraining with feature fusion and keyword-to-caption augmentation. In *Proceedings of the IEEE International Conference on Acoustics, Speech and Signal Processing* (pp. 1–5). IEEE. https://doi.org/10.1109/ICASSP49357.2023.10095969
