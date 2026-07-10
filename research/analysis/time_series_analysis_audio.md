# Time Series Analysis and Audio Signal Processing: Convergent Methodologies

**Project:** trance-stream — Procedural Trance Music Synthesis  
**Date:** 2026-07-10  
**Scope:** Connections between classical time series statistics (ARIMA, Facebook Prophet) and the signal processing methods used in `tools/compare_audio.py`

---

## Abstract

Audio synthesis and evaluation is, at its mathematical core, a problem of time series analysis. Every waveform, every RMS envelope, every chroma sequence is a discrete sequence of measurements indexed by time. This report examines the deep structural parallels between classical statistical forecasting methods — most notably ARIMA (Box & Jenkins, 1970/1994) and Facebook Prophet (Taylor & Letham, 2018) — and the audio signal processing pipeline used in the trance-stream project. Special attention is given to the role of the Discrete Fourier Transform as the shared mathematical bridge, to dynamic time warping as a temporal alignment strategy, and to the conceptual analogies between seasonal decomposition in forecasting and source separation in audio (Défossez et al., 2021). The argument is that the trance-stream evaluation pipeline is not merely analogous to time series analysis — it *is* time series analysis, applied to an exceptionally high-dimensional, multi-channel, and perceptually rich domain.

---

## 1. The Foundational Claim: Audio Is Time Series Data

A digital audio signal is, by definition, a uniformly sampled time series. A mono 44.1 kHz recording is a sequence:

$$x[n], \quad n = 0, 1, 2, \ldots, N-1$$

where each sample $x[n]$ is a scalar measurement of acoustic pressure at time $t = n / f_s$, with $f_s = 44{,}100$ Hz. This is structurally identical to a stock price sampled at 1 Hz, a temperature measured every hour, or a quarterly revenue figure — all are sequences of real-valued observations indexed by a uniform time grid (Box et al., 1994).

The difference is scale and frequency content. Where an econometric time series might contain hundreds of observations, a three-minute audio recording at 44.1 kHz contains 7.9 million samples. Where a business cycle operates over quarters or years, the relevant periodicities in trance music span from 22 ms (a single cycle at 45 Hz, the sub-bass fundamental) to 4 minutes (a full arrangement arc). The methodology, however, is the same: extract structure from sequences of numbers that change over time.

The trance-stream project computes derived time series from raw audio at a reduced sample rate. All features in `tools/compare_audio.py` use a hop length of 512 samples at 22,050 Hz, producing one feature frame every $512 / 22{,}050 \approx 23$ ms. The RMS envelope, onset strength envelope, chroma matrix, MFCC matrix, and tempogram are all derived time series of this kind (McFee et al., 2015).

---

## 2. ARIMA and the Linear Structure of Time Series

### 2.1 The ARIMA Framework

ARIMA — AutoRegressive Integrated Moving Average — is arguably the canonical model of univariate time series analysis. Box and Jenkins (1970) formalised a systematic identification-estimation-diagnostic cycle that remains influential fifty years later. The ARIMA($p$, $d$, $q$) model is written:

$$\Phi(B)(1 - B)^d x_t = \Theta(B)\varepsilon_t$$

where $B$ is the backshift operator ($B x_t = x_{t-1}$), $\Phi(B) = 1 - \phi_1 B - \cdots - \phi_p B^p$ is the autoregressive polynomial, $\Theta(B) = 1 + \theta_1 B + \cdots + \theta_q B^q$ is the moving-average polynomial, $d$ is the order of differencing applied to achieve stationarity, and $\varepsilon_t$ is white noise. The autoregressive component models the series as a linear combination of its own past values; the moving-average component models it as a linear combination of past forecast errors (Box et al., 1994).

### 2.2 Audio as an AR Process

