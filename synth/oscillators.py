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


def _polyblep(phase: np.ndarray, dt: float) -> np.ndarray:
    """PolyBLEP correction term — smooths the discontinuity in a naive sawtooth.

    Exact port of Strudel's polyBlep() in worklets.mjs.
    phase: array in [0, 1). dt = freq / sr (phase increment per sample).
    """
    dt = min(dt, 1.0 - dt)
    if dt < 1e-9:
        return np.zeros_like(phase)
    inv_dt = 1.0 / dt
    out = np.zeros_like(phase)
    # Near start of cycle (phase < dt): rising correction
    mask_lo = phase < dt
    t_lo = phase[mask_lo] * inv_dt
    out[mask_lo] = t_lo + t_lo - t_lo * t_lo - 1.0
    # Near end of cycle (phase > 1 - dt): falling correction
    mask_hi = phase > (1.0 - dt)
    t_hi = (phase[mask_hi] - 1.0) * inv_dt
    out[mask_hi] = t_hi + t_hi + t_hi * t_hi + 1.0
    return out


def sawtooth(
    freq_hz: float,
    n_samples: int,
    sr: int,
    phase: float = 0.0,
) -> tuple[np.ndarray, float]:
    """PolyBLEP sawtooth — exact match to Strudel's sawblep() in worklets.mjs.

    sawblep(phase, dt) = 2*phase - 1 - polyBlep(phase, dt)
    Returns (samples, final_phase) where final_phase is in [0, 1).
    """
    freq_hz = max(float(freq_hz), 1.0)
    dt = freq_hz / sr
    phases = (phase + dt * np.arange(n_samples, dtype=np.float64)) % 1.0
    samples = (2.0 * phases - 1.0) - _polyblep(phases, dt)
    end_phase = (phase + dt * n_samples) % 1.0
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
    """Supersaw: N detuned PolyBLEP sawtooth voices, stereo output.

    Exact port of Strudel's SuperSawOscillatorProcessor from worklets.mjs:
    - Voices distributed evenly across [-detune_cents/2, +detune_cents/2] in semitones
    - Stereo: voices alternate L/R by swapping gainL/gainR each voice (equal-power)
    - Phase init: random per voice (matching Strudel's Math.random() initialisation)
    - panspread=0.6 → gainL/gainR = sqrt(0.2)/sqrt(0.8) for outermost voices

    SA's confirmed params: saw_count=5, detune_cents=60 (freqspread=0.6 semitones * 5 voices).
    Note: Strudel's detune param is in semitones (freqspread), not cents.
    SA uses .detune(.6) = 0.6 semitones spread (= 60 cents total across 5 voices).
    """
    base_freq = 440.0 * 2.0 ** ((midi_note - 69) / 12.0)

    # Strudel's getDetuner: evenly spread voices across [-freqspread/2, +freqspread/2] semitones
    # SA's .detune(.6) = freqspread=0.6 semitones
    freqspread_semitones = detune_cents / 100.0  # convert cents to semitones
    if saw_count > 1:
        scale = freqspread_semitones / (saw_count - 1)
        center = freqspread_semitones * 0.5
        detune_semitones = [i * scale - center for i in range(saw_count)]
    else:
        detune_semitones = [0.0]

    freqs = [base_freq * (2.0 ** (d / 12.0)) for d in detune_semitones]

    # Random phase init if not provided (matches Strudel's Math.random())
    rng = np.random.default_rng(abs(midi_note) * 1000 + saw_count)
    if osc_phases is None:
        osc_phases = rng.random(saw_count)

    buf_l = np.zeros(n_samples, dtype=np.float64)
    buf_r = np.zeros(n_samples, dtype=np.float64)
    new_phases = np.empty(saw_count, dtype=np.float64)

    # Strudel panspread: maps to gainL=sqrt(1-ps), gainR=sqrt(ps) where ps=panspread*0.5+0.5
    # SA uses default panspread=0.4 → ps=0.7 → gainL=sqrt(0.3), gainR=sqrt(0.7)
    panspread = 0.4  # SA default
    ps = panspread * 0.5 + 0.5
    gain_l = np.sqrt(1.0 - ps)
    gain_r = np.sqrt(ps)

    for i in range(saw_count):
        voice, new_phases[i] = sawtooth(freqs[i], n_samples, sr, osc_phases[i])
        buf_l += gain_l * voice
        buf_r += gain_r * voice
        # Strudel alternates L/R each voice
        gain_l, gain_r = gain_r, gain_l

    buf_l /= saw_count
    buf_r /= saw_count

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
