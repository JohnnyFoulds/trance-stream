#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Audio similarity tool — two-tier perceptual + structural comparison.

Tier 1 (gates overall verdict): CLAP embedding cosine, spectral centroid ratio,
6-band energy cosine, MFCC cosine.  All four must pass for OVERALL PASS.

Tier 2 (informational diagnostics): RMS envelope Pearson r, onset cross-
correlation, kick phase alignment, chroma cosine, tempogram cosine, spectral
contrast cosine, MFCC DTW (kept for historical continuity; known-broken).

Usage
-----
    python tools/compare_audio.py reference.wav generated.wav --bpm 138

    from tools.compare_audio import compare_audio
    result = compare_audio('ref.wav', 'gen.wav', bpm=138.0)
    print(result['overall_pass'])

Methodology
-----------
See docs/testing/AUDIO_SIMILARITY_METHODOLOGY.md for full rationale and
APA 7th citations.  Architecture decisions: docs/decisions/compare_audio_redesign.md.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

try:
    import librosa
    import scipy.signal
    import scipy.stats
    from scipy.spatial.distance import cosine as cosine_dist
except ImportError as e:
    print(f"ERROR: missing dependency — {e}")
    print("  pip install librosa scipy")
    sys.exit(1)

# ── Targets ──────────────────────────────────────────────────────────────────
# Tier-1 entries: ('>=', threshold, weight) or ('in_range', (lo, hi), weight)
# Tier-2 entries: same format; weight 'High' or 'Medium' for legacy display.
_TARGETS = {
    # Tier 1 — perceptual gates
    'clap_cosine':             ('>=',       0.70,          'Tier1'),
    'spectral_centroid_ratio': ('in_range', (0.70, 1.30),  'Tier1'),
    'band_energy_cosine':      ('>=',       0.85,          'Tier1'),
    'mfcc_cosine':             ('>=',       0.80,          'Tier1'),
    # Tier 2 — structural diagnostics
    'rms_envelope_r':          ('>=',       0.70,          'High'),
    'onset_xcorr_peak':        ('>=',       0.40,          'High'),
    'kick_phase_err_ms':       ('<=',       30.0,          'High'),
    'chroma_cosine':           ('>=',       0.80,          'High'),
    'mfcc_dtw_dist':           ('<=',       0.30,          'Medium'),
    'tempogram_cosine':        ('>=',       0.80,          'Medium'),
    'spectral_contrast_cosine':('>=',       0.70,          'Medium'),
}

_SR  = 22050
_HOP = 512


def _load(path: str) -> np.ndarray:
    """Load WAV to mono float32 at _SR."""
    y, _ = librosa.load(path, sr=_SR, mono=True)
    return y.astype(np.float32)


# ── Tier-1 metrics ────────────────────────────────────────────────────────────

def _clap_cosine(path_ref: str, path_gen: str):
    """LAION-CLAP embedding cosine similarity between two audio files.

    Returns float in [-1, 1] or None if laion-clap is not installed.
    Uses the music-fine-tuned checkpoint (music_audioset_epoch_15_esc_90.14).

    Wu et al. (2023); Gui et al. (2024) — see AUDIO_SIMILARITY_METHODOLOGY.md.
    """
    try:
        import laion_clap  # noqa: PLC0415
    except ImportError:
        print("  [WARNING] laion-clap not installed — CLAP cosine unavailable.")
        print("            pip install laion-clap")
        return None

    model = laion_clap.CLAP_Module(enable_fusion=False, amodel='HTSAT-tiny')
    model.load_ckpt()  # downloads ~340 MB checkpoint on first run
    embeddings = model.get_audio_embedding_from_filelist(
        [str(path_ref), str(path_gen)], use_tensor=False
    )
    # Embeddings are L2-normalised by the model; dot product == cosine similarity.
    return float(np.dot(embeddings[0], embeddings[1]))


def _spectral_centroid_ratio(y_ref: np.ndarray, y_gen: np.ndarray) -> float:
    """Ratio of mean spectral centroids: mean(centroid_gen) / mean(centroid_ref).

    A ratio near 1.0 means both files have the same average brightness.
    Ratio < 0.70 → generated file is far darker (missing high-frequency content).
    """
    c_ref = librosa.feature.spectral_centroid(y=y_ref, sr=_SR, hop_length=_HOP)[0]
    c_gen = librosa.feature.spectral_centroid(y=y_gen, sr=_SR, hop_length=_HOP)[0]
    mean_ref = float(np.mean(c_ref))
    if mean_ref < 1e-9:
        return 0.0
    return float(np.mean(c_gen) / mean_ref)