Every digital audio filter is, in the z-domain, a rational transfer function — the same algebraic structure as ARIMA. An IIR (Infinite Impulse Response) filter applied to audio is literally an autoregressive-moving-average (ARMA) process: the output at time $n$ depends on a linear combination of past outputs (the AR part) and past inputs (the MA part):

$$y[n] = \sum_{k=1}^{p} a_k y[n-k] + \sum_{k=0}^{q} b_k x[n-k]$$

The Butterworth bandpass filter used in `_kick_phase_err` to isolate the 50–120 Hz kick fundamental is exactly this: a 4th-order IIR filter with poles and zeros placed to pass the target band. When librosa applies a resonant low-pass filter (RLPF) to model the analogue synthesiser ladder filter central to Switch Angel's sound, it is implementing a digital ARMA process. The ARIMA framework is not an analogy to audio filtering — it is the same mathematics, applied to signals rather than economic data.

The practical difference lies in what is *unknown*. In econometrics, the $\phi_k$ and $\theta_k$ coefficients are estimated from data because the generating process is unobserved. In audio synthesis, the filter coefficients are *designed* to achieve a target frequency response. The estimation direction is reversed: the statistician infers the model from observations; the synthesiser engineer designs the model and synthesises the observations.

### 2.3 Stationarity and Differencing

ARIMA requires stationarity — a time series whose statistical properties (mean, variance, autocovariance) do not change over time. The $d$ differencing term transforms a non-stationary series (e.g., one with a trend) into a stationary one. In audio, this maps to the concept of a *steady-state* versus *transient* signal. The onset detection algorithm in `_onset_xcorr` explicitly looks for the non-stationary moments — the sudden increases in energy that mark the beginning of new notes or drum hits. The onset strength envelope is, in effect, the first difference of the log-energy envelope: it is large where the signal changes rapidly and small where it is stationary (Bello et al., 2005).

---

## 3. Facebook Prophet and Seasonal Fourier Decomposition

### 3.1 The Prophet Model

Facebook Prophet, introduced by Taylor and Letham (2018), models a time series as an additive decomposition of trend, seasonality, and holiday effects:

$$y(t) = g(t) + s(t) + h(t) + \varepsilon_t$$

where $g(t)$ is the trend component (piecewise linear or logistic), $s(t)$ is the seasonality component, $h(t)$ encodes known calendar irregularities, and $\varepsilon_t$ is noise. The critical implementation detail is how Prophet represents seasonality: rather than using lagged autoregressive terms, it models periodic patterns using a **Fourier series**:

$$s(t) = \sum_{n=1}^{N} \left[ a_n \cos\left(\frac{2\pi n t}{P}\right) + b_n \sin\left(\frac{2\pi n t}{P}\right) \right]$$

where $P$ is the period (e.g., 365.25 days for annual seasonality) and the $a_n$, $b_n$ coefficients are fit via regularised regression. Prophet is, therefore, a curve-fitting procedure whose seasonal component is a truncated Fourier series (Taylor & Letham, 2018).

### 3.2 The Fourier Transform as the Shared Bridge

The fact that Prophet uses Fourier series to represent seasonality is not coincidental — it is the mathematical reason why time series analysis and audio signal processing share so much vocabulary. The Discrete Fourier Transform (DFT) of a sequence $x[n]$ of length $N$ is:

$$X[k] = \sum_{n=0}^{N-1} x[n] \cdot e^{-j 2\pi k n / N}, \quad k = 0, 1, \ldots, N-1$$

This transforms a time-domain sequence into a frequency-domain representation. The inverse DFT reconstructs the original sequence as exactly the kind of Fourier sum Prophet uses for seasonality: a sum of sinusoids at harmonically related frequencies. Every periodic pattern in a time series — weekly seasonality in sales data, or the 138 BPM pulse in a trance track — corresponds to a peak in the DFT spectrum.

