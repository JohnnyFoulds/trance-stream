# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Smooth legato lead — filtered sawtooth, portamento, plain sustain.

Built specifically for the Hey Angel chromatic glide melody.
Signal chain: sawtooth → LPF (cutoff ~1kHz) → plain sustain VCA

The analysis says "near-sine" — that means a sawtooth heavily low-pass filtered
so only the fundamental and a little 2nd harmonic pass through.  A literal sine
has zero harmonic content and produces a thin single-frequency line on the
spectrogram.  A filtered saw gives the warmth and slight harmonic texture visible
in the reference spectrogram.
"""

from __future__ import annotations
import numpy as np


class SmoothLead:
    """Filtered-sawtooth lead with portamento and held sustain.

    Parameters
    ----------
    cutoff_hz : float
        LPF cutoff.  Default 900 Hz — passes fundamental clearly, attenuates
        harmonics above the 3rd so the timbre stays warm/mellow.
    gain : float
        Output gain.  Default 0.6.
    sr : int
        Sample rate.
    """

    def __init__(self, cutoff_hz: float = 900.0, gain: float = 0.6,
                 sr: int = 44100):
        self.cutoff_hz = cutoff_hz
        self.gain      = gain
        self.sr        = sr
        self._osc_phase = 0.0
        self._lpf_zi    = None

    def render(self, midi_note: int, n_samples: int,
               target_midi: int = None,
               gain: float = None) -> tuple:
        """Render n_samples of smooth portamento lead.

        Parameters
        ----------
        midi_note : int
            Start pitch (MIDI).
        n_samples : int
            Number of samples — voice sustains at full amplitude throughout.
        target_midi : int, optional
            If given, pitch glides linearly from midi_note to target_midi.
        gain : float, optional
            Override instance gain.
        """
        from synth.oscillators import sawtooth
        from synth.filters import lpf2

        g = gain if gain is not None else self.gain
        midi_note = max(0, min(127, int(midi_note)))

        if n_samples <= 0:
            return np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32)

        # ── Oscillator: sawtooth with portamento ──────────────────────────────
        if target_midi is not None:
            end_midi  = float(max(0, min(127, int(target_midi))))
            midi_vals = np.linspace(float(midi_note), end_midi, 64)
            seg_len   = max(1, n_samples // 64)
            samples   = np.empty(n_samples, dtype=np.float32)
            phase     = self._osc_phase
            for seg in range(64):
                s = seg * seg_len
                e = (s + seg_len) if seg < 63 else n_samples
                e = min(e, n_samples)
                if s >= n_samples:
                    break
                freq = 440.0 * 2.0 ** ((midi_vals[seg] - 69.0) / 12.0)
                buf, phase = sawtooth(freq, e - s, self.sr, phase)
                samples[s:e] = buf
            self._osc_phase = phase
        else:
            freq_hz = 440.0 * 2.0 ** ((midi_note - 69) / 12.0)
            samples, self._osc_phase = sawtooth(freq_hz, n_samples, self.sr,
                                                 phase=self._osc_phase)

        # ── LPF — state persists across calls for legato continuity ──────────
        samples, self._lpf_zi = lpf2(samples, self.cutoff_hz, q=0.7,
                                      sr=self.sr, zi=self._lpf_zi)

        # ── Plain sustain VCA — 2ms attack ramp, then hold ───────────────────
        attack = max(1, int(0.002 * self.sr))
        vca    = np.ones(n_samples, dtype=np.float32)
        vca[:attack] = np.linspace(0.0, 1.0, attack)
        samples = (samples * vca * g).astype(np.float32)

        return samples, samples.copy()
