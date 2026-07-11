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

    def __init__(self, root_midi: int = 48, cutoff_slider: float = 0.50,
                 gain: float = None, sr: int = 44100,
                 detune_cents: float = 60.0,
                 room_size: float = 0.7,
                 saw_count: int = 5,
                 voicing_offsets: list = None,
                 bpm: float = 140.0):
        from song.theory import GAIN_PAD
        from synth.effects import SimpleFDN

        self.root_midi     = root_midi
        self.cutoff_slider = cutoff_slider
        self.gain          = gain if gain is not None else GAIN_PAD
        self.sr            = sr
        self.detune_cents  = detune_cents
        self.saw_count     = saw_count
        self._fdn          = SimpleFDN(room_size=room_size, sr=sr)
        self._voicing_offsets = voicing_offsets  # None = use PAD_VOICING_OFFSETS from theory
        self.bpm           = bpm
        self._osc_phases   = None  # shape (n_voices, saw_count), initialised on first render
        self._lpf_zi_l     = None  # LP filter state persisted across bars
        self._lpf_zi_r     = None
        # lpenv persistent state — tracks seconds since the last chord trigger so the
        # filter swell continues smoothly across bar boundaries instead of resetting
        # to the bright peak on every new bar render.
        self._lpenv_t_s    = 0.0    # seconds since last chord trigger
        self._last_chord_id = None  # last chord index; change = new trigger

    def render(self, midi_notes: list, n_samples: int,
               bar_offset_samples: int = 0,
               cutoff_slider: float = None,
               gain: float = None,
               chord_id: int = None,
               global_offset_samples: int = 0) -> tuple:
        """Render n_samples of pad audio for the given chord (list of MIDI notes).

        midi_notes  : list of int — MIDI pitches to play (one supersaw per note)
        chord_id    : int or None — pass the current chord index so a chord change
                      triggers a fresh lpenv swell. None = treat as same chord.
        Returns (buf_l, buf_r) as float32 numpy arrays.

        SA's pad signal chain:
          supersaw → lpenv filter swell → rlpf LP → trancegate → FDN reverb → gain

        The voicing offsets (-14, -21 semitones) are applied: each chord note also
        generates doublings at -14 and -21 semitones (sub-bass fills the low end
        before the acid bass enters).

        SA's lpenv(2): the filter rests at the slider value. On each chord trigger
        it opens to ~1.5 octaves above the rest cutoff, then decays slowly back
        over ~0.8 seconds. This is a gentle swell, NOT a wah; it decays slowly
        enough to sustain brightness through the chord duration.
        """
        import numpy as np
        from synth.oscillators import supersaw
        from synth.filters import lpf2, rlpf_to_hz
        from synth.envelopes import trancegate
        from song.theory import (PAD_VOICING_OFFSETS, TRANCEGATE_DENSITY,
                                  TRANCEGATE_FLOOR, TRANCEGATE_SEED, samples_per_bar)

        slider = cutoff_slider if cutoff_slider is not None else self.cutoff_slider
        g      = gain if gain is not None else self.gain
        spb    = samples_per_bar(bpm=self.bpm)
        cutoff = rlpf_to_hz(slider)

        buf_l = np.zeros(n_samples, dtype=np.float32)
        buf_r = np.zeros(n_samples, dtype=np.float32)

        # Expand notes with voicing offsets and their gain weights.
        # Sub-bass doublings (-14, -21 semitones) are quieter than the root voice
        # so they add weight without dominating the spectral centroid.
        # Gain weights: root=1.0, -14 semitone doubling=0.35, -21 semitone=0.15
        # Source: docs/music_theory/02_sa_vocabulary_codified.md §1
        VOICING_GAINS = [1.0, 0.35, 0.15]
        offsets = self._voicing_offsets if self._voicing_offsets is not None else PAD_VOICING_OFFSETS
        gains   = VOICING_GAINS[:len(offsets)]
        all_notes   = []
        voice_gains = []
        for note in midi_notes:
            for offset, vg in zip(offsets, gains):
                all_notes.append(note + offset)
                voice_gains.append(vg)

        if not all_notes:
            return buf_l, buf_r

        n_voices = len(all_notes)
        # Store saw_count phases per voice so all detuned oscillators continue
        # correctly across bar boundaries (not just the middle voice).
        # When voice count grows (e.g. root→chord at pad_chord_on), carry over
        # existing phases and initialise new voices from voice-0's phases so they
        # don't all restart from 0 simultaneously (which creates a transient pop).
        if self._osc_phases is None or self._osc_phases.shape[1] != self.saw_count:
            self._osc_phases = np.zeros((n_voices, self.saw_count), dtype=np.float64)
        elif self._osc_phases.shape[0] != n_voices:
            old = self._osc_phases
            self._osc_phases = np.zeros((n_voices, self.saw_count), dtype=np.float64)
            n_carry = min(old.shape[0], n_voices)
            self._osc_phases[:n_carry] = old[:n_carry]
            # New voices above n_carry inherit voice-0 phases to avoid phase-zero pop
            for v in range(n_carry, n_voices):
                self._osc_phases[v] = old[0] if old.shape[0] > 0 else np.zeros(self.saw_count)

        for i, (note, vg) in enumerate(zip(all_notes, voice_gains)):
            note = max(0, min(127, note))
            l, r, new_phases = supersaw(note, n_samples, self.sr,
                                        saw_count=self.saw_count,
                                        detune_cents=self.detune_cents,
                                        osc_phases=self._osc_phases[i])
            self._osc_phases[i] = new_phases   # store all saw_count phases
            buf_l += l * vg
            buf_r += r * vg

        # Normalise by sum of voice gains so amplitude is independent of chord size.
        # Without this, 6 voiced notes at gains 1.0/0.35/0.15 each sum to peak >1.0
        # before any downstream gain, causing saturation in the master mix.
        gain_sum = sum(voice_gains)
        buf_l /= gain_sum
        buf_r /= gain_sum

        # LP filter — SA's lpenv(2) behaviour:
        #   - Filter rests at slider value (base_hz = cutoff at rest)
        #   - On chord trigger: opens to peak_hz (~1.5 octaves above = 2.83× base)
        #   - Decays back to base_hz over ~0.8s (slow swell, not a wah)
        #   - Cross-bar: if chord has not changed, the swell continues from where
        #     it left off (persistent _lpenv_t_s timer, not reset on every render call)
        #
        # SA reference: slider=0.5 → base 1100 Hz, peak ~3100 Hz.
        #               At session open the pad is warm and bright immediately.
        #
        # If chord_id changes, reset the swell timer to trigger a new bloom.
        if chord_id is not None and chord_id != self._last_chord_id:
            self._lpenv_t_s = 0.0
            self._last_chord_id = chord_id
            # Do NOT reset _lpf_zi here. The filter output is continuous — it
            # will smoothly track the new peak_hz cutoff from its current state.
            # Resetting zi to None forces the filter output to jump discontinuously
            # to a zero initial condition, which creates an audible click.

        base_hz  = cutoff                   # filter rests at slider value
        peak_hz  = cutoff * 2.83            # ~1.5 octaves above (2^1.5 = 2.83)
        decay_s  = 0.80                     # slow swell — holds brightness ~0.8s

        seg_len = max(1, n_samples // 8)
        zi_l = self._lpf_zi_l
        zi_r = self._lpf_zi_r
        for seg in range(8):
            s = seg * seg_len
            e = s + seg_len if seg < 7 else n_samples
            if s >= n_samples:
                break
            mid_t    = self._lpenv_t_s + (s + (e - s) // 2) / self.sr
            swell_01 = float(np.exp(-mid_t / decay_s))   # 1.0 at trigger → 0.0 as time grows
            seg_cutoff = base_hz + (peak_hz - base_hz) * swell_01
            seg_cutoff = float(np.clip(seg_cutoff, 50.0, self.sr * 0.45))
            buf_l[s:e], zi_l = lpf2(buf_l[s:e], seg_cutoff, 0.707, self.sr, zi_l)
            buf_r[s:e], zi_r = lpf2(buf_r[s:e], seg_cutoff, 0.707, self.sr, zi_r)
        self._lpenv_t_s  += n_samples / self.sr   # advance the swell timer
        self._lpf_zi_l = zi_l
        self._lpf_zi_r = zi_r

        # Trancegate — global_offset_samples anchors the gate phase to absolute
        # session time (bar * spb), so the gate is in phase with the kick regardless
        # of which bar the pad entered on. bar_offset_samples adds intra-bar offset
        # for per-step rendering (used by lead; pad always passes 0).
        gate = trancegate(n_samples, self.sr, spb,
                          bar_offset_samples=global_offset_samples + bar_offset_samples,
                          density=TRANCEGATE_DENSITY, floor=TRANCEGATE_FLOOR,
                          seed=TRANCEGATE_SEED)
        buf_l *= gate
        buf_r *= gate

        # FDN reverb
        buf_l, buf_r = self._fdn.process(buf_l, buf_r)

        # Output gain
        buf_l *= g
        buf_r *= g

        return buf_l, buf_r
