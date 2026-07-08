# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Numerical tests for synth/oscillators.py — no audio hardware, no file I/O."""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

import numpy as np
import pytest

from synth.oscillators import brown_noise, sawtooth, sine, supersaw

SR = 44100
ONE_SECOND = 44100


# ---------------------------------------------------------------------------
# sawtooth
# ---------------------------------------------------------------------------


def test_sawtooth_output_range():
    buf, _ = sawtooth(440, ONE_SECOND, SR)
    assert buf.min() >= -1.0
    assert buf.max() <= 1.0


def test_sawtooth_zero_crossing_rate():
    """A 440 Hz sawtooth should have ~880 zero-crossings per second."""
    buf, _ = sawtooth(440, ONE_SECOND, SR)
    # Count sign changes: positions where consecutive samples straddle zero.
    crossings = np.sum(np.diff(np.sign(buf)) != 0)
    # 2 crossings per cycle × 440 Hz = 880; allow ±10% tolerance.
    assert abs(crossings - 880) <= 88, f"Expected ~880 crossings, got {crossings}"


def test_sawtooth_returns_phase_in_unit_interval():
    _, end_phase = sawtooth(440, ONE_SECOND, SR)
    assert 0.0 <= end_phase < 1.0


def test_sawtooth_phase_continuity():
    """Calling sawtooth twice with phase continuity must not produce a seam jump."""
    buf1, end_phase = sawtooth(440, ONE_SECOND // 2, SR)
    buf2, _ = sawtooth(440, ONE_SECOND // 2, SR, phase=end_phase)
    seam_diff = abs(float(buf1[-1]) - float(buf2[0]))
    # Consecutive samples near the seam should be smooth (no discontinuity).
    assert seam_diff < 0.1, f"Seam discontinuity {seam_diff:.4f} exceeds threshold"


def test_sawtooth_dtype():
    buf, _ = sawtooth(440, ONE_SECOND, SR)
    assert buf.dtype == np.float32


# ---------------------------------------------------------------------------
# supersaw
# ---------------------------------------------------------------------------


def test_supersaw_output_shapes():
    buf_l, buf_r, phases = supersaw(60, ONE_SECOND, SR)
    assert buf_l.shape == (ONE_SECOND,)
    assert buf_r.shape == (ONE_SECOND,)
    assert phases.shape == (5,)


def test_supersaw_output_range():
    buf_l, buf_r, _ = supersaw(60, ONE_SECOND, SR)
    assert buf_l.min() >= -1.0
    assert buf_l.max() <= 1.0
    assert buf_r.min() >= -1.0
    assert buf_r.max() <= 1.0


def test_supersaw_phases_shape_with_explicit_count():
    buf_l, buf_r, phases = supersaw(60, ONE_SECOND, SR, saw_count=5)
    assert phases.shape == (5,)


def test_supersaw_dtype():
    buf_l, buf_r, _ = supersaw(60, ONE_SECOND, SR)
    assert buf_l.dtype == np.float32
    assert buf_r.dtype == np.float32


# ---------------------------------------------------------------------------
# sine
# ---------------------------------------------------------------------------


def test_sine_output_range():
    buf, _ = sine(440, ONE_SECOND, SR)
    assert buf.min() >= -1.0
    assert buf.max() <= 1.0


def test_sine_zero_crossing_count():
    """A 440 Hz sine should cross zero ~880 times per second."""
    buf, _ = sine(440, ONE_SECOND, SR)
    crossings = np.sum(np.diff(np.sign(buf)) != 0)
    assert abs(crossings - 880) <= 20, f"Expected ~880 crossings, got {crossings}"


def test_sine_dtype():
    buf, _ = sine(440, ONE_SECOND, SR)
    assert buf.dtype == np.float32


# ---------------------------------------------------------------------------
# brown_noise
# ---------------------------------------------------------------------------


def test_brown_noise_output_range():
    rng = np.random.default_rng(42)
    buf = brown_noise(ONE_SECOND, rng)
    assert buf.min() >= -1.0
    assert buf.max() <= 1.0


def test_brown_noise_dtype():
    rng = np.random.default_rng(42)
    buf = brown_noise(ONE_SECOND, rng)
    assert buf.dtype == np.float32
