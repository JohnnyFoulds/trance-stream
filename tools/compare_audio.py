#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Audio similarity tool — time-aware cross-file comparison.

Measures whether a generated WAV sounds like a reference WAV using 7 metrics
that all preserve temporal structure.  Every metric is cross-file; none collapse
the time axis before comparing.

Usage
-----
    python tools/compare_audio.py reference.wav generated.wav --bpm 138

    from tools.compare_audio import compare_audio
    result = compare_audio('ref.wav', 'gen.wav', bpm=138.0)
    print(result['rms_envelope_r'])   # e.g. 0.03 — immediately shows the problem
    print(result['overall_pass'])     # False

Methodology
-----------
See docs/testing/AUDIO_SIMILARITY_METHODOLOGY.md for full rationale and citations.
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

# ── Targets (minimum for a passing cover) ────────────────────────────────────
_TARGETS = {
    'rms_envelope_r':      ('>=', 0.70, 'High'),
    'onset_xcorr_peak':    ('>=', 0.40, 'High'),
    'kick_phase_err_ms':   ('<=', 30.0, 'High'),
    'chroma_cosine':       ('>=', 0.80, 'High'),
    'mfcc_dtw_dist':       ('<=', 0.30, 'Medium'),
    'tempogram_cosine':    ('>=', 0.80, 'Medium'),
    'spectral_contrast_cosine': ('>=', 0.70, 'Medium'),
}

_SR = 22050   # common sample rate for all comparisons
_HOP = 512


def _load(path: str) -> np.ndarray:
    """Load WAV to mono float32 at _SR."""
    y, _ = librosa.load(path, sr=_SR, mono=True)
    return y.astype(np.float32)


def _rms_envelope_r(y_ref: np.ndarray, y_gen: np.ndarray) -> float:
    """Pearson r of per-frame RMS envelopes (hop=512 samples ≈ 23ms).

    Captures whether energy rises, falls, and pumps at the same moments.
    A sidechain pump at different times → near-zero r.
    """
    rms_ref = librosa.feature.rms(y=y_ref, hop_length=_HOP)[0].astype(np.float64)
    rms_gen = librosa.feature.rms(y=y_gen, hop_length=_HOP)[0].astype(np.float64)
    n = min(len(rms_ref), len(rms_gen))
    if n < 4:
        return 0.0
    r, _ = scipy.stats.pearsonr(rms_ref[:n], rms_gen[:n])
    return float(r)


def _onset_xcorr(y_ref: np.ndarray, y_gen: np.ndarray) -> tuple[float, float]:
    """Normalised cross-correlation of onset strength envelopes.

    Returns (peak_value, lag_ms).  Peak near 1.0 + lag near 0ms = rhythmic
    events land at the same times.
    """
    o_ref = librosa.onset.onset_strength(y=y_ref, sr=_SR, hop_length=_HOP).astype(np.float64)
    o_gen = librosa.onset.onset_strength(y=y_gen, sr=_SR, hop_length=_HOP).astype(np.float64)

    # Zero-mean unit-variance normalisation before cross-correlation
    def _norm(x):
        x = x - x.mean()
        s = x.std()
        return x / s if s > 1e-9 else x

    o_ref = _norm(o_ref); o_gen = _norm(o_gen)
    n = min(len(o_ref), len(o_gen))
    xcorr = scipy.signal.correlate(o_gen[:n], o_ref[:n], mode='full')
    lags  = scipy.signal.correlation_lags(n, n, mode='full')
    peak_idx  = int(np.argmax(xcorr))
    peak_val  = float(xcorr[peak_idx]) / n   # normalise by length
    lag_ms    = float(lags[peak_idx]) * _HOP / _SR * 1000.0
    return peak_val, lag_ms


def _kick_phase_err(y_ref: np.ndarray, y_gen: np.ndarray,
                    bpm: float) -> float:
    """Mean absolute kick phase error in ms.

    Bandpass-filters to 50–120 Hz (kick fundamental), detects onsets,
    computes each onset modulo the half-note period, and compares to reference.
    """
    half_note_s = 2 * 60.0 / bpm   # half-time kick period

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
    # Wrap: error can't exceed half the period
    err = min(err, half_note_s - err)
    return float(err * 1000.0)


