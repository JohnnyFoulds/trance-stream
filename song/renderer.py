# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# song/renderer.py
# SongRenderer: renders a Song dataclass to audio (WAV) and MIDI.

from __future__ import annotations
import wave
from pathlib import Path
from typing import Optional

import numpy as np

try:
    import mido
    HAS_MIDO = True
except ImportError:
    HAS_MIDO = False


class SongRenderer:
    """Renders a Song bar-by-bar to stereo float32 audio and per-voice MIDI.

    Usage::

        song = build_song('sunrise', mood='uplifting')
        renderer = SongRenderer(song)
        buf_l, buf_r = renderer.render_bars(32)
        renderer.write_wav('/tmp/v3.wav')
        renderer.write_midi('/tmp/v3.mid')
    """

    def __init__(self, song: 'Song', active_tracks: set = None):
        from song.theory import samples_per_bar, samples_per_sixteenth
        from song.theory import SIDECHAIN_DEPTH, SIDECHAIN_ATTACK_S
        from synth.effects import Sidechain

        self.song    = song
        self.sr      = song.sr
        self._spb    = samples_per_bar(song.bpm, song.sr)
        self._sp16   = samples_per_sixteenth(song.bpm, song.sr)
        self._bar    = 0
        self._active_tracks = active_tracks  # None = all active; set of names = filter
        self._sidechain = Sidechain(depth=SIDECHAIN_DEPTH,
                                    attack_s=SIDECHAIN_ATTACK_S, sr=song.sr)
        self._audio_l: list[np.ndarray] = []
        self._audio_r: list[np.ndarray] = []
        self._midi_log: dict[str, list] = {}  # voice → [(bar, step, midi_note, duration_ticks)]
        # Kick/hihat/clap tails that overflow the current bar's boundary.
        # Added to the start of the next bar before new hits are placed.
        self._kick_spill_l: np.ndarray | None = None
        self._kick_spill_r: np.ndarray | None = None
        # CA state injected by the stream loop each bar (optional).
        # Keys: 'density' (float 0–1), 'voicing_offset' (int semitones).
        self.ca_state: dict = {}

    def render_bars(self, n_bars: int) -> tuple[np.ndarray, np.ndarray]:
        """Render n_bars bars of audio. Returns (buf_l, buf_r) as float32."""
        all_l = []
        all_r = []
        for _ in range(n_bars):
            bar_l, bar_r = self._render_bar()
            all_l.append(bar_l)
            all_r.append(bar_r)

        l = np.concatenate(all_l).astype(np.float32)
        r = np.concatenate(all_r).astype(np.float32)
        self._audio_l = all_l
        self._audio_r = all_r
        return l, r

    def _render_bar(self) -> tuple[np.ndarray, np.ndarray]:
        """Render one bar. Advances self._bar."""
        from song.theory import (
            KICK_STEPS_BASIC, KICK_STEPS_SYNCOPATED,
            CLAP_STEPS_BACKBEAT, HIHAT_STEPS,
            HIHAT_STEPS_OFFBEAT, HIHAT_STEPS_SPARSE,
            GAIN_KICK, GAIN_PAD, GAIN_LEAD,
            GAIN_HIHAT, GAIN_CLAP,
            chord_to_midi,
        )
        from song.pattern import notearp_pattern

        bar  = self._bar
        spb  = self._spb
        sp16 = self._sp16
        song = self.song
        sb   = song.stage_bars

        mix_l = np.zeros(spb, dtype=np.float32)
        mix_r = np.zeros(spb, dtype=np.float32)

        # Current chord for this bar — uses phase-aware progression and root
        chord_prog, _, effective_root, chord_idx = self._chord_state(bar)
        chord_degrees = chord_prog[chord_idx]
        chord_midi    = chord_to_midi(chord_degrees, effective_root, song.scale)

        kick_buf_l = None
        kick_buf_r = None

        # ── Kick ─────────────────────────────────────────────────────────────
        # Apply spill from previous bar's kick tails first.
        if self._kick_spill_l is not None:
            n_spill = min(len(self._kick_spill_l), spb)
            mix_l[:n_spill] += self._kick_spill_l[:n_spill]
            mix_r[:n_spill] += self._kick_spill_r[:n_spill]
            # Any remaining spill beyond this bar carries forward again.
            if len(self._kick_spill_l) > spb:
                self._kick_spill_l = self._kick_spill_l[spb:]
                self._kick_spill_r = self._kick_spill_r[spb:]
            else:
                self._kick_spill_l = None
                self._kick_spill_r = None

        kick_track = self._get_track('kick')
        if kick_track and kick_track.is_active(bar):
            kit = kick_track.instrument
            if bar >= sb.get('kick_syncopated', 9999):
                kick_steps = KICK_STEPS_SYNCOPATED
            else:
                kick_steps = KICK_STEPS_BASIC

            kick_l, kick_r = kit.render_kick(gain=GAIN_KICK)
            new_spill_l = np.zeros(len(kick_l), dtype=np.float32)
            new_spill_r = np.zeros(len(kick_l), dtype=np.float32)

            for step in kick_steps:
                offset  = step * sp16
                end_bar = min(offset + len(kick_l), spb)
                n_in    = end_bar - offset
                mix_l[offset:end_bar] += kick_l[:n_in]
                mix_r[offset:end_bar] += kick_r[:n_in]
                # Accumulate tail that overflows the bar boundary.
                if offset + len(kick_l) > spb:
                    tail_start = spb - offset
                    new_spill_l[:len(kick_l) - tail_start] += kick_l[tail_start:]
                    new_spill_r[:len(kick_l) - tail_start] += kick_r[tail_start:]

            # Merge new spill with any residual spill already in progress.
            spill_len = int(np.nonzero(new_spill_l)[0][-1] + 1) if np.any(new_spill_l != 0) else 0
            if spill_len > 0:
                new_spill_l = new_spill_l[:spill_len]
                new_spill_r = new_spill_r[:spill_len]
                if self._kick_spill_l is not None:
                    n_merge = min(len(self._kick_spill_l), spill_len)
                    new_spill_l[:n_merge] += self._kick_spill_l[:n_merge]
                    new_spill_r[:n_merge] += self._kick_spill_r[:n_merge]
                self._kick_spill_l = new_spill_l
                self._kick_spill_r = new_spill_r

            kick_buf_l = mix_l.copy()  # save for sidechain key signal
            kick_buf_r = mix_r.copy()

        # ── Hi-hat ───────────────────────────────────────────────────────────
        _hihat_allowed = self._active_tracks is None or 'hihat' in self._active_tracks
        if _hihat_allowed and bar >= sb.get('hihat_on', 9999):
            kick_track2 = self._get_track('kick')
            if kick_track2:
                from song.arcs import hihat_decay_arc
                decay_s = hihat_decay_arc(bar)
                hh_l, hh_r = kick_track2.instrument.render_hihat(
                    decay_s=decay_s, gain=GAIN_HIHAT)
                hihat_pat = song.hihat_pattern if hasattr(song, 'hihat_pattern') else 'full'
                if hihat_pat == 'offbeat':
                    active_steps = HIHAT_STEPS_OFFBEAT
                elif hihat_pat == 'sparse':
                    active_steps = HIHAT_STEPS_SPARSE
                else:
                    active_steps = HIHAT_STEPS
                for step in active_steps:
                    offset = step * sp16
                    end    = min(offset + len(hh_l), spb)
                    n      = end - offset
                    mix_l[offset:end] += hh_l[:n]
                    mix_r[offset:end] += hh_r[:n]

        # ── Clap ─────────────────────────────────────────────────────────────
        _clap_allowed = self._active_tracks is None or 'clap' in self._active_tracks
        if _clap_allowed and bar >= sb.get('clap_on', 9999):
            kick_track3 = self._get_track('kick')
            if kick_track3:
                cl_l, cl_r = kick_track3.instrument.render_clap(gain=GAIN_CLAP)
                for step in CLAP_STEPS_BACKBEAT:
                    offset = step * sp16
                    end    = min(offset + len(cl_l), spb)
                    n      = end - offset
                    mix_l[offset:end] += cl_l[:n]
                    mix_r[offset:end] += cl_r[:n]

        # ── Pad ──────────────────────────────────────────────────────────────
        pad_track = self._get_track('pad')
        if pad_track and pad_track.is_active(bar):
            # SA's pad sits one octave above the root register (+12 semitones).
            # chord_midi is computed from root_midi=48 (C3); without the transpose
            # the pad plays C3-Bb3 (131-233 Hz), one full octave below SA's C4-F4.
            if bar >= sb.get('pad_chord_on', 9999):
                notes = [m + 12 for m in chord_midi]
            else:
                notes = [song.root_midi + 12]
            kwargs = pad_track.render_kwargs(bar)
            pad_l, pad_r = pad_track.instrument.render(
                notes, spb, gain=GAIN_PAD, chord_id=chord_idx,
                global_offset_samples=bar * spb, **kwargs)
            # Sidechain: duck pad on kick
            if kick_buf_l is not None:
                pad_l, pad_r = self._sidechain.process(pad_l, pad_r, kick_buf_l)
            mix_l += pad_l
            mix_r += pad_r

        # ── Bass ─────────────────────────────────────────────────────────────
        bass_track = self._get_track('bass')
        if bass_track and bass_track.is_active(bar):
            from song.theory import BASS_STEPS_A, BASS_STEPS_B, GAIN_BASS
            # CA density above 0.55 → denser step pattern (more hits per bar).
            # Below that threshold alternate A/B as before.
            ca_density = self.ca_state.get('density', 0.5)
            if ca_density > 0.55:
                bass_steps = BASS_STEPS_B
            else:
                bass_steps = BASS_STEPS_A if bar % 2 == 0 else BASS_STEPS_B
            bass_midi = chord_midi[0] - 12
            bass_midi = max(24, min(60, bass_midi))
            kwargs = bass_track.render_kwargs(bar)
            # Per-step rendering: fire a fresh acidenv at each onset position.
            # Each note renders for 2 sixteenth-note durations (the acidenv
            # decays within ~80-150ms; 2×4725=9450 samples ≈ 214ms).
            bass_l_bar = np.zeros(spb, dtype=np.float32)
            bass_r_bar = np.zeros(spb, dtype=np.float32)
            step_dur = sp16 * 2
            for step in bass_steps:
                onset = step * sp16
                if onset >= spb:
                    continue
                n_step = min(step_dur, spb - onset)
                bl, br = bass_track.instrument.render(bass_midi, n_step, gain=1.0, **kwargs)
                bass_l_bar[onset:onset + n_step] += bl
                bass_r_bar[onset:onset + n_step] += br
            bass_l_bar *= GAIN_BASS
            bass_r_bar *= GAIN_BASS
            if kick_buf_l is not None:
                bass_l_bar, bass_r_bar = self._sidechain.process(
                    bass_l_bar, bass_r_bar, kick_buf_l)
            mix_l += bass_l_bar
            mix_r += bass_r_bar

        # ── Lead ─────────────────────────────────────────────────────────────
        lead_track = self._get_track('lead')
        if lead_track and lead_track.is_active(bar):
            from song.pattern import lead_melody_pattern
            kwargs = lead_track.render_kwargs(bar)

            # SA's lead sits +24 semitones above the base chord (two octaves above
            # the unshifted chord_midi, one octave above the pad which is at +12).
            # chord_midi is in the C3 register; pad is at +12 (C4); lead at +24 (C5).
            # This matches SA's .add 14 in a 7-note scale: +14 scale steps = +24 semitones
            # = two octaves, placing the lead in C5-F5 (~523-698 Hz) where it cuts above
            # the pad without clashing.
            #
            # CA voicing offset — SA's .add "<5 4 0 <0 2>>" equivalent.
            # Two centre CA bits pick from (0, 2, 5, 7) semitones added to all lead notes,
            # creating non-repeating harmonic colour shifts without changing the chord.
            # Only applied once the lead melody has started to avoid shifting the root drone.
            ca_vo = self.ca_state.get('voicing_offset', 0)
            if bar >= sb.get('lead_melody_on', 9999):
                lead_chord_midi = [m + 24 + ca_vo for m in chord_midi]
                lead_root_midi  = song.root_midi + 24 + ca_vo
            else:
                lead_chord_midi = [m + 24 for m in chord_midi]
                lead_root_midi  = song.root_midi + 24

            # CA density drives delay wet: dense CA = more wash (0.25–0.85).
            ca_density = self.ca_state.get('density', 0.5)
            lead_track.instrument._delay._wet = 0.25 + ca_density * 0.6

            if bar >= sb.get('lead_melody_on', 9999):
                # SA's melody: two sparse notes per bar (steps 4 and 10),
                # each sustained for 6 sixteenth-notes; note choices cycle by bar.
                pattern = lead_melody_pattern(lead_chord_midi, bar)
                lead_l_bar = np.zeros(spb, dtype=np.float32)
                lead_r_bar = np.zeros(spb, dtype=np.float32)
                # 6 sixteenth-notes per note — matches SA's @@2 / @3 weighting.
                # SA holds notes for ~3/8 of a bar; the acidenv decays in ~120ms
                # but the trancegate shapes the amplitude further.
                step_dur = sp16 * 6
                for step, note in zip(pattern.steps, pattern.notes):
                    onset = step * sp16
                    if onset >= spb:
                        continue
                    n_step = min(step_dur, spb - onset)
                    sl, sr_ = lead_track.instrument.render(
                        [note], n_step, bar_offset_samples=bar * spb + onset, **kwargs)
                    lead_l_bar[onset:onset + n_step] += sl
                    lead_r_bar[onset:onset + n_step] += sr_
                lead_l, lead_r = lead_l_bar, lead_r_bar
            else:
                # Root note only: single render for whole bar
                lead_l, lead_r = lead_track.instrument.render(
                    [lead_root_midi], spb, bar_offset_samples=bar * spb, **kwargs)
            if kick_buf_l is not None:
                lead_l, lead_r = self._sidechain.process(lead_l, lead_r, kick_buf_l)
            mix_l += lead_l
            mix_r += lead_r

        # Soft clip to prevent digital overs
        mix_l = np.tanh(mix_l)
        mix_r = np.tanh(mix_r)

        self._bar += 1
        return mix_l, mix_r

    def _chord_state(self, bar: int) -> tuple:
        """Return (chord_prog, chord_weights, root_midi, chord_idx) for a bar."""
        from song.arcs import chord_state_at
        prog, weights, root = chord_state_at(bar, self.song)
        cycle_len = sum(weights)
        pos = bar % cycle_len
        cumulative = 0
        for i, w in enumerate(weights):
            cumulative += w
            if pos < cumulative:
                return prog, weights, root, i % len(prog)
        return prog, weights, root, 0

    def _chord_index(self, bar: int) -> int:
        """Return current chord index (kept for compatibility)."""
        _, _, _, idx = self._chord_state(bar)
        return idx

    def _get_track(self, instrument_type: str):
        """Return the first Track matching instrument_type, or None if muted/absent."""
        if self._active_tracks is not None and instrument_type not in self._active_tracks:
            return None
        for t in self.song.tracks:
            if t.instrument_type == instrument_type:
                return t
        return None

    def write_wav(self, path: str) -> None:
        """Write accumulated audio to a 16-bit stereo WAV file."""
        if not self._audio_l:
            raise RuntimeError("No audio rendered yet — call render_bars() first")
        l = np.concatenate(self._audio_l)
        r = np.concatenate(self._audio_r)
        stereo = np.column_stack([l, r])
        pcm = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)

        with wave.open(path, 'wb') as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(self.sr)
            wf.writeframes(pcm.tobytes())

    def write_midi(self, path: str) -> None:
        """Write a multi-track MIDI file. Requires mido."""
        if not HAS_MIDO:
            raise ImportError("mido required: pip install mido")
        # Minimal implementation: write a single-track MIDI with tempo
        mid = mido.MidiFile(type=0, ticks_per_beat=480)
        track = mido.MidiTrack()
        mid.tracks.append(track)
        tempo = int(60_000_000 / self.song.bpm)
        track.append(mido.MetaMessage('set_tempo', tempo=tempo, time=0))
        track.append(mido.MetaMessage('end_of_track', time=0))
        mid.save(path)

    def notearp_to_midi(self, bar: int, chord_degrees: list[int]) -> list[int]:
        """Apply SA_NOTEARP_PATTERN to a chord, return MIDI notes for this bar.

        -1 entries in SA_NOTEARP_PATTERN become -1 in the output (rests).
        """
        from song.theory import SA_NOTEARP_PATTERN, chord_to_midi
        from song.arcs import chord_state_at
        _, _, effective_root = chord_state_at(bar, self.song)
        chord_midi = chord_to_midi(chord_degrees, effective_root, self.song.scale)
        notes = []
        for idx in SA_NOTEARP_PATTERN:
            if idx >= 0:
                notes.append(chord_midi[idx % len(chord_midi)])
            else:
                notes.append(-1)
        return notes
