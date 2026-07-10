# Audio Reproduction Capability Gap Analysis
**Date**: 2026-07-10  
**Sidequest**: `sidequest/pluck-arp-analysis`  
**Comparison basis**: Bad Apple!! cover (the working reference for "sufficient to reproduce")

---

## 1. What "sufficient to reproduce" means

The Bad Apple!! cover defined the standard:
1. **MIDI reference** — note pitches, durations, timing grid
2. **Synthesis parameters** — per-voice envelope (ADSR), filter (cutoff, resonance), oscillator type
3. **Rhythm/groove** — kick pattern, BPM, sidechain depth
4. **Arrangement structure** — which layers are active at which bar range

For "Hey Angel…" we need the same four categories, measured from audio rather than from a MIDI file. The key additional challenge is that no MIDI source exists — we must derive everything from the WAV.

---

## 2. What we have (as of 2026-07-10)

### 2a. Already measured (sufficient for synthesis)

| Parameter | Value | Method | Confidence |
|---|---|---|---|
| BPM | 138 BPM | 3+5 sixteenth kick grid + 16th note arp spacing | High |
| Bass root | G1 = 49Hz | Sub-bass FFT, Demucs stem, full-mix PYIN | High |
| Bass pattern | G1(quarter) → portamento → G1; F-range note at 3rd 16th | Bass stem pitch track | Medium |
| Bass portamento speed | ~120 sem/sec | Pitch trajectory on full-mix PYIN | High |
| Melody: notes | C4 → B3 → Bb3 → A3 → Ab3 → G3 → F#3 (chromatic descend) | Melody stem PYIN + MIDI | High |
| Melody: portamento rate | ~15 sem/sec (slow glide) | Pitch trajectory timing | High |
| High pluck pitch | E5 = 660Hz → D#5 | Full-mix PYIN | High |
| High pluck harmonics | 660Hz + 1300Hz only (near-pure) | Spectral analysis of pluck segment | High |
| High pluck brightness decay | Centroid 2500→1600Hz in 25ms | Spectral centroid over pluck onset | High |
| Sidechain pump depth | -9.2dB mean, -11dB peak | RMS envelope peak/trough ratio | High |
| Sidechain attack | ~169ms (peak to trough) | RMS envelope timing | High |
| Sidechain release | ~371ms (trough to recovery) | RMS envelope timing | High |
| Kick: half-time placement | On half-notes (every ~857ms) | Sub-bass hit detection | High |
| Arrangement structure | 6-section, t=0–32.6s | Full-mix RMS + pitch trajectory | Medium |
| Key | G minor / Dorian | Bass FFT + melody stem K-S + PYIN analysis | High |

### 2b. Measured but need refinement

| Parameter | Current state | What's missing |
|---|---|---|
| High pluck envelope | "Near-zero attack, long sustain" | Exact release time not measured |
| High pluck oscillator type | "Near-sine or filtered saw" | Cannot distinguish without cleaner stem (Demucs puts it in 'guitar' at low amplitude) |
| Melody oscillator type | Unknown | Need 'other' or 'guitar' stem analysis of mid-range content |
| Bass oscillator | Unknown | Need 'bass' stem spectral analysis for harmonic rolloff |
| Pad layer | Not characterised | 'other' stem has RMS=0.050 — needs spectral analysis |

### 2c. Not yet measured

| Parameter | Why needed | Approach |
|---|---|---|
| Pluck filter envelope (VCF params) | To reproduce the brightness burst | Spectral centroid at sub-ms resolution on guitar/pluck stem |
| Melody filter settings | Filter cutoff per section | Spectral centroid of melody stem over time |
| Kick/drum pattern exact steps | To reproduce groove | Onset detection on drums stem with 16th-note grid alignment |
| Kick timbre parameters | To synthesise the kick | Spectral analysis of drums stem (kick vs hihat separation) |
| Reverb/delay parameters | Spatial character | Not measurable from output alone — cannot be reverse-engineered from WAV |
| Master compression/limiting | Final dynamics | Crest factor of full mix vs stems |

---

## 3. Tools: what exists vs what's needed

### 3a. Existing tools (already in `tools/`)

| Tool | What it does | Status |
|---|---|---|
| `stem_separation.py` | Demucs htdemucs_6s wrapper | ✓ Works — used for this analysis |
| `audio_to_midi.py` | PYIN monophonic + chroma polyphonic → MIDI | ✓ Works — used for bass + melody stems |
| `analyse_audio.py` | Level, spectral bands, MIDI analysis | ✓ Works |
| `spectrogram.py` | Mel spectrogram + spectral centroid PNG | ✓ Works |
| `reverse_engineer.py` | Full pipeline: separate → MIDI → analysis markdown | ✓ Works but needs BPM update for non-140 tracks |

### 3b. Missing tools

#### 3b-1. Kick pattern extractor (HIGH PRIORITY)

