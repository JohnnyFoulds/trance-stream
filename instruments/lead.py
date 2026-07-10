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
        self._osc_phases       = None  # shape (saw_count,); persisted across render calls
        self._fm_phase_carrier = 0.0

    def render(self, midi_notes: list, n_samples: int,
               bar_offset_samples: int = 0,
               cutoff_slider: float = None,
               fm_depth: float = 0.0,
               gain: float = None,
               samples_per_bar: int = None,
               portamento_s: float = 0.0,
               target_midi: int = None) -> tuple:
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
            bar 96.
        gain : float, optional
            Output gain override; if None uses the instance value.
        portamento_s : float
            Glide time in seconds.  When > 0 and target_midi is given and
            midi_notes has exactly one note, the pitch slides linearly (in
            semitone space) from midi_notes[0] to target_midi over n_samples.
        target_midi : int, optional
            Target MIDI note for portamento glide.

        Returns
        -------
        (buf_l, buf_r) : tuple of float32 ndarray, shape (n_samples,)
        """
        from synth.oscillators import supersaw
        from synth.filters import lpf2, rlpf_to_hz
        from synth.envelopes import acidenv, trancegate
        from song.theory import (TRANCEGATE_SPEED, TRANCEGATE_AMOUNT,
                                  samples_per_bar as _samples_per_bar)

        slider = cutoff_slider if cutoff_slider is not None else self.cutoff_slider
        g      = gain if gain is not None else self.gain
        spb    = samples_per_bar if samples_per_bar is not None else _samples_per_bar()
        cutoff = rlpf_to_hz(slider)

        if not midi_notes or n_samples <= 0:
            return (np.zeros(n_samples, dtype=np.float32),
                    np.zeros(n_samples, dtype=np.float32))

        buf_l = np.zeros(n_samples, dtype=np.float32)
        buf_r = np.zeros(n_samples, dtype=np.float32)
        n_notes = len(midi_notes)

        use_portamento = (portamento_s > 0.0 and target_midi is not None
                          and len(midi_notes) == 1)

        for note in midi_notes:
            note = max(0, min(127, int(note)))
            if use_portamento:
                # Render 64 pitch segments gliding note → target_midi in semitone space.
                end_midi = float(max(0, min(127, int(target_midi))))
                midi_vals = np.linspace(float(note), end_midi, 64)
                n_segs_port = 64
                seg_len_port = max(1, n_samples // n_segs_port)
                l = np.zeros(n_samples, dtype=np.float32)
                r = np.zeros(n_samples, dtype=np.float32)
                phases = self._osc_phases
                for seg in range(n_segs_port):
                    s = seg * seg_len_port
                    e = (s + seg_len_port) if seg < n_segs_port - 1 else n_samples
                    e = min(e, n_samples)
                    if s >= n_samples:
                        break
                    sl, sr_, phases = supersaw(
                        int(round(midi_vals[seg])), e - s, self.sr,
                        saw_count=self._saw_count,
                        detune_cents=self._detune_cents,
                        osc_phases=phases)
                    l[s:e] = sl
                    r[s:e] = sr_
                self._osc_phases = phases
            else:
                l, r, self._osc_phases = supersaw(note, n_samples, self.sr,
                                                   saw_count=self._saw_count,
                                                   detune_cents=self._detune_cents,
                                                   osc_phases=self._osc_phases)
            if fm_depth > 0.0:
                # SA's .fm(.5).fmwave("brown"): brown-noise phase modulation.
                # Brown noise as modulator creates warm, inharmonic sidebands with
                # no discrete frequency peaks — avoids the "rat/mosquito" tones that
                # a sine modulator at a fixed ratio produces.
                from synth.oscillators import brown_noise
                carrier_freq = 440.0 * 2.0 ** ((note - 69) / 12.0)
                mod_index = fm_depth * 2.0
                brown = brown_noise(n_samples, self._rng)
                n_arr = np.arange(n_samples, dtype=np.float64)
                carr_phase_vec = (2.0 * np.pi * carrier_freq / self.sr * n_arr
                                  + 2.0 * np.pi * self._fm_phase_carrier)
                fm_voice = np.sin(carr_phase_vec + mod_index * brown).astype(np.float32)
                self._fm_phase_carrier = (carrier_freq * n_samples / self.sr
                                          + self._fm_phase_carrier) % 1.0
                saw_rms = float(np.sqrt(np.mean(l ** 2))) or 1e-6
                fm_rms  = float(np.sqrt(np.mean(fm_voice ** 2))) or 1e-6
                fm_weight = (saw_rms * 0.20) / fm_rms
                l = (l + fm_voice * fm_weight).astype(np.float32)
                r = (r + fm_voice * fm_weight).astype(np.float32)
            buf_l += l / n_notes
            buf_r += r / n_notes

        # LP filter: acidenv sweeps the cutoff from base_hz up to full cutoff.
        env     = acidenv(n_samples, self.sr, amount=0.55,
                          decay_s=self._acidenv_decay)
        base_hz = cutoff * 0.60
        n_segs  = 64
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
            buf_l[s:e], zi_l = lpf2(buf_l[s:e], seg_cut, q=2.0, sr=self.sr, zi=zi_l)
            buf_r[s:e], zi_r = lpf2(buf_r[s:e], seg_cut, q=2.0, sr=self.sr, zi=zi_r)

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