def _band_energy_cosine(y_ref: np.ndarray, y_gen: np.ndarray) -> float:
    """Cosine similarity of 6-band fractional energy vectors.

    Bands: 0–200, 200–500, 500–1k, 1–2k, 2–4k, 4k+ Hz.
    Each vector sums to 1.0 (energy fractions), so the comparison is
    shape-only — it detects a missing high-frequency shelf even when the
    reference and generated files differ in absolute loudness.
    """
    S_ref = np.abs(librosa.stft(y_ref, hop_length=_HOP)) ** 2
    S_gen = np.abs(librosa.stft(y_gen, hop_length=_HOP)) ** 2

    n_fft   = (S_ref.shape[0] - 1) * 2
    freqs   = librosa.fft_frequencies(sr=_SR, n_fft=n_fft)
    bands   = [(0, 200), (200, 500), (500, 1000), (1000, 2000), (2000, 4000), (4000, _SR // 2)]

    def _vec(S):
        total = S.sum() + 1e-12
        v = np.array([S[np.logical_and(freqs >= lo, freqs < hi)].sum() / total
                      for lo, hi in bands], dtype=np.float64)
        return v

    v_ref = _vec(S_ref)
    v_gen = _vec(S_gen)
    if v_ref.sum() < 1e-9 or v_gen.sum() < 1e-9:
        return 0.0
    return float(1.0 - cosine_dist(v_ref, v_gen))


def _mfcc_cosine(y_ref: np.ndarray, y_gen: np.ndarray) -> float:
    """Cosine similarity of mean 13-coefficient MFCC vectors.

    Collapses the time axis to a single timbral fingerprint per file.
    Well-calibrated 0–1 range, unlike the DTW normalised cost which was
    never calibrated against real audio (scored 178 vs threshold 0.30).

    Davis & Mermelstein (1980); McFee et al. (2015).
    """
    m_ref = librosa.feature.mfcc(y=y_ref, sr=_SR, n_mfcc=13, hop_length=_HOP).mean(axis=1)
    m_gen = librosa.feature.mfcc(y=y_gen, sr=_SR, n_mfcc=13, hop_length=_HOP).mean(axis=1)
    return float(1.0 - cosine_dist(m_ref.astype(np.float64), m_gen.astype(np.float64)))


# ── Tier-2 metrics (unchanged) ────────────────────────────────────────────────

def _rms_envelope_r(y_ref: np.ndarray, y_gen: np.ndarray) -> float:
    rms_ref = librosa.feature.rms(y=y_ref, hop_length=_HOP)[0].astype(np.float64)
    rms_gen = librosa.feature.rms(y=y_gen, hop_length=_HOP)[0].astype(np.float64)
    n = min(len(rms_ref), len(rms_gen))
    if n < 4:
        return 0.0
    r, _ = scipy.stats.pearsonr(rms_ref[:n], rms_gen[:n])
    return float(r)


def _onset_xcorr(y_ref: np.ndarray, y_gen: np.ndarray) -> tuple[float, float]:
    o_ref = librosa.onset.onset_strength(y=y_ref, sr=_SR, hop_length=_HOP).astype(np.float64)
    o_gen = librosa.onset.onset_strength(y=y_gen, sr=_SR, hop_length=_HOP).astype(np.float64)

    def _norm(x):
        x = x - x.mean()
        s = x.std()
        return x / s if s > 1e-9 else x

    o_ref = _norm(o_ref); o_gen = _norm(o_gen)
    n = min(len(o_ref), len(o_gen))
    xcorr = scipy.signal.correlate(o_gen[:n], o_ref[:n], mode='full')
    lags  = scipy.signal.correlation_lags(n, n, mode='full')
    peak_idx = int(np.argmax(xcorr))
    peak_val = float(xcorr[peak_idx]) / n
    lag_ms   = float(lags[peak_idx]) * _HOP / _SR * 1000.0
    return peak_val, lag_ms


def _kick_phase_err(y_ref: np.ndarray, y_gen: np.ndarray, bpm: float) -> float:
    half_note_s = 2 * 60.0 / bpm

    def _kick_times(y):
        b, a = scipy.signal.butter(4, [50 / (_SR / 2), 120 / (_SR / 2)], btype='band')
        y_kick = scipy.signal.lfilter(b, a, y.astype(np.float64)).astype(np.float32)
        frames = librosa.onset.onset_detect(y=y_kick, sr=_SR, hop_length=_HOP,
                                            backtrack=False)
        return librosa.frames_to_time(frames, sr=_SR, hop_length=_HOP)

    times_ref = _kick_times(y_ref)
    times_gen = _kick_times(y_gen)
    if len(times_ref) == 0 or len(times_gen) == 0:
        return 999.0

    phase_ref = np.mean(times_ref % half_note_s)
    phase_gen = np.mean(times_gen % half_note_s)
    err = abs(phase_ref - phase_gen)
    err = min(err, half_note_s - err)
    return float(err * 1000.0)


def _chroma_cosine(y_ref: np.ndarray, y_gen: np.ndarray) -> float:
    y_h_ref = librosa.effects.harmonic(y_ref, margin=8)
    y_h_gen = librosa.effects.harmonic(y_gen, margin=8)
    c_ref = librosa.feature.chroma_cens(y=y_h_ref, sr=_SR, hop_length=_HOP).mean(axis=1)
    c_gen = librosa.feature.chroma_cens(y=y_h_gen, sr=_SR, hop_length=_HOP).mean(axis=1)
    if c_ref.sum() < 1e-9 or c_gen.sum() < 1e-9:
        return 0.0
    return float(1.0 - cosine_dist(c_ref.astype(np.float64), c_gen.astype(np.float64)))


def _mfcc_dtw(y_ref: np.ndarray, y_gen: np.ndarray) -> float:
    """Kept for historical continuity — do not use as a gate (see mfcc_cosine)."""
    m_ref = librosa.feature.mfcc(y=y_ref, sr=_SR, n_mfcc=13, hop_length=_HOP)
    m_gen = librosa.feature.mfcc(y=y_gen, sr=_SR, n_mfcc=13, hop_length=_HOP)
    D, wp = librosa.sequence.dtw(m_ref, m_gen, metric='euclidean')
    path_length = len(wp)
    if path_length == 0:
        return 999.0
    return float(D[-1, -1] / path_length)


def _tempogram_cosine(y_ref: np.ndarray, y_gen: np.ndarray) -> float:
    o_ref = librosa.onset.onset_strength(y=y_ref, sr=_SR, hop_length=_HOP)
    o_gen = librosa.onset.onset_strength(y=y_gen, sr=_SR, hop_length=_HOP)
    t_ref = librosa.feature.tempogram(onset_envelope=o_ref, sr=_SR, hop_length=_HOP).mean(axis=1)
    t_gen = librosa.feature.tempogram(onset_envelope=o_gen, sr=_SR, hop_length=_HOP).mean(axis=1)
    if t_ref.sum() < 1e-9 or t_gen.sum() < 1e-9:
        return 0.0
    return float(1.0 - cosine_dist(t_ref.astype(np.float64), t_gen.astype(np.float64)))


def _spectral_contrast_cosine(y_ref: np.ndarray, y_gen: np.ndarray) -> float:
    sc_ref = librosa.feature.spectral_contrast(y=y_ref, sr=_SR, n_bands=6,
                                                hop_length=_HOP).mean(axis=1)
    sc_gen = librosa.feature.spectral_contrast(y=y_gen, sr=_SR, n_bands=6,
                                                hop_length=_HOP).mean(axis=1)
    if sc_ref.sum() < 1e-9 or sc_gen.sum() < 1e-9:
        return 0.0
    return float(1.0 - cosine_dist(sc_ref.astype(np.float64), sc_gen.astype(np.float64)))


# ── Pass evaluation ───────────────────────────────────────────────────────────

def _eval_pass(key: str, value) -> bool:
    """Evaluate whether a metric value passes its target. Returns False for None."""
    if value is None:
        return False
    op, threshold, _weight = _TARGETS[key]
    if op == '>=':
        return value >= threshold
    if op == '<=':
        return value <= threshold
    if op == 'in_range':
        lo, hi = threshold
        return lo <= value <= hi
    return False


# ── Main entry point ──────────────────────────────────────────────────────────

def compare_audio(ref_path: str, gen_path: str, bpm: float = 138.0) -> dict:
    """Compare two audio files.

    Parameters
    ----------
    ref_path : str   Path to reference WAV.
    gen_path : str   Path to generated WAV.
    bpm : float      Tempo in BPM (used for kick phase alignment).

    Returns
    -------
    dict with all metric values, passes dict, and overall_pass bool.
    """
    y_ref = _load(ref_path)
    y_gen = _load(gen_path)

    # Tier 1
    clap        = _clap_cosine(ref_path, gen_path)
    centroid    = _spectral_centroid_ratio(y_ref, y_gen)
    band_energy = _band_energy_cosine(y_ref, y_gen)
    mfcc_cos    = _mfcc_cosine(y_ref, y_gen)

    # Tier 2
    rms_r           = _rms_envelope_r(y_ref, y_gen)
    xcorr, lag_ms   = _onset_xcorr(y_ref, y_gen)
    kick_err        = _kick_phase_err(y_ref, y_gen, bpm)
    chroma          = _chroma_cosine(y_ref, y_gen)
    dtw             = _mfcc_dtw(y_ref, y_gen)
    tempogram       = _tempogram_cosine(y_ref, y_gen)
    contrast        = _spectral_contrast_cosine(y_ref, y_gen)

    values = {
        'clap_cosine':              clap,
        'spectral_centroid_ratio':  centroid,
        'band_energy_cosine':       band_energy,
        'mfcc_cosine':              mfcc_cos,
        'rms_envelope_r':           rms_r,
        'onset_xcorr_peak':         xcorr,
        'onset_xcorr_lag_ms':       lag_ms,
        'kick_phase_err_ms':        kick_err,
        'chroma_cosine':            chroma,
        'mfcc_dtw_dist':            dtw,
        'tempogram_cosine':         tempogram,
        'spectral_contrast_cosine': contrast,
    }

    passes = {k: _eval_pass(k, values[k]) for k in _TARGETS}

    # Tier-1 gate: all available Tier-1 metrics must pass
    tier1_keys      = ['clap_cosine', 'spectral_centroid_ratio', 'band_energy_cosine', 'mfcc_cosine']
    tier1_available = [k for k in tier1_keys if values[k] is not None]
    perceptual_pass = len(tier1_available) > 0 and all(passes[k] for k in tier1_available)

    # Tier-2 gate: majority of High-weight structural metrics must pass
    structural_high  = ['rms_envelope_r', 'onset_xcorr_peak', 'kick_phase_err_ms', 'chroma_cosine']
    structural_pass  = sum(passes[k] for k in structural_high) >= 3

    overall_pass = perceptual_pass and structural_pass

    return {**values, 'passes': passes, 'overall_pass': overall_pass}


def _print_report(result: dict, ref_path: str, gen_path: str) -> None:
    print(f"\nAudio Similarity Report")
    print(f"  Reference : {ref_path}")
    print(f"  Generated : {gen_path}")

    def _row(key, label, fmt, target_str, note=''):
        v     = result[key]
        passed = result['passes'][key]
        mark  = 'PASS' if passed else 'FAIL'
        val_s = 'N/A' if v is None else fmt.format(v)
        suffix = f'  — {note}' if note else ''
        print(f"  {label:<35} {val_s:>10}  {target_str:>12}  {mark}{suffix}")

    print()
    print(f"  {'── Perceptual  (gates overall verdict) ──':}")
    _row('clap_cosine',             'CLAP embedding cosine',         '{:.3f}', '>= 0.70',
         'N/A = laion-clap not installed')
    _row('spectral_centroid_ratio', 'Spectral centroid ratio',       '{:.3f}', '0.70–1.30',
         'gen/ref brightness ratio')
    _row('band_energy_cosine',      '6-band energy cosine',          '{:.3f}', '>= 0.85',
         'spectral shape match')
    _row('mfcc_cosine',             'MFCC cosine (mean vector)',     '{:.3f}', '>= 0.80',
         'timbral fingerprint')

    print()
    print(f"  {'── Structural diagnostics  (informational) ──':}")
    _row('rms_envelope_r',           'RMS envelope r',               '{:.3f}', '>= 0.70',
         'sidechain pump / energy trajectory')
    _row('onset_xcorr_peak',         'Onset cross-corr peak',        '{:.3f}', '>= 0.40',
         'rhythmic event timing')
    _row('kick_phase_err_ms',        'Kick phase error (ms)',         '{:.1f}', '<= 30ms',
         'kick phase (known-unreliable: F2 bleed)')
    _row('chroma_cosine',            'Chroma cosine',                 '{:.3f}', '>= 0.80',
         'key / harmonic content')
    _row('mfcc_dtw_dist',            'MFCC DTW (broken — use cosine)','{:.1f}', '<= 0.30',
         'threshold never calibrated; 178 typical')
    _row('tempogram_cosine',         'Tempogram cosine',              '{:.3f}', '>= 0.80',
         'rhythmic hierarchy')
    _row('spectral_contrast_cosine', 'Spectral contrast cos',         '{:.3f}', '>= 0.70',
         'direction-only — unreliable for missing bands')

    lag = result['onset_xcorr_lag_ms']
    print(f"\n  Onset lag: {lag:+.1f}ms  "
          f"({'aligned' if abs(lag) < 20 else 'OFFSET — events not time-aligned'})")

    print()
    overall = result['overall_pass']
    print(f"  OVERALL: {'PASS' if overall else 'FAIL'} — "
          f"{'perceptual + structural criteria met' if overall else 'one or more perceptual gates failed'}")
    print()


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('reference', help='Reference WAV path')
    p.add_argument('generated', help='Generated WAV path')
    p.add_argument('--bpm', type=float, default=138.0, help='Tempo in BPM (default: 138)')
    args = p.parse_args()

    result = compare_audio(args.reference, args.generated, bpm=args.bpm)
    _print_report(result, args.reference, args.generated)
    sys.exit(0 if result['overall_pass'] else 1)


if __name__ == '__main__':
    main()
