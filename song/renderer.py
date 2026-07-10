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
        from song.theory import SIDECHAIN_DEPTH, SIDECHAIN_ATTACK_S, SIDECHAIN_DEPTH_HEY_ANGEL
        from synth.effects import Sidechain

        self.song    = song
        self.sr      = song.sr
        self._spb    = samples_per_bar(song.bpm, song.sr)
        self._sp16   = samples_per_sixteenth(song.bpm, song.sr)
        self._bar    = 0
        self._active_tracks = active_tracks  # None = all active; set of names = filter
        style = getattr(song, 'style', 'trance')
        sc_depth = SIDECHAIN_DEPTH_HEY_ANGEL if style == 'hey_angel' else SIDECHAIN_DEPTH
        self._sidechain = Sidechain(depth=sc_depth,
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

    def fast_forward(self, n_bars: int) -> None:
        """Advance song state by n_bars without synthesising audio.

        Only advances counters, filter state, and chord tracking — skips
        the expensive oscillator and reverb rendering. The first real bar
        after fast_forward() may have a very slight oscillator-phase
        discontinuity (inaudible in practice at trance transient density).
        """
        for _ in range(n_bars):
            bar = self._bar
            # Advance filter state: update lpenv timer on pad (preserves swell position)
            pad_track = self._get_track('pad')
            if pad_track and pad_track.is_active(bar):
                spb_s = self._spb / self.sr
                if hasattr(pad_track.instrument, '_lpenv_t_s'):
                    pad_track.instrument._lpenv_t_s = min(
                        pad_track.instrument._lpenv_t_s + spb_s, 10.0)
                # Update chord id so lpenv retriggers correctly on playback
                from song.arcs import chord_state_at
                _, _, _ = chord_state_at(bar, self.song)  # warm the cache path
            self._bar += 1

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

        from song.arcs import breakdown_at, gain_arc as _gain_arc, pad_seg_count
        in_breakdown = breakdown_at(bar, song)
        master_gain  = _gain_arc(bar, song)

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
            style = getattr(song, 'style', 'trance')
            if style == 'hey_angel':
                from song.theory import KICK_STEPS_HALFTIME
                kick_steps = KICK_STEPS_HALFTIME
            elif bar >= sb.get('kick_syncopated', 9999):
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
        if _hihat_allowed and not in_breakdown and bar >= sb.get('hihat_on', 9999):
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
        if _clap_allowed and not in_breakdown and bar >= sb.get('clap_on', 9999):
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
            n_segs = pad_seg_count(bar, song)
            if n_segs == 1:
                pad_l, pad_r = pad_track.instrument.render(
                    notes, spb, gain=GAIN_PAD, chord_id=chord_idx,
                    global_offset_samples=bar * spb, **kwargs)
            else:
                # Retrigger lpenv n_segs times per bar — SA's .seg 16 equivalent.
                # Each segment gets a fresh lpenv swell, turning the drone into
                # rhythmic filter stabs that pulse with the kick grid.
                seg_len = spb // n_segs
                pad_l = np.zeros(spb, dtype=np.float32)
                pad_r = np.zeros(spb, dtype=np.float32)
                for seg in range(n_segs):
                    onset = seg * seg_len
                    n = seg_len if seg < n_segs - 1 else spb - onset
                    # Force chord_id change each segment to retrigger lpenv swell
                    fake_chord_id = chord_idx * 1000 + seg
                    sl, sr_ = pad_track.instrument.render(
                        notes, n, gain=GAIN_PAD,
                        chord_id=fake_chord_id,
                        global_offset_samples=bar * spb + onset, **kwargs)
                    pad_l[onset:onset + n] += sl
                    pad_r[onset:onset + n] += sr_
            # Sidechain: duck pad on kick
            if kick_buf_l is not None:
                pad_l, pad_r = self._sidechain.process(pad_l, pad_r, kick_buf_l)
            mix_l += pad_l
            mix_r += pad_r

        # ── Bass ─────────────────────────────────────────────────────────────
        bass_track = self._get_track('bass')
        if bass_track and bass_track.is_active(bar) and not in_breakdown:
            from song.theory import BASS_STEPS_A, BASS_STEPS_B, GAIN_BASS
            style = getattr(song, 'style', 'trance')
            bass_l_bar = np.zeros(spb, dtype=np.float32)
            bass_r_bar = np.zeros(spb, dtype=np.float32)
            kwargs = bass_track.render_kwargs(bar)

            if style == 'hey_angel':
                # "Hey Angel…" bass pattern (research/analysis/hey_angel_analysis.md §4c):
                # G1(quarter=4 steps) → F2(8th=2 steps) → portamento sweep F2→G1(8th=2 steps)
                # G1=MIDI 43, F2=MIDI 53 (flat-7 above G1)
                HA_G1 = 43
                HA_F2 = 53
                # Hit 1: G1 held for 4 sixteenths (quarter note) at step 0
                n_quarter = sp16 * 4
                n_q = min(n_quarter, spb)
                bl, br = bass_track.instrument.render(HA_G1, n_q, gain=1.0, **kwargs)
                bass_l_bar[0:n_q] += bl
                bass_r_bar[0:n_q] += br
                # Hit 2: F2 for 2 sixteenths (eighth note) at step 4
                onset_f2 = sp16 * 4
                n_8th = sp16 * 2
                n_f2 = min(n_8th, spb - onset_f2)
                if n_f2 > 0:
                    bl, br = bass_track.instrument.render(HA_F2, n_f2, gain=1.0, **kwargs)
                    bass_l_bar[onset_f2:onset_f2 + n_f2] += bl
                    bass_r_bar[onset_f2:onset_f2 + n_f2] += br
                # Hit 3: portamento glide F2→G1 over 2 sixteenths (eighth note) at step 6
                onset_sweep = sp16 * 6
                n_sweep = min(n_8th, spb - onset_sweep)
                if n_sweep > 0:
                    # portamento_s > 0 triggers linear pitch glide in AcidBass.render()
                    bl, br = bass_track.instrument.render(
                        HA_F2, n_sweep, gain=1.0,
                        portamento_s=float(n_sweep) / song.sr,
                        target_midi=HA_G1, **kwargs)
                    bass_l_bar[onset_sweep:onset_sweep + n_sweep] += bl
                    bass_r_bar[onset_sweep:onset_sweep + n_sweep] += br
            else:
                # CA density above 0.55 → denser step pattern (more hits per bar).
                ca_density = self.ca_state.get('density', 0.5)
                if ca_density > 0.55:
                    bass_steps = BASS_STEPS_B
                else:
                    bass_steps = BASS_STEPS_A if bar % 2 == 0 else BASS_STEPS_B
                bass_midi = chord_midi[0] - 12
                bass_midi = max(24, min(60, bass_midi))
                # Per-step rendering: fire a fresh acidenv at each onset position.
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
        if lead_track and lead_track.is_active(bar) and not in_breakdown:
            from song.pattern import lead_melody_pattern
            kwargs = lead_track.render_kwargs(bar)
            style = getattr(song, 'style', 'trance')

            if style == 'hey_angel':
                # "Hey Angel…" melody: C4→F#3 chromatic descend with slow portamento
                # Rate ~15 sem/sec = 0.067s/semitone; 6 semitones over ~0.4s per bar
                # (research/analysis/hey_angel_analysis.md §4a)
                # C4=MIDI 60, F#3=MIDI 54; descend cycles bar-by-bar
                HA_MELODY_START = 60   # C4
                HA_MELODY_END   = 54   # F#3
                # Render the whole bar as one smooth portamento glide C4→F#3
                lead_l, lead_r = lead_track.instrument.render(
                    [HA_MELODY_START], spb,
                    bar_offset_samples=bar * spb,
                    samples_per_bar=spb,
                    portamento_s=float(spb) / song.sr,
                    target_midi=HA_MELODY_END,
                    **kwargs)
                if kick_buf_l is not None:
                    lead_l, lead_r = self._sidechain.process(lead_l, lead_r, kick_buf_l)
                mix_l += lead_l
                mix_r += lead_r
                # Pluck rendering handled below (outside lead block)
            else:
                # SA's lead sits +24 semitones above the base chord (two octaves above
                # the unshifted chord_midi, one octave above the pad which is at +12).
                # chord_midi is in the C3 register; pad is at +12 (C4); lead at +24 (C5).
                # CA voicing offset — SA's .add "<5 4 0 <0 2>>" equivalent.
                _OFFSETS = (0, 2, 5, 7)
                if 'voicing_offset' in self.ca_state:
                    ca_vo = self.ca_state['voicing_offset']
                else:
                    _h = hash((song.seed, bar)) & 0xFF
                    ca_vo = _OFFSETS[_h % len(_OFFSETS)]

                if bar >= sb.get('lead_melody_on', 9999):
                    from song.theory import degree_to_midi
                    chord_root_degree = chord_degrees[0]
                    target_centre = effective_root + 24 + ca_vo
                    raw_vocab = [
                        degree_to_midi(chord_root_degree + i, effective_root, song.scale)
                        for i in range(5)
                    ]
                    lead_vocab = []
                    for note in raw_vocab:
                        note += 24 + ca_vo
                        while note > target_centre + 11:
                            note -= 12
                        while note < target_centre - 6:
                            note += 12
                        lead_vocab.append(note)
                    lead_chord_midi = lead_vocab
                    lead_root_midi  = lead_vocab[0]
                else:
                    lead_chord_midi = [m + 24 for m in chord_midi]
                    lead_root_midi  = effective_root + 24

                if 'density' in self.ca_state:
                    ca_density = self.ca_state['density']
                else:
                    _h2 = hash((song.seed, bar + 1)) & 0xFF
                    ca_density = 0.3 + (_h2 / 255.0) * 0.5
                lead_track.instrument._delay._wet = 0.25 + ca_density * 0.6

                if bar >= sb.get('lead_melody_on', 9999):
                    pattern = lead_melody_pattern(lead_chord_midi, bar)
                    lead_l_bar = np.zeros(spb, dtype=np.float32)
                    lead_r_bar = np.zeros(spb, dtype=np.float32)
                    step_dur = sp16 * 6
                    for step, note in zip(pattern.steps, pattern.notes):
                        onset = step * sp16
                        if onset >= spb:
                            continue
                        n_step = min(step_dur, spb - onset)
                        sl, sr_ = lead_track.instrument.render(
                            [note], n_step, bar_offset_samples=bar * spb + onset,
                            samples_per_bar=spb, **kwargs)
                        lead_l_bar[onset:onset + n_step] += sl
                        lead_r_bar[onset:onset + n_step] += sr_
                    lead_l, lead_r = lead_l_bar, lead_r_bar
                else:
                    lead_l, lead_r = lead_track.instrument.render(
                        [lead_root_midi], spb, bar_offset_samples=bar * spb,
                        samples_per_bar=spb, **kwargs)
                if kick_buf_l is not None:
                    lead_l, lead_r = self._sidechain.process(lead_l, lead_r, kick_buf_l)
                mix_l += lead_l
                mix_r += lead_r

        # ── Pluck (Hey Angel style only) ──────────────────────────────────────
        pluck_track = self._get_track('pluck')
        if pluck_track and pluck_track.is_active(bar):
            # E5 = MIDI 76 = 660 Hz; sustained for whole bar
            HA_E5 = 76
            pl_l, pl_r = pluck_track.instrument.render(HA_E5, spb,
                                                        gain=pluck_track.gain_target)
            if kick_buf_l is not None:
                pl_l, pl_r = self._sidechain.process(pl_l, pl_r, kick_buf_l)
            mix_l += pl_l
            mix_r += pl_r

        # Master gain arc: 0.55 → 1.0 over the first half of the song
        mix_l *= master_gain
        mix_r *= master_gain

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
