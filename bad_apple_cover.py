#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Bad Apple!! instrumental cover — trance synthesis using switch-angel infrastructure.

Reads research/reference_audio/midi/bad_apple.mid, maps its tracks to the existing
instrument classes (DrumKit, SupersawPad, AcidLead, AcidBass), and renders a trance
cover of the Alstroemeria Records arrangement (138 BPM, A natural minor).

Usage:
    python bad_apple_cover.py --stream --viz          # real-time + ASCII video
    python bad_apple_cover.py --wav bad_apple.wav     # render to file
    python bad_apple_cover.py --bars 32 --stream      # first 32 bars only (quick test)
    python bad_apple_cover.py --help

Determinism: same MIDI file + same --bpm = byte-identical WAV output.
"""
from __future__ import annotations

import argparse
import os
import queue
import sys
import threading
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# Repo root (for resolving relative paths regardless of cwd)
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent

# ---------------------------------------------------------------------------
# Musical constants — Bad Apple!! (Alstroemeria Records arrangement)
# ---------------------------------------------------------------------------
BPM         = 138.0
ROOT_MIDI   = 57           # A3
SR          = 44100
A_MINOR     = [0, 2, 3, 5, 7, 8, 10]  # A natural minor / Aeolian

# Hard-coded chord progression — Am / F / C / G (16-bar cycle, 4 bars each)
# Each entry = [scale_degree_of_root, scale_degree_of_fifth] in A natural minor.
# degree 0=A, 2=C, 3=D, 4=E, 5=F, 6=G
BAD_APPLE_CHORDS   = [[0, 4], [5, 2], [2, 6], [6, 3]]   # Am, F, C, G
BAD_APPLE_WEIGHTS  = [4, 4, 4, 4]

# Section structure: (start_bar, end_bar, name, active_tracks)
# Derived from the Alstroemeria Records arrangement structure.
BAD_APPLE_SECTIONS = [
    (0,   6,   'intro',  {'kick': False, 'pad': True,  'bass': False, 'lead': False}),
    (6,   22,  'verse1', {'kick': True,  'pad': True,  'bass': True,  'lead': True }),
    (22,  38,  'chorus1',{'kick': True,  'pad': True,  'bass': True,  'lead': True }),
    (38,  54,  'verse2', {'kick': True,  'pad': True,  'bass': True,  'lead': True }),
    (54,  70,  'chorus2',{'kick': True,  'pad': True,  'bass': True,  'lead': True }),
    (70,  80,  'bridge', {'kick': True,  'pad': True,  'bass': False, 'lead': False}),
    (80,  97,  'final',  {'kick': True,  'pad': True,  'bass': True,  'lead': True }),
    (97,  999, 'outro',  {'kick': True,  'pad': True,  'bass': True,  'lead': False}),
]

# Filter slider per section (rlpf_to_hz formula: (slider*12)**4 Hz)
_SECTION_SLIDER = {
    'intro':   0.55,
    'verse1':  0.65,
    'chorus1': 0.80,
    'verse2':  0.65,
    'chorus2': 0.80,
    'bridge':  0.55,
    'final':   0.82,
    'outro':   0.70,
}

# Drum note mapping for the MIDI file (analysed empirically — not GM standard)
# note 35/36 → kick (on beats, wide spacing), 39 → clap (backbeat pattern)
# notes 28/29/42/63/69/82 → hihat textures (dense/continuous pattern)
_DRUM_KICK_NOTES  = {35, 36}
_DRUM_CLAP_NOTES  = {39, 49, 60, 61}
_DRUM_HIHAT_NOTES = {28, 29, 42, 46, 63, 64, 69, 82}


# ---------------------------------------------------------------------------
# BadAppleSong — duck-typed to satisfy make_bar_info() / chord_state_at()
# ---------------------------------------------------------------------------
@dataclass
class BadAppleSong:
    bpm:           float = BPM
    sr:            int   = SR
    seed:          str   = 'bad_apple'
    mood:          str   = 'bad_apple'
    root_midi:     int   = ROOT_MIDI
    scale:         list  = field(default_factory=lambda: list(A_MINOR))
    chord_prog:    list  = field(default_factory=lambda: list(BAD_APPLE_CHORDS))
    chord_weights: list  = field(default_factory=lambda: list(BAD_APPLE_WEIGHTS))
    chord_prog_b:  list  = None
    root_shift:    int   = 0
    filter_pb_bar: int   = 9999   # no pullback — filter stays in opening arc
    stage_bars:    dict  = field(default_factory=dict)
    hihat_pattern: str   = 'full'


# ---------------------------------------------------------------------------
# Section helpers
# ---------------------------------------------------------------------------
def _section_at(bar: int) -> tuple:
    """Return (name, active_tracks) for a given bar."""
    for start, end, name, active in BAD_APPLE_SECTIONS:
        if start <= bar < end:
            return name, active
    return 'outro', BAD_APPLE_SECTIONS[-1][3]


def _chord_idx(bar: int) -> int:
    """Return chord index (0–3) for a given bar (4-bar rotation)."""
    return (bar % 16) // 4


def _section_slider(name: str) -> float:
    return _SECTION_SLIDER.get(name, 0.65)


def _fm_depth(bar: int) -> float:
    """FM depth ramps from 0 to 0.3 between bars 22 and 54, then stays."""
    if bar < 22:
        return 0.0
    return min((bar - 22) / 32.0, 1.0) * 0.3


def _master_gain(bar: int) -> float:
    """4-bar fade-in then constant."""
    return 0.5 + 0.5 * min(bar / 4.0, 1.0)


# ---------------------------------------------------------------------------
# MIDI parser
# ---------------------------------------------------------------------------
def parse_midi(midi_path: str, bpm: float = BPM, sr: int = SR) -> tuple:
    """Parse Bad Apple MIDI into per-bar note data.

    Returns:
        (bar_data, total_bars, stage_bars_dict)

    bar_data[bar] = {
        'drum_steps': {step: ['kick'|'hihat'|'clap']},
        'bass_notes': [(step, midi_note, dur_steps)],
        'lead_notes': [(step, midi_note, dur_steps)],
    }
    """
    try:
        import mido
    except ImportError:
        raise ImportError("mido required: pip install mido")

    mid = mido.MidiFile(midi_path)
    tpb   = mid.ticks_per_beat           # 96
    tpbar = tpb * 4                      # ticks per bar
    tp16  = max(1, tpb // 4)            # ticks per 16th note

    # ── Resolve tempo from the MIDI itself ──────────────────────────────────
    for track in mid.tracks:
        for m in track:
            if m.type == 'set_tempo':
                bpm = round(60_000_000 / m.tempo, 3)
                break

    # ── Collect note events per track ───────────────────────────────────────
    # Each track event: (cum_ticks_absolute, note, velocity)
    # Handles both note_off messages and note_on with velocity=0 (running status).
    def track_events(track):
        cum = 0
        events = []
        for m in track:
            cum += m.time
            if m.type == 'note_on':
                events.append((cum, m.note, m.velocity))
            elif m.type == 'note_off':
                events.append((cum, m.note, 0))  # normalise to vel=0 note-off
        return events

    # ── Track role assignment by name ───────────────────────────────────────
    def classify(name: str) -> str:
        n = name.lower()
        if 'drum' in n or 'perc' in n:
            return 'drums'
        if 'sub' in n and 'bass' in n:
            return 'subbass'
        if 'bass' in n and '2' not in n:
            return 'bass1'
        if 'bass2' in n or 'bass 2' in n:
            return 'bass2'
        if 'synth1' in n or 'synth 1' in n or 'synth1' in n.replace(' ', ''):
            return 'synth1'
        if 'synth2' in n or 'synth 2' in n or 'synth2' in n.replace(' ', ''):
            return 'synth2'
        if 'arp' in n:
            return 'arp'
        if 'guitar' in n:
            return 'guitar'
        if 'vocal' in n:
            return 'vocals'
        return 'other'

    bar_data: dict = {}

    def ensure_bar(b):
        if b not in bar_data:
            bar_data[b] = {'drum_steps': {}, 'bass_notes': [], 'lead_notes': []}

    max_bar = 0

    for track in mid.tracks:
        role = classify(track.name)
        events = track_events(track)

        # Build note durations: match note_on (vel>0) with note_off (vel=0)
        pending = {}  # note -> on_tick
        note_list = []  # (on_tick, off_tick, note)
        for tick, note, vel in events:
            if vel > 0:
                pending[note] = tick
            else:
                if note in pending:
                    note_list.append((pending.pop(note), tick, note))
        # Any still-pending notes: give them a default duration of 1 bar
        for note, on_tick in pending.items():
            note_list.append((on_tick, on_tick + tpbar, note))

        for on_tick, off_tick, note in note_list:
            bar   = on_tick // tpbar
            step  = round((on_tick % tpbar) / tp16)
            step  = min(step, 15)
            dur   = max(1, round((off_tick - on_tick) / tp16))
            max_bar = max(max_bar, bar)

            ensure_bar(bar)

            if role == 'drums':
                ds = bar_data[bar]['drum_steps']
                if step not in ds:
                    ds[step] = []
                if note in _DRUM_KICK_NOTES:
                    ds[step].append('kick')
                elif note in _DRUM_CLAP_NOTES:
                    ds[step].append('clap')
                elif note in _DRUM_HIHAT_NOTES:
                    ds[step].append('hihat')

            elif role == 'bass1':
                # "Bass" track: transpose +12 to land in audible bass register (62–208 Hz).
                # "Sub bass" track is skipped — its notes are mostly 23–39 Hz (subsonic).
                bar_data[bar]['bass_notes'].append((step, note + 12, dur))

            elif role in ('synth1', 'arp', 'guitar'):
                # Melody/lead candidates — synth1 is the main melody
                bar_data[bar]['lead_notes'].append((step, note, dur))

            # synth2, bass2, perc1/2, vocals: ignored or absorbed into pad/arp

    total_bars = max_bar + 2  # small buffer

    # ── Dedup bass: if multiple bass notes share a step, keep the highest ───
    # (after +12 transpose the melodic bass register is 62–208 Hz — keep highest)
    for b in bar_data.values():
        if not b['bass_notes']:
            continue
        by_step: dict = {}
        for step, note, dur in b['bass_notes']:
            if step not in by_step or note > by_step[step][0]:
                by_step[step] = (note, dur)
        b['bass_notes'] = [(s, n, d) for s, (n, d) in sorted(by_step.items())]

    # ── Lead: if multiple lead notes share a step, keep highest (melody top) ─
    for b in bar_data.values():
        if not b['lead_notes']:
            continue
        by_step: dict = {}
        for step, note, dur in b['lead_notes']:
            if step not in by_step or note > by_step[step][0]:
                by_step[step] = (note, dur)
        b['lead_notes'] = [(s, n, d) for s, (n, d) in sorted(by_step.items())]

    # ── stage_bars from first note bar per voice ─────────────────────────────
    first: dict = {}
    for bar, d in sorted(bar_data.items()):
        if 'kick' not in first:
            for kinds in d['drum_steps'].values():
                if 'kick' in kinds:
                    first['kick'] = bar; break
        if 'hihat' not in first:
            for kinds in d['drum_steps'].values():
                if 'hihat' in kinds:
                    first['hihat'] = bar; break
        if 'clap' not in first:
            for kinds in d['drum_steps'].values():
                if 'clap' in kinds:
                    first['clap'] = bar; break
        if 'bass' not in first and d['bass_notes']:
            first['bass'] = bar
        if 'lead' not in first and d['lead_notes']:
            first['lead'] = bar

    stage_bars = {
        'kick_on':        first.get('kick', 0),
        'pad_root_on':    0,
        'bass_on':        first.get('bass', 6),
        'lead_root_on':   first.get('lead', 6),
        'lead_melody_on': first.get('lead', 6),
        'pad_chord_on':   0,
        'lead_voicing_on':first.get('lead', 6),
        'clap_on':        first.get('clap', 6),
        'hihat_on':       first.get('hihat', 0),
        'kick_syncopated':9999,  # use as-is from MIDI
        'fm_on':          22,
        'pulse_on':       9999,
    }

    return bar_data, total_bars, stage_bars


# ---------------------------------------------------------------------------
# BadAppleRenderer
# ---------------------------------------------------------------------------
class BadAppleRenderer:
    """Renders Bad Apple!! bar by bar using the existing instrument classes."""

    def __init__(self, midi_path: str, bpm: float = BPM, sr: int = SR):
        sys.path.insert(0, str(REPO_ROOT))

        from instruments.drums import DrumKit
        from instruments.pad   import SupersawPad
        from instruments.lead  import AcidLead
        from instruments.bass  import AcidBass
        from synth.effects     import Sidechain
        from song.theory       import SIDECHAIN_DEPTH, SIDECHAIN_ATTACK_S

        self._bar_data, self._total_bars, stage_bars = parse_midi(midi_path, bpm, sr)

        self._spb  = int(sr * 4 * 60 / bpm)
        self._sp16 = self._spb // 16
        self.sr    = sr
        self._bpm  = bpm
        self._bar  = 0

        self._kit  = DrumKit(seed=42, sr=sr)
        self._pad  = SupersawPad(root_midi=ROOT_MIDI, sr=sr,
                                 detune_cents=60.0, room_size=0.7, saw_count=5)
        self._lead = AcidLead(root_midi=ROOT_MIDI, sr=sr, character='smooth')
        self._bass = AcidBass(sr=sr)
        self._sc   = Sidechain(depth=SIDECHAIN_DEPTH,
                               attack_s=SIDECHAIN_ATTACK_S, sr=sr)

        self._kick_spill_l: Optional[np.ndarray] = None
        self._kick_spill_r: Optional[np.ndarray] = None

        self.song      = BadAppleSong(bpm=bpm, sr=sr, stage_bars=stage_bars)
        self.ca_state  = {}
        self._audio_l  = []
        self._audio_r  = []

    def render_bar(self) -> tuple:
        """Render one bar. Advances internal bar counter."""
        from song.theory import (
            GAIN_KICK, GAIN_PAD, GAIN_LEAD, GAIN_BASS, GAIN_HIHAT, GAIN_CLAP,
            chord_to_midi,
        )

        bar   = self._bar
        spb   = self._spb
        sp16  = self._sp16

        section_name, active = _section_at(bar)
        chord_i   = _chord_idx(bar)
        slider    = _section_slider(section_name)
        fm_d      = _fm_depth(bar)
        master_g  = _master_gain(bar)

        bd = self._bar_data.get(bar, {})
        drum_steps = bd.get('drum_steps', {})
        bass_notes = bd.get('bass_notes', [])
        lead_notes = bd.get('lead_notes', [])

        mix_l = np.zeros(spb, dtype=np.float32)
        mix_r = np.zeros(spb, dtype=np.float32)

        # ── Apply kick spill from previous bar ───────────────────────────────
        if self._kick_spill_l is not None:
            n = min(len(self._kick_spill_l), spb)
            mix_l[:n] += self._kick_spill_l[:n]
            mix_r[:n] += self._kick_spill_r[:n]
            if len(self._kick_spill_l) > spb:
                self._kick_spill_l = self._kick_spill_l[spb:]
                self._kick_spill_r = self._kick_spill_r[spb:]
            else:
                self._kick_spill_l = None
                self._kick_spill_r = None

        kick_buf_l = kick_buf_r = None

        # ── KICK ─────────────────────────────────────────────────────────────
        if active['kick']:
            kick_steps = [s for s, kinds in drum_steps.items() if 'kick' in kinds]
            if not kick_steps:
                kick_steps = [0, 4, 8, 12]  # fallback four-on-floor

            kl, kr = self._kit.render_kick(gain=GAIN_KICK)
            new_spill_l = np.zeros(len(kl), dtype=np.float32)
            new_spill_r = np.zeros(len(kl), dtype=np.float32)

            for step in kick_steps:
                offset  = step * sp16
                end_bar = min(offset + len(kl), spb)
                n_in    = end_bar - offset
                mix_l[offset:end_bar] += kl[:n_in]
                mix_r[offset:end_bar] += kr[:n_in]
                if offset + len(kl) > spb:
                    tail = spb - offset
                    new_spill_l[:len(kl) - tail] += kl[tail:]
                    new_spill_r[:len(kl) - tail] += kr[tail:]

            spill_len = int(np.nonzero(new_spill_l)[0][-1] + 1) if np.any(new_spill_l != 0) else 0
            if spill_len > 0:
                new_spill_l = new_spill_l[:spill_len]
                new_spill_r = new_spill_r[:spill_len]
                if self._kick_spill_l is None:
                    self._kick_spill_l = new_spill_l
                    self._kick_spill_r = new_spill_r
                else:
                    pad_len = max(len(self._kick_spill_l), len(new_spill_l))
                    a = np.zeros(pad_len, dtype=np.float32)
                    b = np.zeros(pad_len, dtype=np.float32)
                    a[:len(self._kick_spill_l)] = self._kick_spill_l
                    b[:len(self._kick_spill_r)] = self._kick_spill_r
                    a[:len(new_spill_l)] += new_spill_l
                    b[:len(new_spill_r)] += new_spill_r
                    self._kick_spill_l = a
                    self._kick_spill_r = b

            # Keep a kick buffer for sidechain (first kick hit only)
            kick_buf_l = kl
            kick_buf_r = kr

        # ── HIHAT ────────────────────────────────────────────────────────────
        if active['kick']:
            hihat_steps = [s for s, kinds in drum_steps.items() if 'hihat' in kinds]
            if not hihat_steps:
                hihat_steps = list(range(0, 16, 2))  # fallback offbeat 8ths

            for step in hihat_steps:
                offset = step * sp16
                if offset >= spb:
                    continue
                hl, hr = self._kit.render_hihat(decay_s=0.08, gain=GAIN_HIHAT)
                end_   = min(offset + len(hl), spb)
                n_     = end_ - offset
                mix_l[offset:end_] += hl[:n_]
                mix_r[offset:end_] += hr[:n_]

        # ── CLAP ─────────────────────────────────────────────────────────────
        if active['kick']:
            clap_steps = [s for s, kinds in drum_steps.items() if 'clap' in kinds]
            if not clap_steps:
                clap_steps = [4, 12]  # fallback backbeat

            for step in clap_steps:
                offset = step * sp16
                if offset >= spb:
                    continue
                cl, cr = self._kit.render_clap(gain=GAIN_CLAP)
                end_   = min(offset + len(cl), spb)
                n_     = end_ - offset
                mix_l[offset:end_] += cl[:n_]
                mix_r[offset:end_] += cr[:n_]

        # ── PAD ──────────────────────────────────────────────────────────────
        if active['pad']:
            chord_midi  = chord_to_midi(BAD_APPLE_CHORDS[chord_i], ROOT_MIDI - 24, A_MINOR)
            pad_notes   = chord_midi
            pl, pr = self._pad.render(
                pad_notes, spb,
                bar_offset_samples=0,
                cutoff_slider=0.50,  # SA's slider value at session open
                gain=GAIN_PAD,
                chord_id=chord_i,
                global_offset_samples=bar * spb,
            )
            if kick_buf_l is not None:
                # Build a kick-size reference buffer for sidechain
                ref = np.zeros(spb, dtype=np.float32)
                for step in ([s for s, k in drum_steps.items() if 'kick' in k] or [0]):
                    offset = step * sp16
                    end_   = min(offset + len(kick_buf_l), spb)
                    n_     = end_ - offset
                    ref[offset:end_] += kick_buf_l[:n_]
                pl, pr = self._sc.process(pl, pr, ref)
            mix_l += pl
            mix_r += pr

        # ── BASS ─────────────────────────────────────────────────────────────
        if active['bass']:
            if not bass_notes:
                # Fallback: root on steps 0, 8
                bass_notes = [(0, ROOT_MIDI - 12, 4), (8, ROOT_MIDI - 12, 4)]

            bass_l = np.zeros(spb, dtype=np.float32)
            bass_r = np.zeros(spb, dtype=np.float32)
            for step, note, dur in bass_notes:
                onset  = step * sp16
                if onset >= spb:
                    continue
                n_step = min(dur * sp16, spb - onset)
                bl, br = self._bass.render(note, n_step,
                                           cutoff_slider=0.45,
                                           gain=GAIN_BASS)
                bass_l[onset:onset + n_step] += bl
                bass_r[onset:onset + n_step] += br

            if kick_buf_l is not None:
                ref = np.zeros(spb, dtype=np.float32)
                for step in ([s for s, k in drum_steps.items() if 'kick' in k] or [0]):
                    offset = step * sp16
                    end_   = min(offset + len(kick_buf_l), spb)
                    n_     = end_ - offset
                    ref[offset:end_] += kick_buf_l[:n_]
                bass_l, bass_r = self._sc.process(bass_l, bass_r, ref)
            mix_l += bass_l
            mix_r += bass_r

        # ── LEAD ─────────────────────────────────────────────────────────────
        if active['lead'] and lead_notes:
            lead_l = np.zeros(spb, dtype=np.float32)
            lead_r = np.zeros(spb, dtype=np.float32)
            for step, note, dur in lead_notes:
                onset  = step * sp16
                if onset >= spb:
                    continue
                n_step = min(dur * sp16, spb - onset)
                ll, lr = self._lead.render(
                    [note], n_step,
                    bar_offset_samples=bar * spb + onset,
                    cutoff_slider=max(slider, 0.65),
                    fm_depth=fm_d,
                    gain=GAIN_LEAD,
                    samples_per_bar=spb,
                )
                lead_l[onset:onset + n_step] += ll
                lead_r[onset:onset + n_step] += lr

            if kick_buf_l is not None:
                ref = np.zeros(spb, dtype=np.float32)
                for step in ([s for s, k in drum_steps.items() if 'kick' in k] or [0]):
                    offset = step * sp16
                    end_   = min(offset + len(kick_buf_l), spb)
                    n_     = end_ - offset
                    ref[offset:end_] += kick_buf_l[:n_]
                lead_l, lead_r = self._sc.process(lead_l, lead_r, ref)
            mix_l += lead_l
            mix_r += lead_r

        # ── Master gain + soft clip ───────────────────────────────────────────
        mix_l = np.tanh(mix_l * master_g).astype(np.float32)
        mix_r = np.tanh(mix_r * master_g).astype(np.float32)

        self._bar += 1
        return mix_l, mix_r

    def render_bars(self, n: int) -> tuple:
        all_l, all_r = [], []
        for _ in range(n):
            l, r = self.render_bar()
            all_l.append(l)
            all_r.append(r)
        self._audio_l = all_l
        self._audio_r = all_r
        return np.concatenate(all_l), np.concatenate(all_r)

    def write_wav(self, path: str) -> None:
        if not self._audio_l:
            raise RuntimeError("No audio rendered yet — call render_bars() first.")
        buf_l = np.concatenate(self._audio_l)
        buf_r = np.concatenate(self._audio_r)
        stereo = np.column_stack([buf_l, buf_r])
        pcm = (np.clip(stereo, -1, 1) * 32767).astype(np.int16)
        with wave.open(path, 'wb') as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(self.sr)
            wf.writeframes(pcm.tobytes())


# ---------------------------------------------------------------------------
# Streaming loop
# ---------------------------------------------------------------------------
def _stream_bars(renderer: BadAppleRenderer, n_bars: int, volume: float,
                 wav_path: Optional[str], use_viz: bool) -> tuple:
    """Real-time streaming loop with optional visualiser."""
    try:
        import sounddevice as sd
    except ImportError:
        print("sounddevice not installed: pip install sounddevice")
        print("Falling back to offline render.")
        return renderer.render_bars(n_bars)

    sr   = renderer.sr
    spb  = renderer._spb
    sp16 = renderer._sp16

    all_l: list = []
    all_r: list = []

    wav_file = None
    if wav_path:
        wav_file = wave.open(wav_path, 'wb')
        wav_file.setnchannels(2)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sr)

    audio_queue: queue.Queue = queue.Queue(maxsize=3)
    stop_event = threading.Event()

    def render_thread():
        bar_idx  = renderer._bar
        bars_done = 0
        while not stop_event.is_set():
            if bars_done >= n_bars:
                break
            t0 = time.time()
            bar_l, bar_r = renderer.render_bar()
            if volume != 1.0:
                bar_l = bar_l * volume
                bar_r = bar_r * volume
            render_ms = (time.time() - t0) * 1000
            audio_queue.put((bar_idx, bar_l, bar_r, render_ms))
            bar_idx   += 1
            bars_done += 1
        audio_queue.put(None)

    render_t = threading.Thread(target=render_thread, daemon=True)
    render_t.start()

    stream = sd.OutputStream(samplerate=sr, channels=2, dtype='float32', latency='low')
    stream.start()

    bar_dur_ms = spb / sr * 1000

    # ── Visualiser setup ─────────────────────────────────────────────────────
    viz = None
    _make_bar_info = None
    if use_viz:
        sys.path.insert(0, str(REPO_ROOT / 'tools'))
        from visualiser import Visualiser, make_bar_info as _mbi
        _make_bar_info = _mbi

        viz = Visualiser(renderer.song, n_bars)
        viz.start()
        # Auto-start the Bad Apple ASCII video (index 0 in the auto-discovered playlist)
        if viz._av_playlist:
            viz._av_playlist_idx = 0
            viz._ascii_video_start_time = time.monotonic()
    else:
        print(f"Streaming {n_bars} bars — Ctrl-C to stop.")

    try:
        while True:
            item = audio_queue.get()
            if item is None:
                break
            bar_idx, bar_l, bar_r, render_ms = item

            bd         = renderer._bar_data.get(bar_idx, {})
            drum_steps = bd.get('drum_steps', {})
            bass_notes = bd.get('bass_notes', [])
            lead_notes = bd.get('lead_notes', [])

            kick_set  = {s for s, k in drum_steps.items() if 'kick' in k}
            hihat_set = {s for s, k in drum_steps.items() if 'hihat' in k}
            clap_set  = {s for s, k in drum_steps.items() if 'clap' in k}
            bass_set  = {s for s, n, d in bass_notes}
            lead_set  = {s for s, n, d in lead_notes}

            _, active = _section_at(bar_idx)

            if viz:
                viz.update(_make_bar_info(bar_idx, renderer.song, render_ms, bar_dur_ms))
                renderer.ca_state = {
                    'density':        viz.ca_density(),
                    'voicing_offset': viz.ca_voicing_offset(),
                }
                for step in range(16):
                    onset = step * sp16
                    end   = onset + sp16
                    chunk = np.column_stack([bar_l[onset:end], bar_r[onset:end]])
                    stream.write(chunk)
                    hit_map = {
                        'kick':  active['kick']  and step in kick_set,
                        'hihat': active['kick']  and step in hihat_set,
                        'clap':  active['kick']  and step in clap_set,
                        'pad':   active['pad']   and step == 0,
                        'bass':  active['bass']  and step in bass_set,
                        'lead':  active['lead']  and step in lead_set,
                        'pulse': False,
                    }
                    viz.tick(hit_map)
            else:
                stereo = np.column_stack([bar_l, bar_r])
                stream.write(stereo)
                print(f"  bar {bar_idx + 1:4d}/{n_bars}  "
                      f"render={render_ms:.0f}ms  "
                      f"budget={bar_dur_ms:.0f}ms  "
                      f"headroom={bar_dur_ms - render_ms:.0f}ms",
                      end='\r')

            all_l.append(bar_l)
            all_r.append(bar_r)
            if wav_file is not None:
                wav_stereo = np.column_stack([bar_l, bar_r])
                pcm = (np.clip(wav_stereo, -1, 1) * 32767).astype(np.int16)
                wav_file.writeframes(pcm.tobytes())

    except KeyboardInterrupt:
        if viz:
            viz.stop()
        else:
            print(f"\nStopped at bar {len(all_l)}.")
        stop_event.set()
        while not audio_queue.empty():
            try:
                audio_queue.get_nowait()
            except Exception:
                break
    finally:
        stop_event.set()
        render_t.join(timeout=2.0)
        stream.stop()
        stream.close()
        if viz:
            viz.stop()
        if wav_file is not None:
            wav_file.close()
            print(f"\nWAV saved → {wav_path}")

    print()
    if not all_l:
        return np.zeros(0, dtype=np.float32), np.zeros(0, dtype=np.float32)

    buf_l = np.concatenate(all_l)
    buf_r = np.concatenate(all_r)
    renderer._audio_l = all_l
    renderer._audio_r = all_r
    return buf_l, buf_r


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main() -> None:
    default_midi = str(REPO_ROOT / 'research/reference_audio/midi/bad_apple.mid')
    default_wav  = str(REPO_ROOT / 'bad_apple.wav')

    p = argparse.ArgumentParser(
        description='Bad Apple!! trance cover — switch-angel synth stack')
    p.add_argument('--midi',   default=default_midi,
                   help='Path to the Bad Apple MIDI file')
    p.add_argument('--bpm',    type=float, default=BPM,
                   help=f'Tempo in BPM (default: {BPM})')
    p.add_argument('--wav',    default=None,
                   help='Write output to WAV file (default: bad_apple.wav when not --stream)')
    p.add_argument('--stream', action='store_true',
                   help='Play in real time via sounddevice')
    p.add_argument('--viz',    action='store_true',
                   help='Show terminal visualiser with Bad Apple ASCII video')
    p.add_argument('--bars',   type=int, default=None,
                   help='Render only the first N bars (default: all)')
    p.add_argument('--volume', type=float, default=1.0,
                   help='Output volume multiplier (default: 1.0)')
    args = p.parse_args()

    midi_path = Path(args.midi)
    if not midi_path.exists():
        print(f"MIDI file not found: {midi_path}")
        print("Run:  python tools/fetch_bad_apple_midi.py")
        sys.exit(1)

    print(f"Loading MIDI: {midi_path}")
    renderer = BadAppleRenderer(str(midi_path), bpm=args.bpm, sr=SR)
    n_bars   = args.bars if args.bars is not None else renderer._total_bars
    print(f"Song: {n_bars} bars @ {args.bpm:.0f} BPM  "
          f"({n_bars * 4 * 60 / args.bpm:.0f}s)")

    if args.stream:
        wav_out = args.wav  # None = no file
        _stream_bars(renderer, n_bars, args.volume, wav_out, args.viz)
    else:
        wav_out = args.wav if args.wav else default_wav
        print(f"Rendering {n_bars} bars offline…")
        t0 = time.time()
        renderer.render_bars(n_bars)
        elapsed = time.time() - t0
        print(f"Rendered in {elapsed:.1f}s  ({n_bars * 4 * 60 / args.bpm / elapsed:.1f}× realtime)")
        renderer.write_wav(wav_out)
        print(f"WAV saved → {wav_out}")


if __name__ == '__main__':
    main()