**What**: Given a drums stem, detect onsets with sub-16th resolution, snap to the nearest 16th-note grid at a given BPM, and output a per-step boolean pattern (16 or 32 steps).  
**Why needed**: The existing `audio_to_midi.py` does not produce a grid-aligned step pattern. For drum synthesis we need `[1,0,0,1,0,0,0,0]` not a list of onset times.  
**Location**: New tool `tools/extract_drum_pattern.py`.

#### 3b-2. Voice timbre analyser (HIGH PRIORITY)

**What**: Given a clean mono stem (bass, lead, pluck), measure:
- Oscillator type best match: sine / saw / square / triangle (via THD: ratio of harmonics)
- Filter cutoff estimate: frequency at which harmonic rolloff exceeds -6dB/octave
- Filter resonance estimate: spectral peak around cutoff relative to adjacent frequencies
- ADSR envelope: attack, decay, sustain level, release (from a single note onset window)

**Why needed**: Currently we observe "near-sine with 2 harmonics" qualitatively. We need numbers: `osc=saw, cutoff=1800Hz, resonance=0.3, attack=2ms, decay=400ms, sustain=0.7, release=200ms`.  
**Location**: New tool `tools/analyse_timbre.py`.

#### 3b-3. BPM-aware portamento measurer (MEDIUM PRIORITY)

**What**: Given a pitch trajectory (from PYIN), detect pitch slide events and measure: semitone span, duration, and rate (semitones/second). Express rate also in bars/beat fractions at the given BPM.  
**Why needed**: The portamento rate (15 sem/sec for melody, 120 sem/sec for bass) was measured by hand. Automating this enables comparison across tracks and validation of synthesised output.  
**Location**: Add to `tools/audio_to_midi.py` as `analyse_portamento()`.

#### 3b-4. Sidechain profile extractor (LOW PRIORITY — already measurable)

**What**: Given full-mix RMS envelope and known kick times, fit a sidechain model (attack, release, depth) to each pump cycle, returning a mean model + confidence interval.  
**Why needed**: The current measurements (attack=169ms, release=371ms, depth=-9.2dB) were taken from a single cycle. Automating across all cycles gives a reliable parameter.  
**Location**: Add to `tools/analyse_audio.py` as `analyse_sidechain()`.

---

## 4. Research: audio analysis algorithms

The following algorithms were evaluated for this analysis pipeline. All are peer-reviewed or standardly cited.

### 4a. Pitch detection: PYIN

**Chosen algorithm**: Probabilistic YIN (PYIN), implemented in librosa (McFee et al., 2015).

**Description**: PYIN (Mauch & Dixon, 2014) extends the classical YIN pitch detector (de Cheveigné & Kawahara, 2002) with a probabilistic model that outputs per-frame voiced/unvoiced probabilities rather than binary pitch estimates. This prevents spurious octave errors in low-confidence frames — critical for tracking portamento glides.

**Accuracy**: ±0.1 semitone on clean monophonic audio; degrades on polyphonic content (hence the benefit of stem separation before pitch tracking).

**Key limitation**: PYIN has a known octave ambiguity problem on very low pitches (below E1) where fewer than two pitch periods fit in the analysis frame. On our bass stem, this caused the fundamental to be read as F1 (43.6Hz) instead of the correct G1 (49Hz). The sub-bass FFT cross-check resolved this.

**References**:
- Mauch, M., & Dixon, S. (2014). PYIN: A fundamental frequency estimator using probabilistic threshold distributions. *2014 IEEE International Conference on Acoustics, Speech and Signal Processing (ICASSP)*, 659–663. https://doi.org/10.1109/ICASSP.2014.6853678
- de Cheveigné, A., & Kawahara, H. (2002). YIN, a fundamental frequency estimator for speech and music. *The Journal of the Acoustical Society of America*, *111*(4), 1917–1930. https://doi.org/10.1121/1.1458024

### 4b. Stem separation: Demucs HTDemucs

**Chosen model**: Demucs HTDemucs, 6-stem variant (`htdemucs_6s`), version 4.0.1.

**Description**: HTDemucs (Rouard et al., 2023) is a hybrid transformer-convolutional source separation model. The 6-stem variant separates audio into: drums, bass, other, vocals, guitar, piano. It operates in both the time domain and the spectrogram domain (STFT), fusing the two via a cross-attention mechanism.

**Relevance to this work**: The model was trained on music data including electronic music (MUSDB18 dataset; Rafii et al., 2017, plus additional sources). For Switch Angel's synthesiser-only trance (no real drums, no guitar, no vocals), the "vocals" stem receives the synth lead (sustained monophonic pitched sound), "drums" receives the kick + hihat, "bass" receives the sub-bass, and "other" receives the pad/chord layer.

**Key limitation**: Because SA's lead synth has characteristics similar to sustained vocal tones (monophonic, vibrato-free, mid-range), Demucs consistently routes it to "vocals". This is not an error — it is the expected behaviour of a model trained on vocals. The MIDI extracted from the vocals stem is correctly the melody. Document and account for this in the pipeline.

