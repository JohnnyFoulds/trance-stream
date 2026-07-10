# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Numerical tests for synth/envelopes.py — no audio hardware, no file I/O."""

import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).parents[2]))

import numpy as np
import pytest

from synth.envelopes import acidenv, lpenv, trancegate

SR = 44100
ONE_SECOND = 44100


# ---------------------------------------------------------------------------
# acidenv
# ---------------------------------------------------------------------------


def test_acidenv_output_range():
    env = acidenv(ONE_SECOND, SR, 0.55)
    assert env.min() >= 0.0
    assert env.max() <= 1.0


def test_acidenv_peak_near_3ms():
    """acidenv attack is 3ms, so the peak sample index should be ~132 (±50)."""
    env = acidenv(ONE_SECOND, SR, 0.55)
    peak_idx = int(np.argmax(env))
    expected = int(SR * 0.003)  # 3ms in samples ≈ 132
    assert abs(peak_idx - expected) <= 50, (
        f"Peak at sample {peak_idx}, expected ~{expected} (±50)"
    )


def test_acidenv_decayed_by_200ms():
    """acidenv should have decayed below 0.5 by 200ms (sample 8820)."""
    env = acidenv(ONE_SECOND, SR, 0.55)
    sample_200ms = int(SR * 0.2)  # 8820
    assert env[sample_200ms] < 0.5, (
        f"env[{sample_200ms}] = {env[sample_200ms]:.4f}, expected < 0.5"
    )


def test_acidenv_dtype():
    env = acidenv(ONE_SECOND, SR, 0.55)
    assert env.dtype == np.float32


# ---------------------------------------------------------------------------
# lpenv
# ---------------------------------------------------------------------------


def test_lpenv_output_range():
    env = lpenv(ONE_SECOND, SR, 2.0)
    assert env.min() >= 0.0
    assert env.max() <= 1.0


def test_lpenv_peaks_early():
    """lpenv attack is 5ms; the peak should fall within the first 50ms."""
    env = lpenv(ONE_SECOND, SR, 2.0)
    peak_idx = int(np.argmax(env))
    max_early_sample = int(SR * 0.05)  # 50ms
    assert peak_idx < max_early_sample, (
        f"Peak at sample {peak_idx}, expected within first {max_early_sample} samples"
    )


def test_lpenv_dtype():
    env = lpenv(ONE_SECOND, SR, 2.0)
    assert env.dtype == np.float32


# ---------------------------------------------------------------------------
# trancegate
# ---------------------------------------------------------------------------


def test_trancegate_output_range():
    """One full bar at 140 BPM = 75600 samples; output should stay in [0, 1]."""
    samples_per_bar = 75600  # 44100 * 60/140 * 4 ≈ 75600
    env = trancegate(samples_per_bar, SR, samples_per_bar)
    assert env.min() >= 0.0
    assert env.max() <= 1.0


def test_trancegate_smooth():
    """No adjacent sample difference should exceed 0.05."""
    samples_per_bar = 75600
    env = trancegate(samples_per_bar, SR, samples_per_bar)
    max_jump = float(np.abs(np.diff(env.astype(np.float64))).max())
    assert max_jump <= 0.0006, f"Max adjacent jump {max_jump:.6f} exceeds 0.0006 (raised-cosine max is ~0.000062)"


def test_trancegate_cycle_count_with_speed_1_5():
    """speed=1.5 should produce 1.5 cycles per bar → ~3 zero-crossings of (gate - 0.5)."""
    samples_per_bar = 75600
    env = trancegate(samples_per_bar, SR, samples_per_bar, speed=1.5)
    centered = env.astype(np.float64) - 0.5
    # Count sign reversals. The gate period divides evenly into the bar so the
    # raised cosine can land exactly on centered=0.0 at an integer sample; the
    # product approach (a*b < 0) returns 0 in that case and misses the crossing.
    # Instead, count pairs where the signal goes neg→non-neg or pos→non-pos:
    a, b = centered[:-1], centered[1:]
    crossings = int(np.sum(((a < 0) & (b >= 0)) | ((a > 0) & (b <= 0))))
    # 1.5 cycles × 2 crossings per cycle = 3; allow ±1 for boundary effects.
    assert abs(crossings - 3) <= 1, (
        f"Expected ~3 zero-crossings, got {crossings}"
    )


def test_trancegate_dtype():
    samples_per_bar = 75600
    env = trancegate(samples_per_bar, SR, samples_per_bar)
    assert env.dtype == np.float32
