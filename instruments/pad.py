# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""SA's pad instrument — supersaw through LP envelope, trancegate, FDN reverb."""

from __future__ import annotations


class SupersawPad:
    """SA's pad instrument.

    Signal chain (SA's exact confirmed order):
    supersaw(saw_count=5, detune=0.6) → lpenv(2) → trancegate(1.5) → SimpleFDN → Sidechain

    Key distinction: uses lpenv (slow pad swell), NOT acidenv.
    acidenv is for bass/lead only. See docs/music_theory/02_sa_vocabulary_codified.md §2.

    Parameters
    ----------
    root_midi : int
        MIDI note of the root (default 48 = C3)
    cutoff_slider : float
        rlpf slider value (0.0–1.0), SA formula: (slider*12)**4 Hz
    gain : float
        Output gain (default: theory.GAIN_PAD = 0.5)
    sr : int
        Sample rate (default 44100)
    """

    def __init__(self, root_midi: int = 48, cutoff_slider: float = 0.55,
                 gain: float = None, sr: int = 44100):
        from song.theory import GAIN_PAD
        from synth.effects import SimpleFDN

        self.root_midi     = root_midi
        self.cutoff_slider = cutoff_slider
        self.gain          = gain if gain is not None else GAIN_PAD
        self.sr            = sr
        self._fdn          = SimpleFDN(room_size=0.7, sr=sr)
        self._osc_phases   = None  # shape (n_voices,), initialised on first render

    def render(self, midi_notes: list, n_samples: int,
               bar_offset_samples: int = 0,
               cutoff_slider: float = None,
               gain: float = None) -> tuple:
        """Render n_samples of pad audio for the given chord (list of MIDI notes).

        midi_notes : list of int — MIDI pitches to play (one supersaw per note)
        Returns (buf_l, buf_r) as float32 numpy arrays.

        For each note in midi_notes: render one supersaw, apply lpenv, sum.
        Then apply trancegate to the sum. Then FDN. Then overall gain.

        The voicing offsets (-14, -21 semitones from theory.PAD_VOICING_OFFSETS)
        are applied: each chord note also generates doublings at -14 and -21 semitones.
        """
        import numpy as np
        from synth.oscillators import supersaw
        from synth.filters import lpf, rlpf_to_hz
        from synth.envelopes import lpenv, trancegate
        from song.theory import (PAD_VOICING_OFFSETS, TRANCEGATE_SPEED,
                                  TRANCEGATE_AMOUNT, samples_per_bar)

        slider = cutoff_slider if cutoff_slider is not None else self.cutoff_slider
        g      = gain if gain is not None else self.gain
        spb    = samples_per_bar()
        cutoff = rlpf_to_hz(slider)

        buf_l = np.zeros(n_samples, dtype=np.float32)
        buf_r = np.zeros(n_samples, dtype=np.float32)

        # Expand notes with voicing offsets
        all_notes = []
        for note in midi_notes:
            for offset in PAD_VOICING_OFFSETS:
                all_notes.append(note + offset)

        if not all_notes:
            return buf_l, buf_r

        # Initialise or resize phase state to match voice count
        n_voices = len(all_notes)
        if self._osc_phases is None or len(self._osc_phases) != n_voices:
            self._osc_phases = np.zeros(n_voices, dtype=np.float64)

        # Render each note as a supersaw voice and accumulate
        for i, note in enumerate(all_notes):
            note = max(0, min(127, note))
            l, r, new_phases = supersaw(note, n_samples, self.sr,
                                        saw_count=5, detune_cents=60.0,
                                        osc_phases=self._osc_phases[i:i + 1].repeat(5))
            self._osc_phases[i] = new_phases[2]  # centre voice (index saw_count//2)
            buf_l += l / n_voices
            buf_r += r / n_voices

        # LP filter sweep driven by lpenv — 8 stepped segments
        env = lpenv(n_samples, self.sr, amount=2.0, decay_s=0.3)
        base_hz = cutoff * 0.3
        peak_hz = cutoff
        seg_len = n_samples // 8
        zi_l = None
        zi_r = None
        for seg in range(8):
            s = seg * seg_len
            e = s + seg_len if seg < 7 else n_samples
            mid = s + (e - s) // 2
            env_val = float(env[mid])
            seg_cutoff = base_hz + (peak_hz - base_hz) * env_val
            seg_cutoff = max(50.0, min(seg_cutoff, self.sr * 0.45))
            buf_l[s:e], zi_l = lpf(buf_l[s:e], seg_cutoff, self.sr, zi_l)
            buf_r[s:e], zi_r = lpf(buf_r[s:e], seg_cutoff, self.sr, zi_r)

        # Trancegate
        gate = trancegate(n_samples, self.sr, spb,
                          bar_offset_samples=bar_offset_samples,
                          speed=TRANCEGATE_SPEED, amount=TRANCEGATE_AMOUNT)
        buf_l *= gate
        buf_r *= gate

        # FDN reverb
        buf_l, buf_r = self._fdn.process(buf_l, buf_r)

        # Output gain
        buf_l *= g
        buf_r *= g

        return buf_l, buf_r