In audio, the Fast Fourier Transform (FFT) — an algorithm computing the DFT in $O(N \log N)$ instead of $O(N^2)$ (Cooley & Tukey, 1965) — is the central computational tool. The Short-Time Fourier Transform (STFT) applies the FFT to overlapping windowed frames of a signal, producing a time-frequency representation (the spectrogram):

$$\text{STFT}[m, k] = \sum_{n=0}^{N-1} x[n + mH] \cdot w[n] \cdot e^{-j 2\pi k n / N}$$

where $m$ is the frame index, $H$ is the hop length (512 samples in our pipeline), and $w[n]$ is a window function (typically Hann). Every librosa feature used in `compare_audio.py` is computed from the STFT or a transformation of it: chroma uses it to bin energy by pitch class, MFCCs use the mel-filterbank applied to the magnitude spectrum, spectral contrast computes peak-to-valley differences per sub-band. The STFT is the same analytical decomposition as Prophet's Fourier seasonality — it resolves a complex signal into a sum of sinusoidal components — but applied frame-by-frame to capture how the spectral content evolves over time.

### 3.3 Additive Decomposition in Audio: Source Separation

Prophet's additive decomposition $y(t) = g(t) + s(t) + h(t)$ has a direct counterpart in audio source separation. Défossez, Chanussot, Bach, and Usunier (2021) introduced Demucs, a deep learning model that decomposes a mixed audio signal into its constituent source signals — drums, bass, vocals, other — each of which is a time-domain waveform summing back to the mix:

$$x(t) = \text{drums}(t) + \text{bass}(t) + \text{vocals}(t) + \text{other}(t)$$

The hybrid version HTDemucs (Défossez et al., 2022) operates simultaneously in the time domain and the frequency (STFT) domain, combining both representations to improve separation quality. This is structurally identical to Prophet decomposing a time series into additive components that each capture a different type of temporal structure. The goal in both cases is the same: understand a complex signal by decomposing it into interpretable, additive parts.

For the trance-stream project, source separation maps directly to the synthesis architecture. The project generates separate tracks — kick, bass, lead, pad, arp, sidechain — and sums them. The evaluation in `compare_audio.py` compares the resulting mix against a reference mix. Source separation methods like Demucs could, in principle, be applied in reverse to isolate individual components of the reference recording and compare them against their synthesised counterparts individually, which would yield more targeted diagnostics.

---

## 4. Mapping the Seven Metrics to Time Series Concepts

### 4.1 RMS Envelope Pearson r — Trend Correlation

The RMS envelope:

$$\text{RMS}[m] = \sqrt{\frac{1}{N} \sum_{n=0}^{N-1} x[n + mH]^2}$$

is a time series of energy measurements, one per 23 ms frame. The Pearson correlation coefficient between reference and generated RMS envelopes measures whether energy rises and falls at the same moments:

$$r = \frac{\sum_m (\text{RMS}_\text{ref}[m] - \bar{r})(\text{RMS}_\text{gen}[m] - \bar{g})}{\sqrt{\sum_m (\text{RMS}_\text{ref}[m] - \bar{r})^2 \sum_m (\text{RMS}_\text{gen}[m] - \bar{g})^2}}$$

In classical time series analysis, this is the cross-correlation at lag zero between two processes. A sidechain compressor pumping in synchrony with the kick drum creates a periodic dip in the RMS envelope once every half-note (at 138 BPM, every $2 \times 60/138 \approx 0.87$ s). If the generated track pumps at the wrong phase or at the wrong rate, $r$ drops sharply toward zero. The Pearson $r$ target of $\geq 0.70$ requires that the two envelopes share 49% of their variance — they must follow essentially the same temporal energy trajectory (Cohen, 1988).

### 4.2 Onset Cross-Correlation — Temporal Event Alignment

The onset strength envelope $o[m] = \max(0, \Delta E[m])$, where $\Delta E[m]$ is the spectral flux between frames $m-1$ and $m$ (Bello et al., 2005), is a sparse time series marking the moments when new acoustic events begin. The cross-correlation of two onset envelopes:

