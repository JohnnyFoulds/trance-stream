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


def test_trancegate_is_binary():
    """Binary gate must produce only floor or 1.0 values — no intermediate levels."""
    samples_per_bar = 75600
    env = trancegate(samples_per_bar, SR, samples_per_bar, density=0.667, floor=0.3, seed=45)
    # Convert to float64 before unique-value check to avoid float32/float64 hash mismatch
    unique_vals = set(np.unique(env.astype(np.float64)))
    floor = 0.3
    assert all(abs(v - floor) < 1e-5 or abs(v - 1.0) < 1e-5 for v in unique_vals), (
        f"Binary gate produced non-binary values: {unique_vals}"
    )


def test_trancegate_has_16_slots_per_bar():
    """Binary gate must have ≤16 transitions per bar; all runs must be multiples of slot_len.
    Consecutive same-value slots merge into wider runs — that is correct behaviour.
    """
    samples_per_bar = 75600
    env = trancegate(samples_per_bar, SR, samples_per_bar, density=0.667, floor=0.3, seed=45)
    slot_len = samples_per_bar // 16
    transitions = np.where(np.diff(env) != 0)[0] + 1
    assert len(transitions) <= 16, (
        f"Expected ≤16 slot transitions per bar, got {len(transitions)}"
    )
    if len(transitions) > 0:
        gaps = np.diff(np.concatenate([[0], transitions, [samples_per_bar]]))
        # Each run must be an exact multiple of slot_len (merged identical slots are 2×, 3×, etc.)
        assert all(g % slot_len == 0 for g in gaps), (
            f"Some run lengths are not multiples of slot_len={slot_len}: {gaps}"
        )


def test_trancegate_dtype():
    samples_per_bar = 75600
    env = trancegate(samples_per_bar, SR, samples_per_bar)
    assert env.dtype == np.float32
