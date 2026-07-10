# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""High pluck instrument — sine with VCF brightness burst on attack.

Derived from "Hey Angel…" stem analysis (research/analysis/hey_angel_analysis.md §4b):
- Pitch: E5 (660 Hz)
- Timbre: "fundamental + weak 2nd harmonic only" — near-sine
- Brightness decay: spectral centroid 2500 → 1600 Hz in first 25ms (VCF close on attack)
- Sustain: long-held, near-sine throughout
"""

from __future__ import annotations

import numpy as np


class HighPluck:
    """Bright pluck: sine fundamental, fast brightness burst on attack.

    Signal chain: sine → 2ms attack VCA → held sustain

    The analysis says "near-sine" (fundamental + 2nd harmonic only).
    We use a pure sine since the LPF on a sine above cutoff is already near-zero.

    Parameters
    ----------
    gain : float, optional
        Output gain.  Default 0.45.
    sr : int
        Sample rate.  Default 44100.
    """

    def __init__(self, gain: float = 0.45, sr: int = 44100):
        self.gain = gain
        self.sr   = sr
        self._osc_phase = 0.0

    def render(self, midi_note: int, n_samples: int,
               gain: float = None) -> tuple:
        """Render one pluck note.

        Parameters
        ----------
        midi_note : int
            MIDI note (E5 = MIDI 76 = 660 Hz).
        n_samples : int
            Number of samples (sustained — does not self-decay).
        gain : float, optional
            Override instance gain.

        Returns
        -------
        (buf_l, buf_r) : tuple of float32 ndarray, shape (n_samples,)
        """
        from synth.oscillators import sine

        g = gain if gain is not None else self.gain
        midi_note = max(0, min(127, int(midi_note)))

        if n_samples <= 0:
            return (np.zeros(0, dtype=np.float32),
                    np.zeros(0, dtype=np.float32))

        freq_hz = 440.0 * 2.0 ** ((midi_note - 69) / 12.0)
        samples, self._osc_phase = sine(freq_hz, n_samples, self.sr,
                                        phase=self._osc_phase)

        # ── VCA: 2ms attack ramp, then sustained hold ─────────────────────────
        attack_s = max(1, int(0.002 * self.sr))
        vca = np.ones(n_samples, dtype=np.float32)
        vca[:attack_s] = np.linspace(0.0, 1.0, attack_s)
        samples = (samples * vca * g).astype(np.float32)

        out = samples.astype(np.float32)
        return out, out.copy()