def _chroma_cosine(y_ref: np.ndarray, y_gen: np.ndarray) -> float:
    """Cosine similarity of mean chroma_cens vectors (12-element pitch-class profile).

    Uses harmonic component only to suppress rhythm influence.
    """
    y_h_ref = librosa.effects.harmonic(y_ref, margin=8)
    y_h_gen = librosa.effects.harmonic(y_gen, margin=8)
    c_ref = librosa.feature.chroma_cens(y=y_h_ref, sr=_SR, hop_length=_HOP).mean(axis=1)
    c_gen = librosa.feature.chroma_cens(y=y_h_gen, sr=_SR, hop_length=_HOP).mean(axis=1)
    if c_ref.sum() < 1e-9 or c_gen.sum() < 1e-9:
        return 0.0
    return float(1.0 - cosine_dist(c_ref.astype(np.float64),
                                    c_gen.astype(np.float64)))


def _mfcc_dtw(y_ref: np.ndarray, y_gen: np.ndarray) -> float:
    """Normalised DTW distance on 13-coefficient MFCC sequences.

    Preserves temporal trajectory unlike mean-collapsed MFCC cosine.
    Returns accumulated cost / path length; lower = more similar.
    """
    m_ref = librosa.feature.mfcc(y=y_ref, sr=_SR, n_mfcc=13, hop_length=_HOP)
    m_gen = librosa.feature.mfcc(y=y_gen, sr=_SR, n_mfcc=13, hop_length=_HOP)
    D, wp = librosa.sequence.dtw(m_ref, m_gen, metric='euclidean')
    path_length = len(wp)
    if path_length == 0:
        return 999.0
    return float(D[-1, -1] / path_length)


def _tempogram_cosine(y_ref: np.ndarray, y_gen: np.ndarray) -> float:
    """Cosine similarity of mean tempogram vectors.

    Captures the full rhythmic hierarchy (half-time feel, double-time hi-hats)
    not just the dominant BPM.
    """
    o_ref = librosa.onset.onset_strength(y=y_ref, sr=_SR, hop_length=_HOP)
    o_gen = librosa.onset.onset_strength(y=y_gen, sr=_SR, hop_length=_HOP)
    t_ref = librosa.feature.tempogram(onset_envelope=o_ref, sr=_SR,
                                       hop_length=_HOP).mean(axis=1)
    t_gen = librosa.feature.tempogram(onset_envelope=o_gen, sr=_SR,
                                       hop_length=_HOP).mean(axis=1)
    if t_ref.sum() < 1e-9 or t_gen.sum() < 1e-9:
        return 0.0
    return float(1.0 - cosine_dist(t_ref.astype(np.float64),
                                    t_gen.astype(np.float64)))


def _spectral_contrast_cosine(y_ref: np.ndarray, y_gen: np.ndarray) -> float:
    """Cosine similarity of mean spectral contrast vectors (7-element).

    Spectral contrast measures peak-valley difference per sub-band — correlates
    with perceived presence/punch better than raw band energy.
    """
    sc_ref = librosa.feature.spectral_contrast(y=y_ref, sr=_SR, n_bands=6,
                                                hop_length=_HOP).mean(axis=1)
    sc_gen = librosa.feature.spectral_contrast(y=y_gen, sr=_SR, n_bands=6,
                                                hop_length=_HOP).mean(axis=1)
    if sc_ref.sum() < 1e-9 or sc_gen.sum() < 1e-9:
        return 0.0
    return float(1.0 - cosine_dist(sc_ref.astype(np.float64),
                                    sc_gen.astype(np.float64)))


