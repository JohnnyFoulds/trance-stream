# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Oscillators for procedural trance synthesis.

All functions return float32 arrays. No Python loops over individual samples —
all inner loops are numpy-vectorised or bounded by harmonic count (max 64),
not sample count.
"""

from __future__ import annotations

import numpy as np


def sawtooth(
    freq_hz: float,
    n_samples: int,
    sr: int,
    phase: float = 0.0,
) -> tuple[np.ndarray, float]:
    """Bandlimited sawtooth via phase accumulation.

    Returns (samples, final_phase) where final_phase is in [0, 1).
    Shape: (n_samples,). dtype: float32.

    Uses additive synthesis for band-limiting (sum of harmonics below Nyquist).
    This avoids the aliasing that naive ramp-based sawtooth produces.
    Harmonics: n=1..N where N = min(64, sr//2 // freq_hz - 1).

    Returns (samples, end_phase) where end_phase is in [0,1) so the caller
    can continue a sequence with phase continuity.
    """
    freq_hz = max(float(freq_hz), 1.0)
    t = np.arange(n_samples, dtype=np.float64)
    phase_vec = 2.0 * np.pi * (freq_hz / sr * t + phase)

    n_harmonics = min(64, int(sr / 2 / freq_hz) - 1)
    n_harmonics = max(1, n_harmonics)

    # Loop over harmonics (max 64), not samples — O(H) not O(N).
    samples = np.zeros(n_samples, dtype=np.float64)
    for n in range(1, n_harmonics + 1):
        samples += ((-1) ** (n + 1)) * (2.0 / (np.pi * n)) * np.sin(n * phase_vec)

    # Additive synthesis has ~9% Gibbs overshoot at discontinuities; normalise.
    peak = np.abs(samples).max()
    if peak > 0:
        samples /= peak

    end_phase = (freq_hz * n_samples / sr + phase) % 1.0
    return samples.astype(np.float32), end_phase


def supersaw(
    midi_note: int,
    n_samples: int,
    sr: int,
    saw_count: int = 5,
    detune_cents: float = 60.0,
    pan: float = 0.0,
    osc_phases: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Supersaw: N detuned sawtooth voices, stereo output.

    SA's confirmed params: saw_count=5, detune_cents=60.
    Detune distributes voices evenly across [-detune_cents/2, +detune_cents/2].
    Voice 0 = center, others spread symmetrically.

    Returns (buf_l, buf_r, osc_phases) where osc_phases shape = (saw_count,)
    for phase continuity across calls.

    Stereo placement: voices alternated L/R with equal power law.
    If pan != 0.0: additional overall pan applied.
    All voices summed and normalised by 1/saw_count.
    """
    base_freq = 440.0 * 2.0 ** ((midi_note - 69) / 12.0)

    # Distribute voices evenly across [-detune_cents/2, +detune_cents/2].
    # Voice at index saw_count//2 lands on 0 when saw_count is odd.
    cent_offsets = np.linspace(-detune_cents / 2.0, detune_cents / 2.0, saw_count)
    freq_ratios = 2.0 ** (cent_offsets / 1200.0)
    freqs = base_freq * freq_ratios

    if osc_phases is None:
        osc_phases = np.zeros(saw_count, dtype=np.float64)

    buf_l = np.zeros(n_samples, dtype=np.float64)
    buf_r = np.zeros(n_samples, dtype=np.float64)
    new_phases = np.empty(saw_count, dtype=np.float64)

    for i in range(saw_count):
        voice, new_phases[i] = sawtooth(freqs[i], n_samples, sr, osc_phases[i])

        # Equal-power stereo spread: alternate voices L/R.
        # Angle 0 = full left, pi/2 = full right, pi/4 = centre.
        # Voices interleave so adjacent voices sit on opposite sides.
        spread_angle = (np.pi / 4.0) * (1.0 + ((-1) ** i) * (i / max(saw_count - 1, 1)))
        l_gain = np.cos(spread_angle)
        r_gain = np.sin(spread_angle)

        buf_l += l_gain * voice
        buf_r += r_gain * voice

    buf_l /= saw_count
    buf_r /= saw_count

    # Additional overall pan using equal-power law.
    if pan != 0.0:
        pan_angle = np.pi / 4.0 * (1.0 + pan)  # pan in [-1, 1] -> angle in [0, pi/2]
        buf_l *= np.cos(pan_angle)
        buf_r *= np.sin(pan_angle)

    return buf_l.astype(np.float32), buf_r.astype(np.float32), new_phases


def sine(
    freq_hz: float,
    n_samples: int,
    sr: int,
    phase: float = 0.0,
) -> tuple[np.ndarray, float]:
    """Sine wave. Returns (samples, final_phase)."""
    t = np.arange(n_samples, dtype=np.float64)
    samples = np.sin(2.0 * np.pi * (freq_hz / sr * t + phase))
    end_phase = (freq_hz * n_samples / sr + phase) % 1.0
    return samples.astype(np.float32), end_phase


def brown_noise(n_samples: int, rng: np.random.Generator) -> np.ndarray:
    """Brown (red) noise via cumulative sum of white noise.

    Normalised to [-1, 1] range.
    Used as FM source for lead synthesis.
    """
    white = rng.standard_normal(n_samples)
    brown = np.cumsum(white)
    brown -= brown.mean()
    peak = np.abs(brown).max()
    return (brown / max(peak, 1e-9)).astype(np.float32)
