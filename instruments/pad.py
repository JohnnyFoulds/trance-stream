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
                 gain: float = None, sr: int = 44100,
                 detune_cents: float = 60.0,
                 room_size: float = 0.7,
                 saw_count: int = 5):
        from song.theory import GAIN_PAD
        from synth.effects import SimpleFDN

        self.root_midi     = root_midi
        self.cutoff_slider = cutoff_slider
        self.gain          = gain if gain is not None else GAIN_PAD
        self.sr            = sr
        self.detune_cents  = detune_cents
        self.saw_count     = saw_count
        self._fdn          = SimpleFDN(room_size=room_size, sr=sr)
        self._osc_phases   = None  # shape (n_voices, saw_count), initialised on first render
        self._samples_rendered = 0  # cumulative sample count for trancegate phase continuity
        self._lpf_zi_l     = None  # LP filter state persisted across bars
        self._lpf_zi_r     = None

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

        # Expand notes with voicing offsets and their gain weights.
        # Sub-bass doublings (-14, -21 semitones) are quieter than the root voice
        # so they add weight without dominating the spectral centroid.
        # Gain weights: root=1.0, -14 semitone doubling=0.35, -21 semitone=0.15
        # Source: docs/music_theory/02_sa_vocabulary_codified.md §1
        VOICING_GAINS = [1.0, 0.35, 0.15]
        all_notes   = []
        voice_gains = []
        for note in midi_notes:
            for offset, vg in zip(PAD_VOICING_OFFSETS, VOICING_GAINS):
                all_notes.append(note + offset)
                voice_gains.append(vg)

        if not all_notes:
            return buf_l, buf_r

        n_voices = len(all_notes)
        # Store saw_count phases per voice so all detuned oscillators continue
        # correctly across bar boundaries (not just the middle voice).
        if self._osc_phases is None or self._osc_phases.shape != (n_voices, self.saw_count):
            self._osc_phases = np.zeros((n_voices, self.saw_count), dtype=np.float64)

        root_gain = voice_gains[0]  # always 1.0
        for i, (note, vg) in enumerate(zip(all_notes, voice_gains)):
            note = max(0, min(127, note))
            l, r, new_phases = supersaw(note, n_samples, self.sr,
                                        saw_count=self.saw_count,
                                        detune_cents=self.detune_cents,
                                        osc_phases=self._osc_phases[i])
            self._osc_phases[i] = new_phases   # store all saw_count phases
            buf_l += l * vg
            buf_r += r * vg

        # LP filter sweep driven by lpenv — 8 stepped segments.
        # Strudel lpenv(2) semantics: filter rests at slider value and opens
        # 2 octaves (4×) upward on each note trigger, then decays back.
        # lpenv returns values scaled by amount/9.0 (peak ≈ 0.222 for amount=2);
        # normalise to [0,1] by dividing by that scale factor.
        # Filter state (zi_l/zi_r) is persisted across bars to avoid clicks.
        amount = 2.0
        env = lpenv(n_samples, self.sr, amount=amount, decay_s=0.3)
        env_01_scale = amount / 9.0          # peak value of lpenv output
        base_hz = cutoff                     # resting cutoff = slider value
        peak_hz = cutoff * 4.0              # 2 octaves above base at trigger
        seg_len = n_samples // 8
        zi_l = self._lpf_zi_l
        zi_r = self._lpf_zi_r
        for seg in range(8):
            s = seg * seg_len
            e = s + seg_len if seg < 7 else n_samples
            mid = s + (e - s) // 2
            env_01 = min(float(env[mid]) / env_01_scale, 1.0)
            seg_cutoff = base_hz + (peak_hz - base_hz) * env_01
            seg_cutoff = max(50.0, min(seg_cutoff, self.sr * 0.45))
            buf_l[s:e], zi_l = lpf(buf_l[s:e], seg_cutoff, self.sr, zi_l)
            buf_r[s:e], zi_r = lpf(buf_r[s:e], seg_cutoff, self.sr, zi_r)
        self._lpf_zi_l = zi_l
        self._lpf_zi_r = zi_r

        # Trancegate — use cumulative sample count for phase continuity across bars.
        # bar_offset_samples is used for intra-bar step onsets (lead per-step rendering);
        # for bar-by-bar pad rendering, _samples_rendered tracks the global phase.
        gate = trancegate(n_samples, self.sr, spb,
                          bar_offset_samples=self._samples_rendered + bar_offset_samples,
                          speed=TRANCEGATE_SPEED, amount=TRANCEGATE_AMOUNT)
        buf_l *= gate
        buf_r *= gate
        self._samples_rendered += n_samples

        # FDN reverb
        buf_l, buf_r = self._fdn.process(buf_l, buf_r)

        # Output gain
        buf_l *= g
        buf_r *= g

        return buf_l, buf_r