def compare_audio(ref_path: str, gen_path: str,
                  bpm: float = 138.0) -> dict:
    """Compare two audio files.  Returns dict of metric values + pass/fail.

    Parameters
    ----------
    ref_path : str
        Path to reference WAV.
    gen_path : str
        Path to generated WAV.
    bpm : float
        Tempo in BPM (used for kick phase alignment).

    Returns
    -------
    dict with keys:
        rms_envelope_r, onset_xcorr_peak, onset_xcorr_lag_ms,
        kick_phase_err_ms, chroma_cosine, mfcc_dtw_dist,
        tempogram_cosine, spectral_contrast_cosine,
        passes (dict of bool per metric), overall_pass (bool)
    """
    y_ref = _load(ref_path)
    y_gen = _load(gen_path)

    rms_r           = _rms_envelope_r(y_ref, y_gen)
    xcorr, lag_ms   = _onset_xcorr(y_ref, y_gen)
    kick_err        = _kick_phase_err(y_ref, y_gen, bpm)
    chroma          = _chroma_cosine(y_ref, y_gen)
    dtw             = _mfcc_dtw(y_ref, y_gen)
    tempogram       = _tempogram_cosine(y_ref, y_gen)
    contrast        = _spectral_contrast_cosine(y_ref, y_gen)

    values = {
        'rms_envelope_r':           rms_r,
        'onset_xcorr_peak':         xcorr,
        'onset_xcorr_lag_ms':       lag_ms,
        'kick_phase_err_ms':        kick_err,
        'chroma_cosine':            chroma,
        'mfcc_dtw_dist':            dtw,
        'tempogram_cosine':         tempogram,
        'spectral_contrast_cosine': contrast,
    }

    passes = {}
    for key, (op, threshold, _weight) in _TARGETS.items():
        v = values[key]
        if op == '>=':
            passes[key] = v >= threshold
        else:
            passes[key] = v <= threshold

    high_weight_keys = [k for k, (_, _, w) in _TARGETS.items() if w == 'High']
    high_passes = sum(1 for k in high_weight_keys if passes[k])
    overall_pass = high_passes >= len(high_weight_keys) // 2 + 1

    return {**values, 'passes': passes, 'overall_pass': overall_pass}


def _print_report(result: dict, ref_path: str, gen_path: str) -> None:
    print(f"\nAudio Similarity Report")
    print(f"  Reference : {ref_path}")
    print(f"  Generated : {gen_path}")
    print()
    print(f"  {'Metric':<30} {'Value':>10}  {'Target':>10}  {'Weight':<8}  Result")
    print(f"  {'-'*30} {'-'*10}  {'-'*10}  {'-'*8}  ------")

    rows = [
        ('rms_envelope_r',           'RMS envelope r',         '{:.3f}',  '>= 0.70', 'High',   'Sidechain pump / energy trajectory match'),
        ('onset_xcorr_peak',         'Onset cross-corr peak',  '{:.3f}',  '>= 0.40', 'High',   'Rhythmic event timing'),
        ('kick_phase_err_ms',        'Kick phase error (ms)',   '{:.1f}',  '<= 30ms', 'High',   'Kick lands at same beat phase'),
        ('chroma_cosine',            'Chroma cosine',           '{:.3f}',  '>= 0.80', 'High',   'Same key / harmonic content'),
        ('mfcc_dtw_dist',            'MFCC DTW distance',       '{:.3f}',  '<= 0.30', 'Medium', 'Timbral trajectory over time'),
        ('tempogram_cosine',         'Tempogram cosine',        '{:.3f}',  '>= 0.80', 'Medium', 'Rhythmic hierarchy (half-time etc)'),
        ('spectral_contrast_cosine', 'Spectral contrast cos',   '{:.3f}',  '>= 0.70', 'Medium', 'Band presence / punch'),
    ]

    for key, label, fmt, target, weight, meaning in rows:
        val = result[key]
        passed = result['passes'][key]
        mark = 'PASS' if passed else 'FAIL'
        print(f"  {label:<30} {fmt.format(val):>10}  {target:>10}  {weight:<8}  {mark}  — {meaning}")

    lag = result['onset_xcorr_lag_ms']
    print(f"\n  Onset cross-corr lag: {lag:+.1f}ms  ({'aligned' if abs(lag) < 20 else 'OFFSET — events not time-aligned'})")

    print()
    overall = result['overall_pass']
    print(f"  OVERALL: {'PASS — cover is plausibly similar to reference' if overall else 'FAIL — cover does not sound like reference'}")
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
