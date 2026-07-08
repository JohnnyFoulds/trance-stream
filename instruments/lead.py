# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""SA's acid lead instrument — supersaw + brown-noise FM through acidenv → trancegate → delay."""

from __future__ import annotations

import numpy as np


class AcidLead:
    """SA's lead instrument.

    Signal chain (SA's exact confirmed order):
    supersaw(saw_count=3, detune=0.3) + brown_noise_FM → lpenv → acidenv → trancegate → FeedbackDelay

    Key facts (from docs/music_theory/02_sa_vocabulary_codified.md):
    - Uses acidenv (fast 3ms attack, 120ms decay) — NOT lpenv alone
    - FeedbackDelay wet=0.7, feedback=0.8, delay_s=0.375 (3/8 note at 140BPM)
    - Brown noise added to FM: fm_depth=0 until bar 96, then ramps to 0.55
    - Gain: GAIN_LEAD = 0.70
    """

    def __init__(self, root_midi: int = 48, cutoff_slider: float = 0.593,
                 gain: float = None, sr: int = 44100):
        from song.theory import GAIN_LEAD
        from synth.effects import FeedbackDelay

        self.root_midi     = root_midi
        self.cutoff_slider = cutoff_slider
        self.gain          = gain if gain is not None else GAIN_LEAD
        self.sr            = sr
        self._delay        = FeedbackDelay(delay_s=0.375, feedback=0.8, wet=0.7, sr=sr)
        self._rng          = np.random.default_rng(42)
        self._osc_phases   = None  # shape (saw_count,); reset on each note trigger

    def render(self, midi_notes: list, n_samples: int,
               bar_offset_samples: int = 0,
               cutoff_slider: float = None,
               fm_depth: float = 0.0,
               gain: float = None) -> tuple:
        """Render n_samples of lead audio.

        Parameters
        ----------
        midi_notes : list of int
            Notes to play (one supersaw per note, summed and normalised).
        n_samples : int
            Number of samples to render.
        bar_offset_samples : int
            Samples elapsed since the start of the current bar, for trancegate
            phase continuity when called bar-by-bar.
        cutoff_slider : float, optional
            rlpf slider override; if None uses the instance value.
        fm_depth : float
            Brown-noise FM amount. 0.0 at session start, ramps to 0.55 after bar 96.
        gain : float, optional
            Output gain override; if None uses the instance value.

        Returns
        -------
        (buf_l, buf_r) : tuple of float32 ndarray, shape (n_samples,)
        """
        from synth.oscillators import supersaw, brown_noise
        from synth.filters import lpf, rlpf_to_hz
        from synth.envelopes import acidenv, trancegate
        from song.theory import (TRANCEGATE_SPEED, TRANCEGATE_AMOUNT,
                                  samples_per_bar)

        slider = cutoff_slider if cutoff_slider is not None else self.cutoff_slider
        g      = gain if gain is not None else self.gain
        spb    = samples_per_bar()
        cutoff = rlpf_to_hz(slider)

        if not midi_notes or n_samples <= 0:
            return (np.zeros(n_samples, dtype=np.float32),
                    np.zeros(n_samples, dtype=np.float32))

        buf_l = np.zeros(n_samples, dtype=np.float32)
        buf_r = np.zeros(n_samples, dtype=np.float32)
        n_notes = len(midi_notes)

        for note in midi_notes:
            note = max(0, min(127, int(note)))
            l, r, _ = supersaw(note, n_samples, self.sr,
                                saw_count=3, detune_cents=30.0)
            # Brown-noise FM: additive noise scaled by fm_depth.
            # fm_depth=0 early session; ramps to 0.55 after bar 96.
            if fm_depth > 0.0:
                noise = brown_noise(n_samples, self._rng) * (fm_depth * 0.3)
                l = l + noise
                r = r + noise
            buf_l += l / n_notes
            buf_r += r / n_notes

        # LP filter: acidenv sweeps the cutoff from a low base up to full cutoff.
        # 8 stepped segments — bounded loop over segments, not samples.
        env     = acidenv(n_samples, self.sr, amount=0.55)
        base_hz = min(100.0, cutoff * 0.05)
        n_segs  = 8
        seg_len = max(1, n_samples // n_segs)
        zi_l = zi_r = None
        for seg in range(n_segs):
            s = seg * seg_len
            if s >= n_samples:
                break
            e = (s + seg_len) if seg < (n_segs - 1) else n_samples
            e = min(e, n_samples)
            mid_val  = float(env[s + (e - s) // 2])
            seg_cut  = base_hz + (cutoff - base_hz) * mid_val
            seg_cut  = float(np.clip(seg_cut, 50.0, self.sr * 0.45))
            buf_l[s:e], zi_l = lpf(buf_l[s:e], seg_cut, self.sr, zi_l)
            buf_r[s:e], zi_r = lpf(buf_r[s:e], seg_cut, self.sr, zi_r)

        # Trancegate: smooth cosine amplitude gate at 1.5× bar rate.
        gate  = trancegate(n_samples, self.sr, spb,
                           bar_offset_samples=bar_offset_samples,
                           speed=TRANCEGATE_SPEED, amount=TRANCEGATE_AMOUNT)
        buf_l *= gate
        buf_r *= gate

        # Ping-pong feedback delay: wet=0.7, feedback=0.8, delay_s=0.375.
        buf_l, buf_r = self._delay.process(buf_l, buf_r)

        buf_l *= g
        buf_r *= g
        return buf_l.astype(np.float32), buf_r.astype(np.float32)