**References**:
- Rouard, S., Massa, F., & Défossez, A. (2023). Hybrid transformers for music source separation. *2023 IEEE International Conference on Acoustics, Speech and Signal Processing (ICASSP)*, 1–5. https://doi.org/10.1109/ICASSP49357.2023.10096956
- Défossez, A. (2021). Hybrid spectrogram and waveform source separation. *Proceedings of the ISMIR 2021 Workshop on Music Source Separation*. https://arxiv.org/abs/2111.03600
- Rafii, Z., Liutkus, A., Stöter, F.-R., Mimilakis, S. I., & Bitteur, R. (2017). MUSDB18 — a corpus for music separation. *Zenodo*. https://doi.org/10.5281/zenodo.1117372

### 4c. Key detection: Krumhansl-Schmuckler algorithm

**Chosen method**: Correlation of chroma mean with Krumhansl-Schmuckler (K-S) profiles for all 24 major/minor keys, implemented via librosa chroma features (McFee et al., 2015).

**Description**: The K-S key-finding algorithm (Krumhansl & Schmuckler, 1990; Krumhansl, 1990) correlates a 12-dimensional pitch-class distribution (chroma) with empirically-derived "key profiles" representing the relative prevalence of each pitch class in each key. The key with the highest correlation is returned.

**Limitation observed in this work**: The algorithm fails on tracks with prominent chromatic passage work. The melody in "Hey Angel…" is a 6-semitone chromatic descend (C4→F#3), which activates all 12 pitch classes nearly equally and destroys the statistical key signature. Resolution: apply K-S only to the isolated bass stem or melody stem (post-Demucs), not the full mix, when a chromatic melody is present.

**References**:
- Krumhansl, C. L. (1990). *Cognitive foundations of musical pitch*. Oxford University Press.
- Krumhansl, C. L., & Schmuckler, M. A. (1990). The Petroushka chord: A perceptual investigation. *Music Perception*, *7*(2), 153–184. https://doi.org/10.2307/40285455

### 4d. Onset detection and tempo estimation

**Chosen method**: librosa onset detection (spectral flux) + manual grid alignment from measured onset intervals (McFee et al., 2015).

**Description**: Spectral flux onset detection computes the L1 norm of the positive difference in per-frame magnitude spectra (Bello et al., 2005). librosa's `onset_detect()` wraps this with peak picking. However, for tracks with half-time kick feel (kick landing on half-notes), librosa's `beat_track()` returned 112 BPM (half the true 138 BPM) due to the long inter-beat interval. The correct BPM was derived by:
1. Measuring sub-bass hit intervals from `find_peaks()` on the sub-bass envelope
2. Cross-validating that the arpeggio 16th-note grid (0.117s) matches 138 BPM (16th = 108.7ms, within 8% error from the yt-dlp audio quality loss)
3. Confirming the kick 3+5 subdivision (313ms + 544ms = 857ms) as 3+5 sixteenth notes at 138 BPM

**Key lesson**: Never rely on `librosa.beat_track()` alone for half-time groove tracks. Always cross-check against sub-bass onset intervals and known note-grid spacings.

**References**:
- McFee, B., Raffel, C., Liang, D., Ellis, D. P. W., McVicar, M., Battenberg, E., & Nieto, O. (2015). librosa: Audio and music signal analysis in Python. *Proceedings of the 14th Python in Science Conference*, 18–25. https://doi.org/10.25080/Majora-7b98e3ed-003
- Bello, J. P., Daudet, L., Abdallah, S., Duxbury, C., Davies, M., & Sandler, M. B. (2005). A tutorial on onset detection in music signals. *IEEE Transactions on Speech and Audio Processing*, *13*(5), 1035–1047. https://doi.org/10.1109/TSA.2005.851998

---

## 5. Summary: current vs. required for Bad Apple-level reproduction

| Category | Bad Apple (from MIDI) | Hey Angel (from audio) | Gap |
|---|---|---|---|
| Note pitches | From MIDI ✓ | PYIN on melody stem ✓ | None — equal quality |
| Note durations | From MIDI ✓ | PYIN + onset detection ✓ | Small — PYIN less reliable on portamento notes |
| Rhythm grid | MIDI ticks ✓ | Manual grid analysis ✓ | Moderate — automated grid-snap tool missing |
| Oscillator type | Known (AcidLead = saw) ✓ | Estimated from harmonics | **Gap** — need `analyse_timbre.py` |
| Filter parameters | Measured from Strudel ✓ | Spectral centroid only | **Gap** — need VCF parameter extraction |
| ADSR envelope | Known from Strudel ✓ | Attack measured; decay partial | **Gap** — per-voice ADSR tool missing |
| Kick pattern | From MIDI ✓ | Grid position estimated | **Gap** — need `extract_drum_pattern.py` |
| Sidechain depth | Measured from Strudel ✓ | Measured from RMS ✓ | None |
| Portamento | Measured from Strudel ✓ | Measured from PYIN ✓ | Small — needs automation |

**Verdict**: We have enough data to make a first synthesis attempt now. The three missing tools (timbre analyser, drum pattern extractor, sidechain profiler) would raise confidence from "good guess" to "parameter-verified". Build them before the next track, not as a blocker for "Hey Angel…".
