# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# synth/filters.py
# Stateful digital filters using scipy.signal.lfilter.
# All functions accept and return filter state (zi) for sample-continuous processing.

import numpy as np
from scipy.signal import butter, lfilter, lfilter_zi


def rlpf_to_hz(slider: float) -> float:
    """SA's exact rlpf formula: (slider * 12) ** 4.

    slider=0.877 -> 12267 Hz. slider=0.593 -> 2563 Hz.
    Source: research/analysis/switch_angel_vocabulary.md
    """
    return (slider * 12.0) ** 4.0


def lpf(
    signal: np.ndarray,
    cutoff_hz: float,
    sr: int,
    zi: np.ndarray = None,
) -> tuple[np.ndarray, np.ndarray]:
    """First-order low-pass filter.

    Returns (filtered_signal, zi) where zi is the filter state for the next call.
    """
    nyq = sr / 2.0
    cutoff = np.clip(cutoff_hz, 10.0, nyq * 0.99) / nyq
    b, a = butter(1, cutoff, btype="low")
    if zi is None:
        zi = lfilter_zi(b, a) * (signal[0] if len(signal) > 0 else 0.0)
    out, zi_out = lfilter(b, a, signal, zi=zi.reshape(-1))
    return out.astype(np.float32), zi_out


def hpf(
    signal: np.ndarray,
    cutoff_hz: float,
    sr: int,
    zi: np.ndarray = None,
) -> tuple[np.ndarray, np.ndarray]:
    """First-order high-pass filter.

    Returns (filtered_signal, zi) where zi is the filter state for the next call.
    """
    nyq = sr / 2.0
    cutoff = np.clip(cutoff_hz, 10.0, nyq * 0.99) / nyq
    b, a = butter(1, cutoff, btype="high")
    if zi is None:
        zi = lfilter_zi(b, a) * (signal[0] if len(signal) > 0 else 0.0)
    out, zi_out = lfilter(b, a, signal, zi=zi.reshape(-1))
    return out.astype(np.float32), zi_out


def lpf2(
    signal: np.ndarray,
    cutoff_hz: float,
    q: float,
    sr: int,
    zi: np.ndarray = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Second-order low-pass filter (resonant).

    Returns (filtered_signal, zi) where zi is the filter state for the next call.

    q: Q factor (0.5-10). q=0.707 is Butterworth (no resonance peak).
    """
    nyq = sr / 2.0
    cutoff = np.clip(cutoff_hz, 10.0, nyq * 0.99) / nyq
    # Standard biquad LPF parameterised by corner frequency and Q.
    wc = np.pi * cutoff  # normalised angular frequency (0..pi); cutoff is f/nyq
    cos_wc = np.cos(wc)
    alpha = np.sin(wc) / (2.0 * q)
    b0 = (1.0 - cos_wc) / 2.0
    b1 = 1.0 - cos_wc
    b2 = (1.0 - cos_wc) / 2.0
    a0 = 1.0 + alpha
    a1 = -2.0 * cos_wc
    a2 = 1.0 - alpha
    b_q = np.array([b0 / a0, b1 / a0, b2 / a0])
    a_q = np.array([1.0, a1 / a0, a2 / a0])

    if zi is None:
        zi = lfilter_zi(b_q, a_q) * (signal[0] if len(signal) > 0 else 0.0)
    out, zi_out = lfilter(b_q, a_q, signal, zi=zi.reshape(-1))
    return out.astype(np.float32), zi_out
