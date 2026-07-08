# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""SA's acid bass instrument — sawtooth through acidenv LP sweep."""

from __future__ import annotations

import numpy as np


class AcidBass:
    """SA's acid bass instrument.

    Signal chain: sawtooth → acidenv → lpf

    Note is transposed down by the caller (typically played at -14 semitones
    relative to the pad root to sit in the sub-bass register).

    Gain: GAIN_BASS = 0.55
    """

    def __init__(self, gain: float = None, sr: int = 44100):
        from song.theory import GAIN_BASS

        self.gain = gain if gain is not None else GAIN_BASS
        self.sr   = sr

    def render(self, midi_note: int, n_samples: int,
               cutoff_slider: float = 0.45,
               gain: float = None) -> tuple:
        """Render one bass note for n_samples.

        Parameters
        ----------
        midi_note : int
            MIDI note to render (clamped to 0–127).
        n_samples : int
            Number of samples to render.
        cutoff_slider : float
            rlpf slider value; SA formula: (slider*12)**4 Hz.
            Default 0.45 ≈ 1336 Hz — appropriate for sub-bass.
        gain : float, optional
            Output gain override; if None uses the instance value.

        Returns
        -------
        (buf_l, buf_r) : tuple of float32 ndarray, shape (n_samples,)
            Stereo pair (identical — bass is mono, returned as stereo for
            mix compatibility).
        """
        from synth.oscillators import sawtooth
        from synth.filters import lpf, rlpf_to_hz
        from synth.envelopes import acidenv

        g      = gain if gain is not None else self.gain
        midi_note = max(0, min(127, int(midi_note)))
        cutoff = rlpf_to_hz(cutoff_slider)

        if n_samples <= 0:
            return (np.zeros(0, dtype=np.float32),
                    np.zeros(0, dtype=np.float32))

        freq_hz = 440.0 * 2.0 ** ((midi_note - 69) / 12.0)
        samples, _ = sawtooth(freq_hz, n_samples, self.sr)

        # acidenv modulates LP cutoff: 3ms attack, exponential decay.
        env = acidenv(n_samples, self.sr, amount=0.65)

        # 8 stepped filter segments — bounded loop over segments, not samples.
        base_hz = 80.0
        n_segs  = 8
        seg_len = max(1, n_samples // n_segs)
        zi = None
        for seg in range(n_segs):
            s = seg * seg_len
            if s >= n_samples:
                break
            e = (s + seg_len) if seg < (n_segs - 1) else n_samples
            e = min(e, n_samples)
            mid_val  = float(env[s + (e - s) // 2])
            seg_cut  = base_hz + (cutoff - base_hz) * mid_val
            seg_cut  = float(np.clip(seg_cut, 30.0, self.sr * 0.45))
            samples[s:e], zi = lpf(samples[s:e], seg_cut, self.sr, zi)

        out = (samples * g).astype(np.float32)
        return out, out.copy()