$$R_{xy}[\tau] = \sum_m o_\text{ref}[m] \cdot o_\text{gen}[m - \tau]$$

is the standard cross-correlation function familiar from ARIMA residual diagnostics and from signal processing alike. The peak location $\tau^*$ gives the timing offset between the two tracks; the peak value $R_{xy}[\tau^*]$ measures how well the rhythmic event times align. This is exactly the statistic used to diagnose phase offset between two time series before applying a lag correction.

### 4.3 Chroma as a Harmonic Time Series

Chroma-CENS (Chroma Energy Normalised Statistics) projects the short-time spectrum onto 12 pitch classes (C, C#, D, ..., B), normalises, and smooths, yielding a $12 \times M$ matrix — twelve simultaneous time series, one per pitch class (Müller & Ewert, 2011; McFee et al., 2015). The cosine similarity of the *mean* chroma vectors collapses this to a single 12-dimensional profile comparison, testing whether the generated track occupies the same tonal space as the reference. In time series terms, this is a spectral-domain comparison: do the two signals have the same harmonic content, averaged over time? The target of $\geq 0.80$ means the synthesised trance track must be in the same key and use the same general harmonic vocabulary as the reference.

### 4.4 MFCC DTW Distance — Time-Warped Spectral Trajectory

Mel-Frequency Cepstral Coefficients (MFCCs) are derived from the log mel-filterbank spectrum via the Discrete Cosine Transform, yielding 13 coefficients per frame that encode the spectral envelope in a perceptually weighted, decorrelated basis (Davis & Mermelstein, 1980). The sequence of MFCC vectors over time is a multivariate time series representing the timbral trajectory of the audio.

Dynamic Time Warping (DTW) aligns two time series of potentially different lengths by finding the minimum-cost monotonic warping path through the cost matrix $C[i,j] = \|m_\text{ref}[i] - m_\text{gen}[j]\|_2$. The DTW distance is:

$$\text{DTW}(A, B) = \min_{\mathcal{W}} \sum_{(i,j) \in \mathcal{W}} C[i,j]$$

subject to boundary, monotonicity, and continuity constraints (Müller, 2007; Sakoe & Chiba, 1978). DTW is the classical solution to tempo-flexible comparison in music information retrieval. It generalises Euclidean distance to allow for local time stretching — if the generated track plays a particular timbral section 50 ms later than the reference, DTW can absorb that offset without penalising it as a mismatch. This makes it strictly more powerful than a frame-aligned Euclidean or Pearson comparison for timbral trajectory matching.

In `_mfcc_dtw`, the accumulated cost is normalised by path length to give a per-frame average distance, ensuring that longer comparisons are not penalised purely by duration.

### 4.5 Tempogram Cosine — Rhythmic Hierarchy

The tempogram is the Fourier transform of the onset strength envelope, computed frame by frame (Grosche & Müller, 2011):

$$\mathcal{T}[m, \omega] = \left| \sum_{n=m-W/2}^{m+W/2} o[n] \cdot w[n-m] \cdot e^{-j 2\pi \omega n / f_s} \right|^2$$

Each column is effectively a local periodicity analysis — at which tempos (measured in BPM) is the rhythm locally periodic? The mean tempogram is a fingerprint of the full rhythmic hierarchy: the 138 BPM pulse, the 69 BPM half-time feel, the 276 BPM double-time hi-hat layer all appear as peaks at their respective frequencies. Cosine similarity between mean tempograms compares these full hierarchies. This is precisely analogous to comparing the power spectra of two time series in econometrics — the spectral density function is the Fourier transform of the autocovariance function, and comparing spectral densities is standard practice in time series analysis (Priestley, 1981).

### 4.6 Kick Phase Error — Phase-Aware Temporal Alignment

The kick phase error bandpass-filters to 50–120 Hz, detects onsets, and computes each onset time modulo the half-note period. This is a phase estimation problem: given a periodic signal at a known frequency (the kick drum at BPM/2 Hz), what is its phase offset relative to time zero? This is directly analogous to computing the phase of the dominant Fourier component of a seasonal time series. A weather forecasting model that predicts winter correctly but six weeks early has zero amplitude error and 90-degree phase error — which is what `kick_phase_err_ms` detects in the drum machine.

---

## 5. Where the Approaches Diverge

Despite their shared mathematical substrate, statistical time series analysis and audio signal processing differ in important ways:

**Dimensionality and sampling rate.** ARIMA models are typically applied to univariate series with tens to thousands of observations. An audio signal at 22,050 Hz generates millions of samples per track, and the feature matrices (MFCC: $13 \times M$, chroma: $12 \times M$, STFT: $1025 \times M$ for a 2048-point window) are high-dimensional multivariate time series. DTW and cosine similarity scale to this dimensionality; standard ARIMA identification does not.

**Stochastic versus deterministic.** ARIMA assumes the series is generated by a stochastic process with unknown parameters to be estimated. Audio synthesis is, in the trance-stream project, *designed* — the parameters of every oscillator, filter, and envelope are known and controlled. The comparison problem is not parameter estimation but parameter optimisation: adjust synthesis parameters until the 7 metrics exceed their targets.

**Forecasting versus evaluation.** ARIMA and Prophet are forecasting frameworks: given past values, predict future values. The trance-stream metrics are *evaluation* metrics: given two complete time series (reference and generated), measure their similarity. ARIMA's autocorrelation function and partial autocorrelation function are used to diagnose temporal structure; the trance-stream metrics use the same mathematical tools (correlation, Fourier analysis, DTW) in a comparative rather than predictive mode.

**Non-stationarity is signal, not noise.** In econometric time series, trends and structural breaks are often removed (differenced away) before modelling. In audio, the non-stationary parts — transients, onset bursts, the attack phase of a synth note — are often the most perceptually significant events. The onset detector specifically targets these non-stationary moments.

---

## 6. Implications for the trance-stream Optimisation Loop

The synthesis-compare-iterate loop in trance-stream is a form of **system identification**: find synthesis parameters such that the output time series matches a target time series across multiple feature dimensions simultaneously. This is conceptually related to ARIMA model identification (finding the model whose residuals are white noise) and to spectral matching (finding a filter whose output power spectrum matches a target).

The seven metrics form a multi-objective loss function over different temporal representations of the same audio:

| Metric | Time Series Being Compared | Comparison Method |
|---|---|---|
| RMS envelope Pearson r | Energy trajectory | Correlation |
| Onset cross-correlation | Rhythmic event times | Cross-correlation |
| Kick phase error | Kick onset phase | Phase estimation |
| Chroma cosine | Harmonic content profile | Spectral similarity |
| MFCC DTW distance | Timbral trajectory | Warped distance |
| Tempogram cosine | Rhythmic hierarchy | Spectral similarity |
| Spectral contrast cosine | Band presence/punch | Spectral similarity |

Future work could apply ARIMA-style spectral diagnostics to the *residuals* of each metric — if the RMS correlation is 0.70 but there is still a systematic phase offset in the sidechain pump, the partial autocorrelation of the RMS error time series would reveal this structure. Similarly, Prophet's Fourier seasonality fitting could be applied directly to the onset strength envelope to estimate the dominant beat period and its harmonics, providing an explicit BPM estimate that could seed the kick phase alignment metric.

---

## 7. Conclusion

Time series analysis and audio signal processing are not merely analogous — they share a common mathematical foundation in the Fourier transform and its ability to decompose structured temporal variation into interpretable components. ARIMA formalises the linear dependence structure of a time series through autoregressive and moving-average polynomials; audio filters implement the same mathematics to shape spectral content. Prophet decomposes business metrics into additive trend and Fourier-seasonal components; source separation models like HTDemucs decompose audio mixtures into additive instrumental stems. Dynamic time warping, cross-correlation, and cosine spectral similarity are tools shared freely between the two domains.

The trance-stream evaluation pipeline in `tools/compare_audio.py` is, in rigorous terms, a multi-scale time series comparison system. Its seven metrics span from the fastest temporal scales (kick phase alignment at millisecond precision) to the slowest (RMS envelope tracking over the full arrangement arc), and from the time domain (onset cross-correlation) to the frequency domain (chroma, tempogram) to the cepstral domain (MFCC DTW). The goal — that generated audio should be indistinguishable from a reference at all temporal and spectral scales simultaneously — is the goal of any good time series model: residuals that contain no structure, only noise.

---

## References

Bello, J. P., Daudet, L., Abdallah, S., Duxbury, C., Davies, M., & Sandler, M. B. (2005). A tutorial on onset detection in music signals. *IEEE Transactions on Speech and Audio Processing*, *13*(5), 1035–1047. https://doi.org/10.1109/TSA.2005.851998

Box, G. E. P., Jenkins, G. M., & Reinsel, G. C. (1994). *Time series analysis: Forecasting and control* (3rd ed.). Prentice Hall. (Original work published 1970)

Cohen, J. (1988). *Statistical power analysis for the behavioral sciences* (2nd ed.). Lawrence Erlbaum Associates.

Cooley, J. W., & Tukey, J. W. (1965). An algorithm for the machine calculation of complex Fourier series. *Mathematics of Computation*, *19*(90), 297–301. https://doi.org/10.1090/S0025-5718-1965-0178586-1

Davis, S. B., & Mermelstein, P. (1980). Comparison of parametric representations for monosyllabic word recognition in continuously spoken sentences. *IEEE Transactions on Acoustics, Speech, and Signal Processing*, *28*(4), 357–366. https://doi.org/10.1109/TASSP.1980.1163420

Défossez, A., Usunier, N., Bottou, L., & Bach, F. (2021). Music source separation in the waveform domain. *arXiv preprint arXiv:1911.13254v2*. https://arxiv.org/abs/1911.13254

Défossez, A., Chanussot, C., & Bach, F. (2022). *Hybrid transformers for music source separation*. arXiv preprint arXiv:2211.00230. https://arxiv.org/abs/2211.00230

Grosche, P., & Müller, M. (2011). Toward characteristic audio shingles for efficient audio identification. In *Proceedings of the IEEE International Conference on Acoustics, Speech and Signal Processing (ICASSP)* (pp. 493–496). IEEE. https://doi.org/10.1109/ICASSP.2011.5946451

McFee, B., Raffel, C., Liang, D., Ellis, D. P. W., McVicar, M., Battenberg, E., & Nieto, O. (2015). librosa: Audio and music signal analysis in Python. In *Proceedings of the 14th Python in Science Conference* (pp. 18–25). https://doi.org/10.25080/Majora-7b98e3ed-003

Müller, M. (2007). *Information retrieval for music and motion*. Springer. https://doi.org/10.1007/978-3-540-74048-3

Müller, M., & Ewert, S. (2011). Chroma Toolbox: MATLAB implementations of chromagram representations. In *Proceedings of the 12th International Society for Music Information Retrieval Conference (ISMIR)* (pp. 215–220).

Priestley, M. B. (1981). *Spectral analysis and time series* (Vol. 1). Academic Press.

Sakoe, H., & Chiba, S. (1978). Dynamic programming algorithm optimization for spoken word recognition. *IEEE Transactions on Acoustics, Speech, and Signal Processing*, *26*(1), 43–49. https://doi.org/10.1109/TASSP.1978.1163055

Taylor, S. J., & Letham, B. (2018). Forecasting at scale. *The American Statistician*, *72*(1), 37–45. https://doi.org/10.1080/00031305.2017.1380080
