# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""v3 parameter audit: measure sidechain, trancegate, filter, and lpenv behaviour.

Renders four WAV passes of trance_stream_v3.py, then measures five key parameters
before any source files are changed.  Confirms the sidechain perpetual-duck bug
(effects.py:327) and documents the actual state of trancegate shape, filter floor,
and lpenv sweep timing.

Usage::

    python tools/measure_v3_output.py [--bpm 140] [--bars 8] [--seed sunrise]
        [--out research/analysis/v3_measurements.json]

All subprocess calls use the repo root as cwd so trance_stream_v3.py resolves
relative imports correctly.

Dependencies (all already in the project): numpy, scipy, mido.
librosa is used for spectral centroid if available; otherwise computed inline.
"""
from __future__ import annotations

import argparse
import datetime
import json
import math
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
from scipy import signal as scipy_signal
from scipy.io import wavfile

try:
    import mido
except ImportError:
    raise ImportError("mido required: pip install mido")

try:
    import librosa
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False

REPO_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# WAV loading helpers
# ---------------------------------------------------------------------------

def _load_wav_mono(path: str) -> tuple[np.ndarray, int]:
    """Load a WAV file and return (mono_float32, sample_rate)."""
    with wave.open(path, "rb") as wf:
        n_channels = wf.getnchannels()
        framerate  = wf.getframerate()
        n_frames   = wf.getnframes()
        raw        = wf.readframes(n_frames)
    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if n_channels == 2:
        mono = pcm.reshape(-1, 2).mean(axis=1)
    else:
        mono = pcm.flatten()
    return mono, framerate


def _rms(arr: np.ndarray) -> float:
    if len(arr) == 0:
        return 0.0
    return float(np.sqrt(np.mean(arr.astype(np.float64) ** 2)))


def _rms_window(audio: np.ndarray, start: int, end: int) -> float:
    seg = audio[max(0, start):max(0, end)]
    return _rms(seg)


# ---------------------------------------------------------------------------
# Step 1: Render audio
# ---------------------------------------------------------------------------

def render_audio(bpm: float, bars: int, seed: str) -> dict[str, str]:
    """Run three subprocess renders and return paths to the WAV files."""
    paths = {
        "full":     "/tmp/v3_full.wav",
        "pad_solo": "/tmp/v3_pad_solo.wav",
        "kick_solo": "/tmp/v3_kick_solo.wav",
        "midi":     "/tmp/v3.mid",
    }
    renders = [
        # Full mix + MIDI
        [
            sys.executable, "trance_stream_v3.py",
            "--bars", str(bars),
            "--bpm",  str(bpm),
            "--seed", seed,
            "--wav",  paths["full"],
            "--out-midi", paths["midi"],
        ],
        # Pad solo
        [
            sys.executable, "trance_stream_v3.py",
            "--bars", str(bars),
            "--bpm",  str(bpm),
            "--seed", seed,
            "--solo", "pad",
            "--wav",  paths["pad_solo"],
        ],
        # Kick solo
        [
            sys.executable, "trance_stream_v3.py",
            "--bars", str(bars),
            "--bpm",  str(bpm),
            "--seed", seed,
            "--solo", "kick",
            "--wav",  paths["kick_solo"],
        ],
    ]
    for cmd in renders:
        label = " ".join(cmd[1:4])
        print(f"  Rendering: {label} ...")
        result = subprocess.run(
            cmd, cwd=str(REPO_ROOT),
            capture_output=True, text=True
        )
        if result.returncode != 0:
            print(f"  STDERR: {result.stderr[-2000:]}", file=sys.stderr)
            raise RuntimeError(f"Render failed: {cmd}")
    return paths


# ---------------------------------------------------------------------------
# M1: Sidechain perpetual-duck confirmation
# ---------------------------------------------------------------------------

def measure_m1_sidechain(
    full_wav: str, kick_wav: str, pad_wav: str, sr: int, bpm: float
) -> dict:
    """Measure sidechain duck depth and permanent-duck ratio.

    The perpetual-duck bug (effects.py:327) normalises IIR residuals to 1.0
    every bar. After the first kick the IIR state (zi) retains a residual that
    is normalised to full ducking. Expected: permanent_duck_ratio ~0.4 when
    buggy, ~1.0 when correct.
    """
    kick_audio, sr_k  = _load_wav_mono(kick_wav)
    full_audio, sr_f  = _load_wav_mono(full_wav)
    pad_audio,  sr_p  = _load_wav_mono(pad_wav)

    # Use the common sample rate
    assert sr_k == sr_f == sr_p == sr, \
        f"Sample rate mismatch: {sr_k}, {sr_f}, {sr_p}"

    window_50ms = int(sr * 0.050)

    # --- Find kick onsets using rising-edge detection ---
    # Simple RMS threshold misses because the kick has a long reverb tail that
    # keeps window RMS > 0.1 continuously.  Instead we look for windows where the
    # RMS rises sharply from the previous window (onset transient) and is above a
    # minimum level.  A 2× rise ratio and minimum 0.05 RMS reliably picks up the
    # attack while ignoring the decaying tail.  Onsets within 300 ms of a prior
    # onset are deduplicated (the kick body spans <300 ms).
    n_windows = len(kick_audio) // window_50ms
    window_rms: list[float] = []
    for i in range(n_windows):
        seg = kick_audio[i * window_50ms: (i + 1) * window_50ms]
        window_rms.append(_rms(seg))

    kick_onsets_s: list[float] = []
    last_onset_s = -1.0
    for i in range(1, n_windows):
        prev = window_rms[i - 1]
        curr = window_rms[i]
        t    = i * 0.050
        if curr > prev * 2.0 and curr > 0.05 and (t - last_onset_s) > 0.300:
            kick_onsets_s.append(t)
            last_onset_s = t

    per_cycle: list[dict] = []
    duck_depths: list[float] = []
    recovery_ms_list: list[float] = []

    pre_ms  = 200
    post_ms = 600
    win_ms  = 10

    pre_samples  = int(sr * pre_ms  / 1000)
    post_samples = int(sr * post_ms / 1000)
    win_samples  = int(sr * win_ms  / 1000)

    for t_kick in kick_onsets_s:
        kick_sample = int(t_kick * sr)

        pre_start = kick_sample - pre_samples
        pre_end   = kick_sample
        if pre_start < 0:
            continue
        pre_rms = _rms_window(full_audio, pre_start, pre_end)
        if pre_rms < 1e-6:
            continue

        # 10ms windows in [t_kick, t_kick + 600ms]
        post_rms_vals: list[float] = []
        n_post = post_samples // win_samples
        for j in range(n_post):
            s = kick_sample + j * win_samples
            e = s + win_samples
            post_rms_vals.append(_rms_window(full_audio, s, e))

        if not post_rms_vals:
            continue

        min_post = min(post_rms_vals)
        duck_depth = min_post / pre_rms if pre_rms > 0 else 1.0

        # Recovery: first window where RMS > 0.9 * pre_rms
        recovery_ms_val = float("nan")
        for j, rv in enumerate(post_rms_vals):
            if rv > 0.9 * pre_rms:
                recovery_ms_val = j * win_ms
                break

        duck_depths.append(duck_depth)
        if not math.isnan(recovery_ms_val):
            recovery_ms_list.append(recovery_ms_val)

        duck_depth_db = 20 * math.log10(max(duck_depth, 1e-9))
        per_cycle.append({
            "t_kick_s":       round(t_kick, 4),
            "pre_rms":        round(pre_rms, 6),
            "min_post_rms":   round(min_post, 6),
            "duck_depth_db":  round(duck_depth_db, 2),
            "recovery_ms":    round(recovery_ms_val, 1) if not math.isnan(recovery_ms_val) else None,
        })

    # Permanent duck ratio: mean RMS of pad in full mix between kicks /
    # mean RMS of pad solo at same positions
    # Compute global between-kick RMS (avoid kick onset windows)
    between_kick_mask = np.ones(len(full_audio), dtype=bool)
    onset_window_half = int(sr * 0.3)  # mask 300ms around each kick
    for t_kick in kick_onsets_s:
        s = max(0, int(t_kick * sr) - onset_window_half)
        e = min(len(full_audio), int(t_kick * sr) + onset_window_half)
        between_kick_mask[s:e] = False

    # Take the shorter of the two arrays
    n = min(len(full_audio), len(pad_audio))
    full_between = full_audio[:n][between_kick_mask[:n]]
    pad_between  = pad_audio[:n][between_kick_mask[:n]]

    full_btw_rms = _rms(full_between)
    pad_solo_rms = _rms(pad_between)

    # Permanent duck ratio: how much of the pad solo RMS survives in the full mix
    # outside kick windows.  If ducking is stuck at 0.4, ratio ≈ 0.4.
    # This is a rough estimate because full mix includes other instruments.
    # We use it directionally: <<1.0 confirms permanent ducking.
    if pad_solo_rms > 1e-6:
        permanent_duck_ratio = float(np.clip(full_btw_rms / pad_solo_rms, 0.0, 2.0))
    else:
        permanent_duck_ratio = float("nan")

    mean_duck_depth = float(np.mean(duck_depths)) if duck_depths else float("nan")
    mean_recovery   = float(np.mean(recovery_ms_list)) if recovery_ms_list else float("nan")
    min_duck_depth  = float(np.min(duck_depths))  if duck_depths else float("nan")
    max_duck_depth  = float(np.max(duck_depths))  if duck_depths else float("nan")

    # Bug confirmation note: the sidechain bug (effects.py:327) is latent — it does
    # not trigger when 4-on-floor kick patterns fill every bar, because the bar's
    # max(kick_env_smooth) is always the real kick peak.  The bug fires when a bar
    # has no kick (breakdown, fill, or bars before kick_on).  We confirm presence
    # of the bug by checking whether any kick cycle has zero recovery (recovery_ms
    # is None for >50% of kicks), which would indicate permanent ducking.
    # At 4-on-floor the audio evidence is: duck depth ~0.4 on each kick, recovery
    # in one time-constant (~160ms).  If no recovery is seen (None count > 50%),
    # the bug is actively manifesting.
    n_no_recovery = sum(1 for c in per_cycle if c["recovery_ms"] is None)
    bug_confirmed = (len(per_cycle) > 0 and n_no_recovery > len(per_cycle) * 0.5)

    return {
        "mean_duck_depth":      round(mean_duck_depth, 4),
        "min_duck_depth":       round(min_duck_depth,  4),
        "max_duck_depth":       round(max_duck_depth,  4),
        "mean_recovery_ms":     round(mean_recovery,   1) if not math.isnan(mean_recovery) else None,
        "permanent_duck_ratio": round(permanent_duck_ratio, 4) if not math.isnan(permanent_duck_ratio) else None,
        "n_kick_onsets":        len(kick_onsets_s),
        "bug_confirmed":        bug_confirmed,
        "per_cycle":            per_cycle,
    }


# ---------------------------------------------------------------------------
# M2: Trancegate actual shape
# ---------------------------------------------------------------------------

def measure_m2_trancegate(pad_wav: str, sr: int, bpm: float, bars: int) -> dict:
    """Measure trancegate trough/peak ratio, cycles/bar, and cosine fit quality.

    Uses Hilbert-transform envelope extraction, smoothed with a 5ms moving average.
    TRANCEGATE_AMOUNT=0.7 → expected trough=0.3, peak=1.0, trough/peak≈0.3.
    TRANCEGATE_SPEED=1.5 → expected 1.5 cycles/bar.
    """
    audio, sr_a = _load_wav_mono(pad_wav)
    assert sr_a == sr

    # Skip first bar to avoid lpenv swell
    bar_samples = int(sr * 4 * 60 / bpm)
    audio = audio[bar_samples:]
    if len(audio) < sr:
        return {"error": "pad solo too short after skipping bar 1"}

    # Hilbert envelope
    analytic = scipy_signal.hilbert(audio.astype(np.float64))
    envelope = np.abs(analytic).astype(np.float32)

    # Smoothing window must be large enough to suppress the audio-rate carrier
    # (fundamental ~48 Hz → period 21 ms) and reveal the gate modulation.
    # The trancegate period at 1.5 cycles/bar @ 140 BPM is 1.14 s.
    # A window of ~1/4 of the gate period (≈ 285 ms) low-passes the carrier
    # while preserving the gate envelope shape.
    gate_period_s  = (4.0 * 60.0 / bpm) / 1.5   # 1.5 = TRANCEGATE_SPEED
    smooth_samples = max(1, int(sr * gate_period_s / 4.0))
    kernel = np.ones(smooth_samples, dtype=np.float32) / smooth_samples
    envelope = np.convolve(envelope, kernel, mode="same")

    # Trough/peak ratio
    env_max = float(envelope.max())
    env_min = float(envelope.min())
    if env_max < 1e-9:
        return {"error": "envelope is silent"}

    trough_peak_ratio = env_min / env_max

    # Cycles per bar: count zero-crossings of (envelope - midpoint)
    midpoint = (env_max + env_min) / 2.0
    centered = envelope - midpoint
    sign_changes = np.where(np.diff(np.sign(centered)))[0]
    n_crossings = len(sign_changes)
    n_cycles    = n_crossings / 2.0
    duration_bars = (len(audio) / sr) / (4.0 * 60.0 / bpm)
    cycles_per_bar = n_cycles / max(duration_bars, 1.0)

    # Cosine fit: fit one cycle of the expected trancegate shape.
    # Normalise envelope to [0,1] for shape comparison.
    env_norm = (envelope - env_min) / max(env_max - env_min, 1e-9)

    # Expected cycle period in samples
    speed          = 1.5
    bar_s          = 4.0 * 60.0 / bpm
    period_s       = bar_s / speed
    period_samples = int(sr * period_s)

    # Take a 3-cycle chunk from the middle of the recording for the fit.
    # The phase of the cosine at the start of the chunk is unknown (it depends
    # on the bar offset at render time), so we find the best-matching phase by
    # cross-correlating one reference cosine cycle against the segment and using
    # the lag as the phase offset.
    mid = len(env_norm) // 2
    fit_len = min(3 * period_samples, len(env_norm) - mid)
    seg = env_norm[mid: mid + fit_len]
    t   = np.arange(len(seg)) / sr

    # Find the best-matching phase of the reference cosine by scanning 360 phase
    # values over one period.  The rendering bar offset is unknown so we cannot
    # assume a fixed phase; a brute-force sweep is cheap (360 cos evals over the
    # segment length) and avoids cross-correlation wrap ambiguity.
    best_rms   = 1e9
    best_phase = 0.0
    for phi in np.linspace(0.0, 2.0 * np.pi, 360, endpoint=False):
        expected_cand = (1.0 + np.cos(2.0 * np.pi * t / period_s + phi)) / 2.0
        err = float(np.sqrt(np.mean((seg - expected_cand[:len(seg)]) ** 2)))
        if err < best_rms:
            best_rms   = err
            best_phase = phi

    expected_norm = (1.0 + np.cos(2.0 * np.pi * t / period_s + best_phase)) / 2.0
    expected_norm = expected_norm[:len(seg)]

    cosine_rms_error = float(best_rms)
    # Threshold 0.20: at 140 BPM with 286ms smoothing window the cosine edges are
    # rounded by ~0.1–0.15 RMS; a threshold of 0.20 reliably separates a smoothed
    # cosine from a binary (LFSR) gate shape.
    shape_is_cosine  = cosine_rms_error < 0.20

    return {
        "trough_peak_ratio":    round(trough_peak_ratio,   4),
        "env_min":              round(env_min,              6),
        "env_max":              round(env_max,              6),
        "cycles_per_bar":       round(cycles_per_bar,       3),
        "cosine_fit_rms_error": round(cosine_rms_error,     4),
        "shape_is_cosine":      shape_is_cosine,
        "expected_trough_peak": 0.3,    # 1 - TRANCEGATE_AMOUNT
        "expected_cycles_bar":  1.5,    # TRANCEGATE_SPEED
    }


# ---------------------------------------------------------------------------
# M3: Filter floor — steady-state spectral centroid
# ---------------------------------------------------------------------------

def _spectral_centroid_inline(audio: np.ndarray, sr: int,
                               chunk: int = 4096) -> tuple[float, float]:
    """Compute mean spectral centroid and 95% rolloff using inline FFT."""
    hop = chunk // 2
    centroids: list[float] = []
    rolloffs:  list[float] = []
    n_steps = (len(audio) - chunk) // hop
    freqs = np.fft.rfftfreq(chunk, 1.0 / sr)
    for i in range(n_steps):
        seg  = audio[i * hop: i * hop + chunk]
        win  = np.hanning(chunk).astype(np.float32)
        spec = np.abs(np.fft.rfft(seg * win))
        power = spec ** 2
        denom = float(power.sum())
        if denom < 1e-12:
            continue
        centroids.append(float((freqs * power).sum() / denom))
        # 95% rolloff
        cumpower = np.cumsum(power)
        idx = np.searchsorted(cumpower, 0.95 * cumpower[-1])
        rolloffs.append(float(freqs[min(idx, len(freqs) - 1)]))
    mean_c = float(np.mean(centroids)) if centroids else 0.0
    mean_r = float(np.mean(rolloffs))  if rolloffs  else 0.0
    return mean_c, mean_r


def measure_m3_filter_floor(pad_wav: str, sr: int, bpm: float) -> dict:
    """Measure steady-state spectral centroid of pad solo (skip bar 1).

    SA rlpf(0.5) → (0.5 * 12)^4 = 1296 Hz.  SA target range 800–1200 Hz.
    """
    audio, sr_a = _load_wav_mono(pad_wav)
    assert sr_a == sr

    bar_samples = int(sr * 4 * 60 / bpm)
    audio = audio[bar_samples:]  # skip first bar
    if len(audio) < sr:
        return {"error": "pad solo too short after skipping bar 1"}

    if HAS_LIBROSA:
        # librosa centroid
        y = audio.astype(np.float32)
        centroid_frames = librosa.feature.spectral_centroid(
            y=y, sr=sr, n_fft=4096, hop_length=2048
        )[0]
        rolloff_frames = librosa.feature.spectral_rolloff(
            y=y, sr=sr, n_fft=4096, hop_length=2048, roll_percent=0.95
        )[0]
        mean_centroid = float(np.mean(centroid_frames))
        mean_rolloff  = float(np.mean(rolloff_frames))
    else:
        mean_centroid, mean_rolloff = _spectral_centroid_inline(audio, sr)

    # rlpf(0.5) formula prediction
    formula_hz = (0.5 * 12.0) ** 4   # = 1296 Hz
    sa_target_lo, sa_target_hi = 800.0, 1200.0
    in_sa_range = sa_target_lo <= mean_centroid <= sa_target_hi
    in_formula  = abs(mean_centroid - formula_hz) / formula_hz < 0.10

    return {
        "steady_state_centroid_hz":  round(mean_centroid,  1),
        "rolloff_hz":                round(mean_rolloff,   1),
        "formula_prediction_hz":     formula_hz,
        "sa_target_range":           [sa_target_lo, sa_target_hi],
        "in_sa_target_range":        in_sa_range,
        "within_10pct_of_formula":   in_formula,
    }


# ---------------------------------------------------------------------------
# M4: lpenv sweep shape (temporal centroid rise)
# ---------------------------------------------------------------------------

def _detect_pad_chord_onsets(pad_solo: np.ndarray, sr: int, bpm: float) -> list[float]:
    """Detect pad chord trigger times from the pad solo WAV using onset detection.

    The write_midi() implementation is a minimal stub that only writes tempo — it
    does not include note events.  We therefore derive trigger times directly from
    the pad audio.

    Pad chords change every 4 bars (SA canonical).  Each chord onset produces a
    brief amplitude surge from the lpenv attack.  We find onsets using a smoothed
    envelope derivative, then keep only onsets separated by at least 0.5 s (the
    trancegate modulation has a ~1.14 s period; chord change intervals are
    4 bars ≈ 6.86 s at 140 BPM, so there is no ambiguity at this gap threshold).
    """
    env = np.abs(scipy_signal.hilbert(pad_solo.astype(np.float64))).astype(np.float32)
    # Smooth to suppress trancegate modulation (~1.14s period)
    gate_period_s  = (4.0 * 60.0 / bpm) / 1.5
    sm = max(1, int(sr * gate_period_s / 4.0))
    env_sm = np.convolve(env, np.ones(sm) / sm, mode="same")

    # Derivative of smoothed envelope; positive slope = onset transient
    deriv = np.diff(env_sm.astype(np.float64))
    threshold = float(np.percentile(np.abs(deriv), 99)) * 0.5

    # 50ms windows
    win = int(sr * 0.050)
    n_win = len(deriv) // win
    win_deriv: list[float] = []
    for i in range(n_win):
        seg = deriv[i * win: (i + 1) * win]
        win_deriv.append(float(seg.max()))

    onsets: list[float] = []
    last_t = -1.0
    for i, d in enumerate(win_deriv):
        t = i * 0.050
        if d > threshold and (t - last_t) > 0.500:
            onsets.append(t)
            last_t = t

    return onsets


def measure_m4_lpenv_sweep(full_wav: str, pad_wav: str, midi_path: str,
                            sr: int, bpm: float) -> dict:
    """Measure centroid rise time after pad chord triggers.

    Chord trigger times are derived from the pad solo WAV using onset detection
    (the MIDI write_midi() is a stub that does not output note events).  The
    spectral centroid trajectory is computed from the full mix WAV in 10ms windows
    for 500ms after each detected trigger.
    Expected: centroid peaks ~60ms after trigger (SA target).
    """
    audio, sr_a = _load_wav_mono(full_wav)
    assert sr_a == sr

    pad_audio, sr_p = _load_wav_mono(pad_wav)
    assert sr_p == sr

    # --- Detect pad chord onsets from pad solo ---
    pad_trigger_times_s = _detect_pad_chord_onsets(pad_audio, sr, bpm)

    if not pad_trigger_times_s:
        return {"error": "no pad chord onsets detected from pad solo WAV"}

    win_ms  = 10
    post_ms = 500
    win_samples  = int(sr * win_ms  / 1000)
    post_samples = int(sr * post_ms / 1000)

    n_post = post_samples // win_samples
    freqs  = np.fft.rfftfreq(win_samples, 1.0 / sr)

    peak_centroid_list:  list[float] = []
    time_to_peak_list:   list[float] = []
    decay_to_90pct_list: list[float] = []

    for t_trig in pad_trigger_times_s:
        trig_sample = int(t_trig * sr)

        # Base centroid: mean of centroid 100-200ms before trigger
        base_start = trig_sample - int(sr * 0.200)
        base_end   = trig_sample - int(sr * 0.100)
        if base_start < 0:
            continue

        base_seg = audio[base_start:base_end]
        if len(base_seg) < win_samples:
            continue
        base_c_vals: list[float] = []
        for j in range(len(base_seg) // win_samples):
            s = j * win_samples
            seg = base_seg[s: s + win_samples]
            sp = np.abs(np.fft.rfft(seg * np.hanning(win_samples).astype(np.float32)))
            pw = sp ** 2
            d = float(pw.sum())
            if d > 1e-12:
                base_c_vals.append(float((freqs * pw).sum() / d))
        base_centroid = float(np.mean(base_c_vals)) if base_c_vals else 0.0

        # Post-trigger centroid trajectory
        centroids_post: list[float] = []
        for j in range(n_post):
            s = trig_sample + j * win_samples
            e = s + win_samples
            if e > len(audio):
                break
            seg = audio[s:e]
            sp  = np.abs(np.fft.rfft(seg * np.hanning(win_samples).astype(np.float32)))
            pw  = sp ** 2
            d   = float(pw.sum())
            if d > 1e-12:
                centroids_post.append(float((freqs * pw).sum() / d))
            else:
                centroids_post.append(0.0)

        if not centroids_post:
            continue

        peak_idx     = int(np.argmax(centroids_post))
        peak_c       = centroids_post[peak_idx]
        time_to_peak = peak_idx * win_ms

        # Decay: time until centroid drops to 90% of base centroid after peak
        decay_90 = float("nan")
        if base_centroid > 0:
            for j in range(peak_idx, len(centroids_post)):
                if centroids_post[j] <= 0.90 * base_centroid:
                    decay_90 = (j - peak_idx) * win_ms
                    break

        peak_centroid_list.append(peak_c)
        time_to_peak_list.append(float(time_to_peak))
        if not math.isnan(decay_90):
            decay_to_90pct_list.append(decay_90)

    if not peak_centroid_list:
        return {"error": "could not compute centroid trajectory for any trigger"}

    return {
        "mean_peak_centroid_hz":  round(float(np.mean(peak_centroid_list)),  1),
        "mean_time_to_peak_ms":   round(float(np.mean(time_to_peak_list)),   1),
        "mean_decay_to_90pct_ms": round(float(np.mean(decay_to_90pct_list)), 1)
                                  if decay_to_90pct_list else None,
        "n_triggers_analysed":    len(peak_centroid_list),
        "sa_target_time_to_peak_ms": 60,
    }


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def _check(value: float, target: float, tol: float = 0.10) -> str:
    """Return checkmark if value is within tol fraction of target."""
    if math.isnan(value):
        return "?"
    return "OK" if abs(value - target) / max(abs(target), 1e-9) <= tol else "MISS"


def _in_range(value: float, lo: float, hi: float) -> str:
    if math.isnan(value):
        return "?"
    return "OK" if lo <= value <= hi else "MISS"


def print_table(m1: dict, m2: dict, m3: dict, m4: dict,
                bpm: float, bars: int, seed: str, out_path: str) -> None:

    print()
    print("=== v3 Parameter Audit Results ===")
    print(f"Seed: {seed}  BPM: {bpm}  Bars: {bars}")
    print()

    # M1
    print("M1 Sidechain (perpetual-duck bug)")
    if "error" not in m1:
        pdr   = m1["permanent_duck_ratio"]
        mdd   = m1["mean_duck_depth"]
        rec   = m1["mean_recovery_ms"]
        label = "[BUG CONFIRMED -- should be ~1.0 between kicks]" if m1["bug_confirmed"] else "[no bug detected]"
        pdr_s = f"{pdr:.2f}" if pdr is not None else "n/a"
        mdd_s = f"{20*math.log10(max(mdd,1e-9)):.1f} dB" if mdd and not math.isnan(mdd) else "n/a"
        rec_s = f"{rec:.0f} ms" if rec and not math.isnan(rec) else "n/a"
        print(f"  Permanent duck ratio:  {pdr_s}  {label}")
        print(f"  Mean duck depth:       {mdd_s}")
        print(f"  Mean recovery:         {rec_s}")
        print(f"  Kick onsets found:     {m1['n_kick_onsets']}")
    else:
        print(f"  ERROR: {m1['error']}")

    print()

    # M2
    print("M2 Trancegate shape")
    if "error" not in m2:
        tpr = m2["trough_peak_ratio"]
        cpb = m2["cycles_per_bar"]
        cfe = m2["cosine_fit_rms_error"]
        cosine_label = "[shape IS cosine]" if m2["shape_is_cosine"] else "[NOT cosine]"
        tpr_flag = "OK" if abs(tpr - 0.30) < 0.10 else "MISS"
        cpb_flag = "OK" if abs(cpb - 1.50) < 0.15 else "MISS"
        print(f"  Trough/peak ratio:     {tpr:.4f}  [expected ~0.30 for amount=0.7] {tpr_flag}")
        print(f"  Cycles per bar:        {cpb:.3f}  [expected 1.50] {cpb_flag}")
        print(f"  Cosine fit error:      {cfe:.4f} {cosine_label}")
    else:
        print(f"  ERROR: {m2['error']}")

    print()

    # M3
    print("M3 Filter floor (steady-state centroid)")
    if "error" not in m3:
        cen   = m3["steady_state_centroid_hz"]
        roll  = m3["rolloff_hz"]
        fml   = m3["formula_prediction_hz"]
        cen_fml_flag  = "OK" if m3["within_10pct_of_formula"]  else "MISS"
        cen_sa_flag   = "OK" if m3["in_sa_target_range"] else "MISS"
        print(f"  Centroid:              {cen:.0f} Hz  "
              f"[formula predicts {fml:.0f} Hz {cen_fml_flag}, SA target 800-1200 Hz {cen_sa_flag}]")
        print(f"  Rolloff (95%):         {roll:.0f} Hz")
    else:
        print(f"  ERROR: {m3['error']}")

    print()

    # M4
    print("M4 lpenv sweep")
    if "error" not in m4:
        ttp  = m4["mean_time_to_peak_ms"]
        pc   = m4["mean_peak_centroid_hz"]
        d90  = m4["mean_decay_to_90pct_ms"]
        n    = m4["n_triggers_analysed"]
        ttp_flag = "OK" if abs(ttp - 60.0) / 60.0 <= 0.10 else "MISS"
        d90_s = f"{d90:.0f} ms" if d90 else "n/a"
        print(f"  Time to centroid peak: {ttp:.0f} ms   [SA target: 60 ms] {ttp_flag}")
        print(f"  Peak centroid:         {pc:.0f} Hz")
        print(f"  Decay to 90%:          {d90_s}")
        print(f"  Triggers analysed:     {n}")
    else:
        print(f"  ERROR: {m4['error']}")

    print()
    print(f"=== Results written to {out_path} ===")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--bpm",  type=float, default=140.0)
    parser.add_argument("--bars", type=int,   default=8)
    parser.add_argument("--seed", default="sunrise")
    parser.add_argument("--out",  default="research/analysis/v3_measurements.json",
                        help="Output JSON path (relative to repo root or absolute)")
    args = parser.parse_args()

    bpm  = args.bpm
    bars = args.bars
    seed = args.seed
    sr   = 44100

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"=== v3 Parameter Audit ===")
    print(f"BPM={bpm}  Bars={bars}  Seed={seed!r}")
    print()

    # --- Step 1: Render ---
    print("Step 1: Rendering audio...")
    paths = render_audio(bpm, bars, seed)
    print("  Done.")
    print()

    # --- Step 2: M1 Sidechain ---
    print("Step 2: M1 — Sidechain perpetual-duck...")
    m1 = measure_m1_sidechain(
        paths["full"], paths["kick_solo"], paths["pad_solo"], sr, bpm
    )
    print(f"  Done. n_kick_onsets={m1.get('n_kick_onsets', '?')}  "
          f"bug_confirmed={m1.get('bug_confirmed', '?')}")
    print()

    # --- Step 3: M2 Trancegate ---
    print("Step 3: M2 — Trancegate shape...")
    m2 = measure_m2_trancegate(paths["pad_solo"], sr, bpm, bars)
    print(f"  Done. trough_peak={m2.get('trough_peak_ratio','?')}  "
          f"cycles_per_bar={m2.get('cycles_per_bar','?')}")
    print()

    # --- Step 4: M3 Filter floor ---
    print("Step 4: M3 — Filter floor...")
    m3 = measure_m3_filter_floor(paths["pad_solo"], sr, bpm)
    print(f"  Done. centroid={m3.get('steady_state_centroid_hz','?')} Hz")
    print()

    # --- Step 5: M4 lpenv sweep ---
    print("Step 5: M4 — lpenv sweep shape...")
    m4 = measure_m4_lpenv_sweep(paths["full"], paths["pad_solo"], paths["midi"], sr, bpm)
    print(f"  Done. time_to_peak={m4.get('mean_time_to_peak_ms','?')} ms")
    print()

    # --- Step 6: Write JSON ---
    m1_out = {k: v for k, v in m1.items() if k != "per_cycle"}
    results = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "bpm":  bpm,
        "bars": bars,
        "seed": seed,
        "M1_sidechain":       m1_out,
        "M2_trancegate":      m2,
        "M3_filter_floor":    m3,
        "M4_lpenv_sweep":     m4,
        "M5_sidechain_per_cycle": m1.get("per_cycle", []),
    }

    with open(out_path, "w") as fh:
        json.dump(results, fh, indent=2, default=str)

    # --- Step 7: Print table ---
    print_table(m1, m2, m3, m4, bpm, bars, seed, str(out_path))


if __name__ == "__main__":
    main()
