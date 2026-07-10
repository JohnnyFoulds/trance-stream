# Audio Similarity Methodology

**Tool**: `tools/compare_audio.py`  
**Purpose**: Determine whether a synthesised cover WAV sounds like a reference recording.

---

## 1. Problem Statement

Aggregate per-file statistics (spectral centroid, band energy ratios, ZCR) are insufficient for evaluating whether a synthesised cover sounds like a reference. A track can match the reference on every aggregate statistic while being completely wrong dynamically — e.g., loud when the reference is quiet, quiet when it is loud, or rhythmically offset by a full second.

The fundamental requirement is **temporal fidelity**: the right sounds must happen at the right times.

---

## 2. Metrics and Rationale

All metrics operate on both files loaded to mono float32 at 22050 Hz (`librosa.load`). This normalises sample rate differences before any comparison.

### 2.1 RMS Envelope Pearson r (High weight)

**What it measures**: Whether energy rises, falls, and pumps at the same moments in both files.

**Method**: `librosa.feature.rms(hop_length=512)` produces one RMS value per 23ms hop. Both envelopes are truncated to the shorter length and compared with `scipy.stats.pearsonr`.

**Why it matters**: A trance sidechain pump — the defining rhythmic feature of the genre — appears as a periodic oscillation in the RMS envelope. If the generated cover has its pump at different times to the reference, Pearson r will be near zero or negative regardless of how similar the sounds are in isolation.

**Target**: r ≥ 0.70

### 2.2 Onset Cross-Correlation Peak (High weight)

**What it measures**: Whether rhythmic events (note onsets, transients) land at the same times.

**Method**: `librosa.onset.onset_strength(hop_length=512)` on both files, zero-mean unit-variance normalised, then `scipy.signal.correlate(mode='full')`. The normalised peak value and its lag are reported.

**Why it matters**: Onset strength captures all rhythmic events — kick, hi-hat, note attacks — simultaneously. A lag near zero with a high peak means events are time-aligned. A lag of +1161ms means our arrangement is offset by over a second.

**Target**: peak ≥ 0.40, lag within ±20ms

### 2.3 Kick Phase Alignment (High weight)

**What it measures**: Whether the kick drum lands at the same beat phase.

**Method**: Bandpass filter 50–120 Hz on both files, `librosa.onset.onset_detect`, compute `kick_times mod half_note_period`, compare mean phases.

**Why it matters**: In half-time trance at 138 BPM, the kick lands every 869ms. If our kick is offset by even 50ms within that period, the groove feels wrong regardless of all other content.

**Target**: mean absolute phase error ≤ 30ms

### 2.4 Chroma Cosine Similarity (High weight)

**What it measures**: Whether both files are in the same key with similar harmonic content.

**Method**: Harmonic/percussive separation (`librosa.effects.harmonic(margin=8)`) suppresses rhythmic content, then `librosa.feature.chroma_cens(hop_length=512).mean(axis=1)` produces a 12-element pitch-class distribution. Cosine similarity via `scipy.spatial.distance.cosine`.

`chroma_cens` (chroma energy normalised statistics) is used rather than raw chroma — it is more robust to tuning differences and transient artefacts (Müller & Ewert, 2011).

**Target**: ≥ 0.80

### 2.5 MFCC DTW Distance (Medium weight)

**What it measures**: Timbral trajectory similarity over time, handling small tempo drift.

**Method**: `librosa.feature.mfcc(n_mfcc=13, hop_length=512)` on both files. Dynamic time warping via `librosa.sequence.dtw` (Müller, 2007). Normalised cost = `D[-1,-1] / path_length`.

**Why this is better than mean-collapsed MFCC cosine**: The `.mean(axis=1)` approach used in the existing `health_check.py` discards all temporal information. A track with the correct average timbre but wrong temporal structure scores the same as a correct cover. DTW preserves the trajectory.

**Target**: normalised distance ≤ 0.30

### 2.6 Tempogram Cosine (Medium weight)

**What it measures**: Similarity of the full rhythmic hierarchy — not just the dominant BPM, but also half-time, double-time, and sub-beat periodicities.

**Method**: `librosa.feature.tempogram` on the onset strength envelope from both files, mean across time, cosine similarity.

**Why it matters**: "Hey Angel" has a half-time feel — the listener perceives ~69 BPM but the grid is 138. The tempogram captures this relationship. A cover that runs four-on-floor at 138 would score differently than the correct half-time feel.

**Target**: ≥ 0.80

### 2.7 Spectral Contrast Cosine (Medium weight)

**What it measures**: Perceived presence and punch per frequency band.

**Method**: `librosa.feature.spectral_contrast(n_bands=6, hop_length=512)` measures the difference between spectral peaks and valleys within 6 sub-bands. More correlated with perceptual presence than raw band energy. Mean across time → 7-element vector → cosine similarity.

**Target**: ≥ 0.70

---

## 3. Overall Pass Criterion

A cover **passes** if the majority of high-weight metrics (RMS envelope r, onset cross-correlation, kick phase alignment, chroma cosine) individually pass their targets. Medium-weight metrics are reported but do not gate the overall verdict.

---

## 4. How to Run

```bash
# Sanity check (file vs itself — all scores should be ~1.0)
python tools/compare_audio.py reference.wav reference.wav --bpm 138

# Cover evaluation
python tools/compare_audio.py reference.wav generated.wav --bpm 138

# Exit code: 0 = PASS, 1 = FAIL
```

---

## 5. Known Limitations

- **Length mismatch**: Files are truncated to the shorter length for envelope correlation. If the generated file is much shorter, metrics may be computed over a non-representative window.
- **Tempo drift**: DTW handles small drift; the other metrics assume both files are at the same BPM. If BPM differs significantly, kick phase alignment and onset cross-correlation will fail even if the cover is otherwise good.
- **Polyphonic chroma**: `chroma_cens` on a full mix captures the aggregate pitch-class distribution. Two files with identical notes but different instrumentation will score differently.

---

## 6. References

Davis, S., & Mermelstein, P. (1980). Comparison of parametric representations for monosyllabic word recognition in continuously spoken sentences. *IEEE Transactions on Acoustics, Speech, and Signal Processing*, *28*(4), 357–366. https://doi.org/10.1109/TASSP.1980.1163420

Fujishima, T. (1999). Realtime chord recognition of musical sound: A system using Common Lisp Music. In *Proceedings of the International Computer Music Conference* (pp. 464–467). International Computer Music Association.

McFee, B., Raffel, C., Liang, D., Ellis, D. P. W., McVicar, M., Battenberg, E., & Nieto, O. (2015). librosa: Audio and music signal analysis in Python. In *Proceedings of the 14th Python in Science Conference* (pp. 18–24). https://doi.org/10.25080/Majora-7b98e3ed-003

Müller, M. (2007). *Information retrieval for music and motion*. Springer. https://doi.org/10.1007/978-3-540-74048-3

Müller, M., & Ewert, S. (2011). Chroma Toolbox: MATLAB implementations of various chroma feature representations. In *Proceedings of the 12th International Society for Music Information Retrieval Conference* (pp. 215–220). ISMIR.
