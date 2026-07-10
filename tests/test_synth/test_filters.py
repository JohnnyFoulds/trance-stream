# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Numerical tests for synth/filters.py — no audio hardware, no file I/O."""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

import numpy as np
import pytest

from synth.filters import hpf, lpf, lpf2, rlpf_to_hz

SR = 44100
N = 44100  # one second of samples


def _sine_tone(freq_hz: float, n: int = N) -> np.ndarray:
    t = np.arange(n, dtype=np.float64)
    return np.sin(2.0 * np.pi * freq_hz / SR * t).astype(np.float32)


def _rms(buf: np.ndarray) -> float:
    return float(np.sqrt(np.mean(buf.astype(np.float64) ** 2)))


# ---------------------------------------------------------------------------
# rlpf_to_hz
# ---------------------------------------------------------------------------


def test_rlpf_to_hz_high_slider():
    hz = rlpf_to_hz(0.877)
    assert 12000 <= hz <= 12500, f"Expected 12000–12500 Hz, got {hz:.1f}"


def test_rlpf_to_hz_mid_slider():
    hz = rlpf_to_hz(0.593)
    assert 2400 <= hz <= 2700, f"Expected 2400–2700 Hz, got {hz:.1f}"


# ---------------------------------------------------------------------------
# lpf
# ---------------------------------------------------------------------------


def test_lpf_passes_low_frequency():
    """lpf at 1000 Hz should pass 100 Hz with little attenuation."""
    sig = _sine_tone(100)
    out, _ = lpf(sig, 1000, SR)
    assert _rms(out) > 0.7 * _rms(sig)


def test_lpf_attenuates_high_frequency():
    """lpf at 1000 Hz should attenuate 10000 Hz by > 12 dB."""
    sig = _sine_tone(10000)
    out, _ = lpf(sig, 1000, SR)
    assert _rms(out) < 0.25 * _rms(sig)


# ---------------------------------------------------------------------------
# hpf
# ---------------------------------------------------------------------------


def test_hpf_passes_high_frequency():
    """hpf at 1000 Hz should pass 10000 Hz."""
    sig = _sine_tone(10000)
    out, _ = hpf(sig, 1000, SR)
    assert _rms(out) > 0.7 * _rms(sig)


def test_hpf_attenuates_low_frequency():
    """hpf at 1000 Hz should attenuate 100 Hz."""
    sig = _sine_tone(100)
    out, _ = hpf(sig, 1000, SR)
    assert _rms(out) < 0.25 * _rms(sig)


# ---------------------------------------------------------------------------
# lpf2
# ---------------------------------------------------------------------------


def test_lpf2_attenuates_high_frequency():
    """2nd-order lpf at 1000 Hz, q=1.0 should attenuate 10000 Hz by > 12 dB."""
    sig = _sine_tone(10000)
    out, _ = lpf2(sig, 1000, 1.0, SR)
    assert _rms(out) < 0.25 * _rms(sig)


def test_lpf2_state_continuity():
    """Filtering two half-buffers (with state) must equal filtering the full buffer."""
    sig = _sine_tone(440)
    half = N // 2

    full_out, _ = lpf2(sig, 1000, 1.0, SR)

    half1_out, zi = lpf2(sig[:half], 1000, 1.0, SR)
    half2_out, _ = lpf2(sig[half:], 1000, 1.0, SR, zi=zi)

    stitched = np.concatenate([half1_out, half2_out])
    diff = np.abs(full_out.astype(np.float64) - stitched.astype(np.float64))
    assert diff.max() < 1e-5, f"lpf2 state-continuity error: {diff.max():.2e}"


# ---------------------------------------------------------------------------
# State continuity
# ---------------------------------------------------------------------------


def test_lpf_state_continuity():
    """Filtering two half-buffers (with state) must equal filtering the full buffer."""
    sig = _sine_tone(440)
    half = N // 2

    # Full buffer in one call.
    full_out, _ = lpf(sig, 1000, SR)

    # Two half-buffers with state forwarded.
    half1_out, zi = lpf(sig[:half], 1000, SR)
    half2_out, _ = lpf(sig[half:], 1000, SR, zi=zi)

    stitched = np.concatenate([half1_out, half2_out])
    diff = np.abs(full_out.astype(np.float64) - stitched.astype(np.float64))
    assert diff.max() < 1e-4, f"Max state-continuity error: {diff.max():.2e}"
