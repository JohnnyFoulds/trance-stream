# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""SA's acid lead instrument — supersaw + sine-FM through acidenv → trancegate → delay."""

from __future__ import annotations

import numpy as np


class AcidLead:
    """SA's lead instrument.

    Signal chain (SA's exact confirmed order):
    supersaw(saw_count=3, detune=0.3) + sine-FM → lpenv → acidenv → trancegate → FeedbackDelay

    Key facts (from docs/music_theory/02_sa_vocabulary_codified.md):
    - Uses acidenv (fast 3ms attack, 120ms decay) — NOT lpenv alone
    - FeedbackDelay wet=0.7, feedback=0.8, delay_s=0.375 (3/8 note at 140BPM)
    - Sine FM modulates carrier phase by sin(2π·mod_freq·t), adding sidebands
      at carrier ± n·mod_freq; fm_depth=0 until bar 96, then ramps to 0.55
    - Gain: GAIN_LEAD = 0.70
    """

    # Character presets: (saw_count, detune_cents, acidenv_decay_s, delay_wet, cutoff_slider)
    _CHARACTERS = {
        'acid':   (3, 30.0, 0.08, 0.7,  0.593),  # SA's default: tight acid
        'smooth': (3, 50.0, 0.15, 0.5,  0.650),  # wider detuning, slower env, less delay
        'stab':   (5, 20.0, 0.04, 0.25, 0.500),  # punchy stab: very short env, mostly dry
    }

    def __init__(self, root_midi: int = 48, cutoff_slider: float = None,
                 gain: float = None, sr: int = 44100, character: str = 'acid'):
        from song.theory import GAIN_LEAD
        from synth.effects import FeedbackDelay

        if character not in self._CHARACTERS:
            character = 'acid'
        (saw_count, detune_cents, _acidenv_decay, delay_wet,
         default_slider) = self._CHARACTERS[character]

        self.root_midi     = root_midi
        self.cutoff_slider = cutoff_slider if cutoff_slider is not None else default_slider
        self.gain          = gain if gain is not None else GAIN_LEAD
        self.sr            = sr
        self.character     = character
        self._saw_count    = saw_count
        self._detune_cents = detune_cents
        self._acidenv_decay = _acidenv_decay
        self._delay        = FeedbackDelay(delay_s=0.375, feedback=0.8, wet=delay_wet, sr=sr)
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
            Sine-FM modulation index. 0.0 at session start, ramps to 0.55 after
            bar 96. Modulator at ~0.5× carrier frequency; creates sidebands in
            the 2k–8k range when carrier is 200–400 Hz.
        gain : float, optional
            Output gain override; if None uses the instance value.

        Returns
        -------
        (buf_l, buf_r) : tuple of float32 ndarray, shape (n_samples,)
        """
        from synth.oscillators import supersaw
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

        t = np.arange(n_samples, dtype=np.float64) / self.sr

        for note in midi_notes:
            note = max(0, min(127, int(note)))
            l, r, _ = supersaw(note, n_samples, self.sr,
                                saw_count=self._saw_count,
                                detune_cents=self._detune_cents)
            if fm_depth > 0.0:
                # SA's fm .5: modulator at 0.5× carrier (ratio 1:2), index ≈ 0.5.
                # Ratio 1:2 places sidebands at 0.5×, 1.5×, 2.5× carrier —
                # sub-harmonics that warm the tone without creating odd-partial
                # reed/harmonica character (which comes from ratio 4:1 + high index).
                carrier_freq = 440.0 * 2.0 ** ((note - 69) / 12.0)
                mod_freq  = carrier_freq * 0.5
                mod_index = fm_depth * 1.0      # index 0 → 0.55 at max fm_depth
                phase_mod = mod_index * np.sin(2.0 * np.pi * mod_freq * t)
                fm_voice  = (np.sin(2.0 * np.pi * carrier_freq * t + phase_mod)
                              .astype(np.float32))
                # Scale FM voice to 20% of the supersaw RMS so it enriches
                # without dominating regardless of the saw's output level.
                saw_rms = float(np.sqrt(np.mean(l ** 2))) or 1e-6
                fm_rms  = float(np.sqrt(np.mean(fm_voice ** 2))) or 1e-6
                fm_weight = (saw_rms * 0.20) / fm_rms
                l = (l + fm_voice * fm_weight).astype(np.float32)
                r = (r + fm_voice * fm_weight).astype(np.float32)
            buf_l += l / n_notes
            buf_r += r / n_notes

        # LP filter: acidenv sweeps the cutoff from base_hz up to full cutoff.
        # SA's .lpenv 2 is modelled as a rising acidenv on the filter frequency.
        # base_hz is 60% of the target cutoff (not 5% as before) so the lead has
        # perceptible brightness even before the acid peak opens it fully.
        # This ensures the lead registers in the 600-2000 Hz range from the start.
        env     = acidenv(n_samples, self.sr, amount=0.55,
                          decay_s=self._acidenv_decay)
        base_hz = cutoff * 0.60   # was 0.05 — too dark; SA's lead starts bright
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
