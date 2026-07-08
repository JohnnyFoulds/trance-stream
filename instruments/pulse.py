# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""SA's pulse texture layer — 16th-note pulse bursts with time-varying FM."""

from __future__ import annotations

import math

import numpy as np


def _pulse_texture(step: int, total_steps: int,
                   n_samples: int, sr: int = 44100) -> tuple:
    """Render one 16th-note pulse burst with time-varying FM.

    SA's idiom: pulse!16, dec(.1), fm(time).fmh(time)
    - Pulse wave (50% duty square), 100ms decay envelope.
    - Base frequency drifts slowly via sin(total_steps * 0.01).
    - Band-pass filtered (HPF 400 Hz, LPF 3000 Hz) to keep it textural.
    - FM harmonic multiplier also drifts slowly: fmh(time) modelled as
      sin(total_steps * 0.007) mapped to 1–4× the base frequency.
    - No Python loops over individual samples — all numpy-vectorised.

    Returns (buf_l, buf_r) as float32 ndarrays, shape (n_samples,).
    """
    from synth.filters import lpf, hpf

    if n_samples <= 0:
        return np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32)

    t = np.arange(n_samples, dtype=np.float64) / sr

    # Time-varying base frequency: 200–1000 Hz, drifts over the session.
    freq_base = 200.0 + 800.0 * ((math.sin(total_steps * 0.01) + 1.0) / 2.0)

    # FM depth increases with session time (fm(time) idiom): 0 → 0.5.
    fm_depth = 0.5 * (total_steps / max(total_steps, 1))

    # FM harmonic: fmh(time) → 1–4× base freq, drifts with sin.
    fm_harm = 1.0 + 3.0 * ((math.sin(total_steps * 0.007) + 1.0) / 2.0)

    # Modulator: sine at freq_base * fm_harm, depth scales the frequency.
    mod_freq = freq_base * fm_harm
    modulator = fm_depth * np.sin(2.0 * np.pi * mod_freq * t)

    # Carrier instantaneous frequency = freq_base * (1 + modulator).
    # Phase = integral of freq(t)/sr; use cumsum for sample-accurate phase.
    inst_freq = freq_base * (1.0 + modulator)
    # Clamp to avoid aliasing.
    inst_freq = np.clip(inst_freq, 20.0, sr * 0.45)
    phase = np.cumsum(inst_freq / sr) % 1.0

    # Pulse wave via sign of sin — 50% duty cycle.
    pulse = np.sign(np.sin(2.0 * np.pi * phase)).astype(np.float32) * 0.5

    # Amplitude envelope: fast attack (1 sample step), 100ms exponential decay.
    env = np.exp(-t / 0.1).astype(np.float32)
    buf = (pulse * env).astype(np.float32)

    # Band-pass: HPF at 400 Hz then LPF at 3000 Hz — one-pole each, no sample loop.
    buf, _ = hpf(buf, 400.0, sr)
    buf, _ = lpf(buf, 3000.0, sr)

    # Mild stereo spread: slightly different pan for even/odd steps.
    if step % 2 == 0:
        return (buf * 0.7).astype(np.float32), (buf * 0.5).astype(np.float32)
    else:
        return (buf * 0.5).astype(np.float32), (buf * 0.7).astype(np.float32)


class PulseTexture:
    """SA's pulse texture layer.

    SA's idiom: pulse!16, dec(.1), fm(time).fmh(time)
    - 16 pulses per bar (one per 16th note)
    - Very short decay (100ms)
    - FM depth increases with time (bar position)
    - Low gain: GAIN_PULSE = 0.12

    Each render call produces one 16th-note pulse.
    """

    def render(self, step: int, total_steps: int, n_samples: int,
               sr: int = 44100) -> tuple:
        """Render one 16th-note pulse at position step/total_steps through the song.

        Parameters
        ----------
        step : int
            Step within the current bar (0–15).
        total_steps : int
            Absolute step count since session start, used for FM time-arc.
        n_samples : int
            Samples to render (should equal one 16th-note step length).
        sr : int
            Sample rate (default 44100).

        Returns
        -------
        (buf_l, buf_r) : tuple of float32 ndarray, shape (n_samples,)
        """
        from song.theory import GAIN_PULSE

        buf_l, buf_r = _pulse_texture(step, total_steps, n_samples, sr=sr)
        g = GAIN_PULSE
        return (buf_l * g).astype(np.float32), (buf_r * g).astype(np.float32)
