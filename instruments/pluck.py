# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""High pluck instrument — filtered sine with VCF brightness burst.

Derived from "Hey Angel…" stem analysis (research/analysis/hey_angel_analysis.md §4b):
- Pitch: E5 (660 Hz), near-instantaneous attack
- Brightness decay: spectral centroid 2500 → 1600 Hz in first 25ms (VCF close)
- Sustain: long-held, near-sine timbre (fundamental + weak 2nd harmonic only)
- Character: hard-filtered saw with a one-pole LPF that opens on note-on then closes fast
"""

from __future__ import annotations

import numpy as np


class HighPluck:
    """Bright pluck with a fast filter-burst on attack.

    Signal chain: sawtooth → one-pole LPF burst (2500→1600 Hz in 25ms) → sustain LPF → VCA

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
            MIDI note to render (clamped 0–127).  E5 = MIDI 76 = 660 Hz.
        n_samples : int
            Number of samples (sustain length — pluck does not self-decay).
        gain : float, optional
            Override instance gain.

        Returns
        -------
        (buf_l, buf_r) : tuple of float32 ndarray, shape (n_samples,)
        """
        from synth.oscillators import sawtooth
        from synth.filters import lpf2

        g = gain if gain is not None else self.gain
        midi_note = max(0, min(127, int(midi_note)))

        if n_samples <= 0:
            return (np.zeros(0, dtype=np.float32),
                    np.zeros(0, dtype=np.float32))

        freq_hz = 440.0 * 2.0 ** ((midi_note - 69) / 12.0)
        samples, self._osc_phase = sawtooth(freq_hz, n_samples, self.sr,
                                            phase=self._osc_phase)

        # ── VCF burst: 2500 → 1600 Hz in 25ms, then hold at 1600 Hz ─────────
        # Derived from "Hey Angel…" §4b centroid measurement.
        burst_samples = int(0.025 * self.sr)   # 25ms
        cutoff_high = 2500.0
        cutoff_low  = 1600.0

        n_filter_segs = 64
        seg_len = max(1, n_samples // n_filter_segs)
        zi = None
        for seg in range(n_filter_segs):
            s = seg * seg_len
            if s >= n_samples:
                break
            e = (s + seg_len) if seg < (n_filter_segs - 1) else n_samples
            e = min(e, n_samples)
            mid = s + (e - s) // 2
            # Exponential close: starts open at cutoff_high, decays to cutoff_low
            if mid < burst_samples:
                t_frac = mid / max(burst_samples, 1)
                # Exponential close over the burst window
                cut = cutoff_high * (cutoff_low / cutoff_high) ** t_frac
            else:
                cut = cutoff_low
            cut = float(np.clip(cut, 200.0, self.sr * 0.45))
            samples[s:e], zi = lpf2(samples[s:e], cut, q=1.2, sr=self.sr, zi=zi)

        # ── VCA: fast attack (< 1ms), sustained hold (no self-decay) ─────────
        attack_samples = max(1, int(0.001 * self.sr))
        t_arr = np.arange(n_samples, dtype=np.float32)
        vca = np.where(t_arr < attack_samples,
                       t_arr / attack_samples,
                       np.ones(n_samples, dtype=np.float32))
        samples = (samples * vca).astype(np.float32)

        out = (samples * g).astype(np.float32)
        return out, out.copy()
