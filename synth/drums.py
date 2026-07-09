# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Drum synthesis — all seeded for determinism.  No Python sample loops.

Every function builds its signal via numpy vectorised operations; the only
loops present are over a small bounded constant (e.g. 3 noise bursts for
clap, or 4 harmonics for pulse_texture FM) — never over individual samples.

All functions return (buf_l, buf_r) as float32 stereo arrays of equal length.
"""

from __future__ import annotations

import numpy as np
from scipy.signal import butter, lfilter, lfilter_zi


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _butter_filter(
    signal: np.ndarray,
    cutoff_hz: float,
    sr: int,
    btype: str,
    order: int = 2,
) -> np.ndarray:
    """Apply a Butterworth filter, initialised at steady state."""
    nyq = sr / 2.0
    cutoff = float(np.clip(cutoff_hz, 10.0, nyq * 0.99)) / nyq
    b, a = butter(order, cutoff, btype=btype)
    zi = lfilter_zi(b, a) * signal[0]
    out, _ = lfilter(b, a, signal, zi=zi)
    return out.astype(np.float32)


def _bandpass(
    signal: np.ndarray,
    lo_hz: float,
    hi_hz: float,
    sr: int,
    order: int = 2,
) -> np.ndarray:
    """Apply a 2-pole Butterworth band-pass filter."""
    nyq = sr / 2.0
    lo = float(np.clip(lo_hz, 10.0, nyq * 0.99)) / nyq
    hi = float(np.clip(hi_hz, lo + 1e-4, nyq * 0.999)) / nyq
    b, a = butter(order, [lo, hi], btype="bandpass")
    zi = lfilter_zi(b, a) * signal[0]
    out, _ = lfilter(b, a, signal, zi=zi)
    return out.astype(np.float32)


# ---------------------------------------------------------------------------
# Drum voices
# ---------------------------------------------------------------------------

def kick(sr: int = 44100, seed: int = 42,
         decay_s: float = 0.12, pitch_floor: float = 50.0
         ) -> tuple[np.ndarray, np.ndarray]:
    """Synthesise one kick drum hit.

    Model: sine wave with fast pitch drop + short noise click.

    Pitch envelope fitted to real TR-909 measurements:
      285 Hz → 50 Hz, time constant 31 ms.
    decay_s controls amplitude envelope length: punchy (0.12s) to boomy (0.25s).
    Click: high-frequency noise burst in the first 10 ms, tapered to zero.
    Total length: max(decay_s * 1.6, 0.2) seconds.

    Returns (buf_l, buf_r) — mono signal mirrored to stereo.
    """
    rng = np.random.default_rng(seed)
    total_s = max(decay_s * 1.6, 0.2)
    n_samples = int(sr * total_s)
    t = np.arange(n_samples, dtype=np.float64) / sr

    # Pitch envelope fitted to TR-909 zero-crossing measurements:
    # starts at 285 Hz (floor + 235), decays with tau=31ms to floor=50 Hz.
    pitch_decay = 0.031
    freq = pitch_floor + 235.0 * np.exp(-t / pitch_decay)

    # Instantaneous phase via cumulative sum (vectorised, no sample loop).
    phase = 2.0 * np.pi * np.cumsum(freq) / sr
    tone = np.sin(phase)

    # Amplitude envelope: linear attack then exponential decay.
    attack_n = int(0.002 * sr)
    amp = np.empty(n_samples, dtype=np.float64)
    amp[:attack_n] = np.linspace(0.0, 1.0, attack_n)
    amp[attack_n:] = np.exp(-(t[attack_n:] - t[attack_n]) / decay_s)

    # Click transient: noise burst in first 10 ms, linearly faded.
    click_n = int(0.010 * sr)
    click = rng.standard_normal(click_n) * np.linspace(0.3, 0.0, click_n)

    signal = tone * amp
    signal[:click_n] += click
    signal = np.clip(signal, -1.0, 1.0).astype(np.float32)
    return signal, signal.copy()


def hihat(
    sr: int = 44100, decay_s: float = 0.08, seed: int = 42
) -> tuple[np.ndarray, np.ndarray]:
    """Synthesise one closed hi-hat hit.

    Model: white noise, high-pass filtered at 6 kHz, exponential decay.

    Total length: max(decay_s × 5, 0.1) seconds.

    Returns (buf_l, buf_r).
    """
    rng = np.random.default_rng(seed)
    total_s = max(decay_s * 5.0, 0.1)
    n_samples = int(sr * total_s)
    t = np.arange(n_samples, dtype=np.float64) / sr

    # White noise source.
    noise = rng.standard_normal(n_samples).astype(np.float32)

    # High-pass filter at 6 kHz.
    filtered = _butter_filter(noise, cutoff_hz=6000.0, sr=sr, btype="high", order=2)

    # Instantaneous attack, exponential decay envelope.
    amp = np.exp(-t / decay_s).astype(np.float32)

    signal = (filtered * amp).astype(np.float32)
    peak = np.abs(signal).max()
    if peak > 1e-9:
        signal = signal / peak
    return signal, signal.copy()


def clap(sr: int = 44100, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """Synthesise one clap hit.

    Model: three noise bursts at t = 0, 10 ms, 20 ms with decaying amplitude,
    band-pass filtered 1 kHz – 8 kHz.  Total length ≈ 200 ms.

    Returns (buf_l, buf_r).
    """
    rng = np.random.default_rng(seed)
    total_s = 0.20
    n_samples = int(sr * total_s)
    t = np.arange(n_samples, dtype=np.float64) / sr

    signal = np.zeros(n_samples, dtype=np.float64)

    # 3 noise bursts; each bounded iteration generates one burst — not a
    # sample loop.  Amplitudes decay: 1.0, 0.6, 0.3.
    burst_offsets_s = [0.000, 0.010, 0.020]
    burst_amps = [1.0, 0.6, 0.3]
    burst_decay_s = 0.018  # fast decay per burst

    for offset_s, amp_scale in zip(burst_offsets_s, burst_amps):
        offset_n = int(offset_s * sr)
        if offset_n >= n_samples:
            continue
        remaining = n_samples - offset_n
        t_burst = np.arange(remaining, dtype=np.float64) / sr
        noise_burst = rng.standard_normal(remaining)
        env = amp_scale * np.exp(-t_burst / burst_decay_s)
        signal[offset_n:] += noise_burst * env

    # Band-pass 1 kHz – 8 kHz.
    signal_f32 = signal.astype(np.float32)
    filtered = _bandpass(signal_f32, lo_hz=1000.0, hi_hz=8000.0, sr=sr, order=2)

    peak = np.abs(filtered).max()
    if peak > 1e-9:
        filtered = filtered / peak
    return filtered, filtered.copy()


# Gain constant matching SA's idiom: pulse!16, dec(.1) — quiet texture layer.
GAIN_PULSE: float = 0.12


def pulse_texture(
    step: int,
    total_steps: int,
    n_samples: int,
    sr: int = 44100,
) -> tuple[np.ndarray, np.ndarray]:
    """SA's pulse texture: sine carrier + FM, modulated by time position.

    SA's idiom: pulse!16, dec(.1), fm(time).fmh(time)
      - Carrier: sine at 80 Hz.
      - FM index depth scales linearly with step/total_steps (0 at step 0,
        max_depth at the final step), modelling fm(time).
      - FM modulator frequency also scales with step/total_steps, modelling
        fmh(time) (harmonic ratio of modulator).
      - Very short buffer (n_samples = samples_per_sixteenth typically).
      - Output gain: GAIN_PULSE = 0.12.

    Returns (buf_l, buf_r) — mono mirrored to stereo.
    """
    t = np.arange(n_samples, dtype=np.float64) / sr
    progress = float(step) / max(total_steps - 1, 1)  # 0.0 → 1.0

    carrier_hz = 80.0
    # FM index 0 at step=0, rising to 4.0 at step=total_steps-1.
    fm_depth = 4.0 * progress
    # Modulator frequency rises from carrier_hz × 1 to carrier_hz × 3.
    mod_hz = carrier_hz * (1.0 + 2.0 * progress)

    modulator = np.sin(2.0 * np.pi * mod_hz * t)
    phase = 2.0 * np.pi * carrier_hz * t + fm_depth * modulator
    signal = (np.sin(phase) * GAIN_PULSE).astype(np.float32)

    return signal, signal.copy()
