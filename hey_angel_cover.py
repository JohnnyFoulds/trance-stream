#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Hey Angel… — cover using switch-angel synthesisers.

Arrangement derived from research/analysis/hey_angel_analysis.md.
All parameters are hardcoded from measurement — no MIDI file, no samples.

Strudel equivalent (for reference):
  bass:    "g1@4 [f2@2 ~>g1@2]" # quarter G1, eighth F2, eighth portamento back
  melody:  c4 → f#3 chromatic glide, 15 sem/sec, repeating per bar
  pluck:   e5 sustained (enters bar 2)
  kick:    "x . . . . . . . x . . . . . . ."  (half-time, steps 0+8)

Usage:
    python hey_angel_cover.py --stream          # real-time playback
    python hey_angel_cover.py --wav out.wav     # render to file
    python hey_angel_cover.py --bars 8 --stream # first 8 bars only
"""
from __future__ import annotations

import argparse
import queue
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).parent
sys.path.insert(0, str(REPO_ROOT))

BPM  = 138.0
SR   = 44100
ROOT = 43          # G1 = MIDI 43 = 49 Hz

# ---------------------------------------------------------------------------
# Duck-typed song object — satisfies make_bar_info() and Visualiser()
# ---------------------------------------------------------------------------
from dataclasses import dataclass, field

@dataclass
class HeyAngelSong:
    bpm:           float = BPM
    sr:            int   = SR
    seed:          str   = 'hey_angel'
    mood:          str   = 'uplifting'
    root_midi:     int   = ROOT
    # G natural minor
    scale:         list  = field(default_factory=lambda: [0, 2, 3, 5, 7, 8, 10])
    # Static G minor tonic chord (root + fifth)
    chord_prog:    list  = field(default_factory=lambda: [[0, 4]])
    chord_weights: list  = field(default_factory=lambda: [1])
    chord_prog_b:  list  = None
    root_shift:    int   = 0
    filter_pb_bar: int   = 9999
    stage_bars:    dict  = field(default_factory=lambda: {
        'kick_on': 3, 'pad_root_on': 9999, 'bass_on': 2,
        'lead_root_on': 0, 'lead_melody_on': 0, 'pad_chord_on': 9999,
        'lead_voicing_on': 9999, 'clap_on': 9999, 'fm_on': 9999,
        'pulse_on': 9999, 'hihat_on': 3, 'kick_syncopated': 9999,
    })
    hihat_pattern: str   = 'full'
    total_bars:    int   = 128


# ---------------------------------------------------------------------------
# Musical constants — all measured from hey_angel_analysis.md
# ---------------------------------------------------------------------------

# Bass pattern per bar — repeats twice (half-time feel, 2× per bar)
# Each entry: (step_16th, midi_note, target_midi_for_porta, n_sixteenths)
# target_midi=None means no portamento (fixed pitch)
BASS_PATTERN = [
    ( 0, 43, None, 4),   # G1 quarter note
    ( 4, 53, None, 2),   # F2 eighth
    ( 6, 53,   43, 2),   # F2 → G1 portamento sweep (eighth)
    ( 8, 43, None, 4),   # G1 quarter note (second half-note)
    (12, 53, None, 2),   # F2 eighth
    (14, 53,   43, 2),   # F2 → G1 portamento sweep
]

# Melody: C4 → F#3 chromatic glide (6 semitones)
# MIDI stem analysis (research/analysis/hey_angel_analysis.md §8):
# "chromatic descend C4→F#3 (t=0–1.2s)" → 5 semitones/sec, NOT 15.
# Fills ~69% of bar before resting; avoids dead silence per beat.
MELODY_START  = 60   # C4
MELODY_END    = 54   # F#3
MELODY_GLIDE_S = 1.2  # seconds for the 6-semitone descent (from MIDI stem)

# High pluck: E5, sustained the whole bar, filter-burst on attack
PLUCK_NOTE = 76      # E5 = 660 Hz

# Kick: half-time (steps 0 and 8 only)
KICK_STEPS = [0, 8]

# Sidechain: -11.1 dB trough (research §5)
SIDECHAIN_DEPTH = 0.721
SIDECHAIN_ATTACK_S = 0.16

# ---------------------------------------------------------------------------
# Arrangement sections
# (start_bar, end_bar, kick, bass, melody, pluck, hihat)
# ---------------------------------------------------------------------------
# t=0.0–2.5s  (~bars 0-1): intro arp — melody only
# t=2.5–3.1s  (~bar 1-2):  suspension — bass drone G1 only
# t=3.1–4.0s  (~bar 2):    high pluck enters
# t=4.0s+     (~bar 2+):   full groove
SECTIONS = [
    # start  end  kick   bass   melody pluck  hihat
    (0,    2,  False, False, True,  False, False),  # intro: melody only
    (2,    3,  False, True,  False, True,  False),  # suspension+pluck
    (3,    99, True,  True,  True,  True,  True ),  # full groove
]

def _section_at(bar: int) -> dict:
    for start, end, kick, bass, melody, pluck, hihat in SECTIONS:
        if start <= bar < end:
            return dict(kick=kick, bass=bass, melody=melody,
                        pluck=pluck, hihat=hihat)
    return dict(kick=True, bass=True, melody=True, pluck=True, hihat=True)


# ---------------------------------------------------------------------------
# Renderer
# ---------------------------------------------------------------------------
class HeyAngelRenderer:
    def __init__(self, sr: int = SR, n_bars: int = 20):
        from instruments.drums import DrumKit
        from instruments.bass  import AcidBass
        from instruments.pluck import HighPluck
        from synth.effects     import Sidechain, SchroederReverb
        from song.theory       import GAIN_KICK, GAIN_BASS, GAIN_LEAD, GAIN_HIHAT

        self.sr    = sr
        self._bpm  = BPM
        self._spb  = int(sr * 4 * 60 / BPM)   # samples per bar
        self._sp16 = self._spb // 16            # samples per sixteenth
        self._bar  = 0
        self.n_bars = n_bars

        from instruments.smooth_lead import SmoothLead

        self._kit   = DrumKit(seed=42, sr=sr, kick_decay_s=0.25,
                               kick_pitch_floor=50.0)
        self._bass  = AcidBass(sr=sr)
        # Single filtered saw, no gate, no delay — matches Hey Angel's clean glide
        self._lead  = SmoothLead(cutoff_hz=900.0, gain=0.55, sr=sr)
        self._pluck = HighPluck(sr=sr)
        self._sc    = Sidechain(depth=SIDECHAIN_DEPTH,
                                attack_s=SIDECHAIN_ATTACK_S, sr=sr)
        self._reverb = SchroederReverb(room_size=0.75, wet=0.40, sr=sr)

        self._gain_kick  = GAIN_KICK * 0.7
        self._gain_bass  = GAIN_BASS * 0.20  # sub-bass — warm foundation, not dominant
        self._gain_lead  = 0.40              # lower — reverb will fill the space
        self._gain_hihat = GAIN_HIHAT * 1.0
        self._gain_pluck = 0.14

        self._kick_spill_l = None
        self._kick_spill_r = None

        self._audio_l: list = []
        self._audio_r: list = []

        # Duck-typed song object for the visualiser
        self.song = HeyAngelSong(bpm=BPM, sr=sr)
        self.ca_state: dict = {}

    # ── per-bar render ───────────────────────────────────────────────────────

    def render_bar(self) -> tuple:
        bar  = self._bar
        spb  = self._spb
        sp16 = self._sp16
        active = _section_at(bar)

        mix_l = np.zeros(spb, dtype=np.float32)
        mix_r = np.zeros(spb, dtype=np.float32)

        # Apply kick spill from previous bar
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

        kick_ref = None

        # ── Kick (half-time) ─────────────────────────────────────────────────
        if active['kick']:
            kl, kr = self._kit.render_kick(gain=self._gain_kick)
            new_spill_l = np.zeros(len(kl), dtype=np.float32)
            new_spill_r = np.zeros(len(kl), dtype=np.float32)
            for step in KICK_STEPS:
                offset = step * sp16
                end_bar = min(offset + len(kl), spb)
                n_in = end_bar - offset
                mix_l[offset:end_bar] += kl[:n_in]
                mix_r[offset:end_bar] += kr[:n_in]
                if offset + len(kl) > spb:
                    tail = spb - offset
                    new_spill_l[:len(kl) - tail] += kl[tail:]
                    new_spill_r[:len(kl) - tail] += kr[tail:]
            spill_len = (int(np.nonzero(new_spill_l)[0][-1]) + 1
                         if np.any(new_spill_l != 0) else 0)
            if spill_len > 0:
                self._kick_spill_l = new_spill_l[:spill_len]
                self._kick_spill_r = new_spill_r[:spill_len]
            kick_ref = mix_l.copy()

        # ── Hi-hat (simple 8th-note pattern) ─────────────────────────────────
        if active['hihat']:
            hl, hr = self._kit.render_hihat(decay_s=0.06, gain=self._gain_hihat)
            for step in range(0, 16, 2):   # every 8th note
                onset = step * sp16
                end   = min(onset + len(hl), spb)
                n     = end - onset
                mix_l[onset:end] += hl[:n]
                mix_r[onset:end] += hr[:n]

        # ── Bass: G1(quarter) → F2(eighth) → portamento F2→G1(eighth) ×2 ────
        if active['bass']:
            bass_l = np.zeros(spb, dtype=np.float32)
            bass_r = np.zeros(spb, dtype=np.float32)
            for step, note, target, dur in BASS_PATTERN:
                onset = step * sp16
                n_smp = min(dur * sp16, spb - onset)
                if n_smp <= 0:
                    continue
                if target is not None:
                    # Portamento sweep — no acid filter, just sweep
                    bl, br = self._bass.render(
                        note, n_smp, gain=self._gain_bass,
                        portamento_s=float(n_smp) / self.sr,
                        target_midi=target,
                        vca_tau=2.0, bypass_acidenv=True)
                else:
                    # Held drone or F2 hit — sustained, warm sub-bass
                    bl, br = self._bass.render(
                        note, n_smp, gain=self._gain_bass,
                        cutoff_slider=0.30,   # ~400Hz — keeps it sub-warm, not buzzy
                        vca_tau=2.0, bypass_acidenv=True)
                bass_l[onset:onset + n_smp] += bl
                bass_r[onset:onset + n_smp] += br
            if kick_ref is not None:
                bass_l, bass_r = self._sc.process(bass_l, bass_r, kick_ref)
            mix_l += bass_l
            mix_r += bass_r

        # ── Melody: C4 → F#3 chromatic glide, once per bar, then rest ──────
        if active['melody']:
            melody_l = np.zeros(spb, dtype=np.float32)
            melody_r = np.zeros(spb, dtype=np.float32)
            # MIDI stem: descend t=0–1.2s, bar=1.74s → 0.54s natural rest at end
            n_glide = min(int(MELODY_GLIDE_S * self.sr), spb)
            ml, mr = self._lead.render(
                MELODY_START, n_glide,
                target_midi=MELODY_END,
                gain=self._gain_lead)
            melody_l[:n_glide] = ml
            melody_r[:n_glide] = mr
            if kick_ref is not None:
                melody_l, melody_r = self._sc.process(melody_l, melody_r, kick_ref)
            mix_l += melody_l
            mix_r += melody_r

        # ── High pluck: E5, whole bar, filter-burst brightness ────────────────
        if active['pluck']:
            pl, pr = self._pluck.render(PLUCK_NOTE, spb, gain=self._gain_pluck)
            if kick_ref is not None:
                pl, pr = self._sc.process(pl, pr, kick_ref)
            mix_l += pl
            mix_r += pr

        # ── Master: reverb → soft clip ────────────────────────────────────────
        mix_l, mix_r = self._reverb.process(mix_l, mix_r)
        mix_l = np.tanh(mix_l).astype(np.float32)
        mix_r = np.tanh(mix_r).astype(np.float32)

        self._bar += 1
        return mix_l, mix_r

    def render_bars(self, n: int) -> tuple:
        all_l, all_r = [], []
        for _ in range(n):
            l, r = self.render_bar()
            all_l.append(l); all_r.append(r)
        self._audio_l = all_l
        self._audio_r = all_r
        return np.concatenate(all_l), np.concatenate(all_r)

    def write_wav(self, path: str) -> None:
        buf_l = np.concatenate(self._audio_l)
        buf_r = np.concatenate(self._audio_r)
        pcm = (np.clip(np.column_stack([buf_l, buf_r]), -1, 1) * 32767).astype(np.int16)
        with wave.open(path, 'wb') as wf:
            wf.setnchannels(2); wf.setsampwidth(2); wf.setframerate(self.sr)
            wf.writeframes(pcm.tobytes())


# ---------------------------------------------------------------------------
# Streaming
# ---------------------------------------------------------------------------
def _stream(renderer: HeyAngelRenderer, n_bars: int, volume: float,
            wav_path: str | None, use_viz: bool = False) -> None:
    try:
        import sounddevice as sd
    except ImportError:
        print("sounddevice not installed — falling back to offline render.")
        renderer.render_bars(n_bars)
        if wav_path:
            renderer.write_wav(wav_path)
        return

    spb  = renderer._spb
    sp16 = renderer._sp16
    sr   = renderer.sr
    bar_dur_ms = spb / sr * 1000

    q = queue.Queue(maxsize=3)
    stop = threading.Event()

    def _render():
        for _ in range(n_bars):
            if stop.is_set():
                break
            t0 = time.time()
            l, r = renderer.render_bar()
            ms = (time.time() - t0) * 1000
            q.put((l * volume, r * volume, ms))
        q.put(None)

    threading.Thread(target=_render, daemon=True).start()

    wav_file = None
    if wav_path:
        wav_file = wave.open(wav_path, 'wb')
        wav_file.setnchannels(2); wav_file.setsampwidth(2); wav_file.setframerate(sr)

    stream = sd.OutputStream(samplerate=sr, channels=2, dtype='float32', latency='low')
    stream.start()

    # ── Visualiser setup ──────────────────────────────────────────────────────
    viz = None
    _make_bar_info = None
    if use_viz:
        from tools.visualiser import Visualiser, make_bar_info as _mbi
        _make_bar_info = _mbi
        viz = Visualiser(renderer.song, n_bars)
        viz.start()
        if viz._av_playlist:
            viz._av_playlist_idx = 0
            viz._ascii_video_start_time = time.monotonic()
    else:
        print(f"Streaming {n_bars} bars — Ctrl-C to stop.")

    bar = 0
    try:
        while True:
            item = q.get()
            if item is None:
                break
            l, r, ms = item
            active = _section_at(bar)

            if viz:
                viz.update(_make_bar_info(bar, renderer.song, ms, bar_dur_ms))
                renderer.ca_state = {
                    'density':        viz.ca_density(),
                    'voicing_offset': viz.ca_voicing_offset(),
                }
                # Step-by-step playback so viz.tick() stays in sync
                for step in range(16):
                    onset = step * sp16
                    end   = onset + sp16
                    chunk = np.column_stack([l[onset:end], r[onset:end]])
                    stream.write(chunk)
                    hit_map = {
                        'kick':  active['kick']   and step in KICK_STEPS,
                        'hihat': active['hihat']  and step % 2 == 0,
                        'clap':  False,
                        'pad':   False,
                        'bass':  active['bass']   and any(s == step for s, *_ in BASS_PATTERN),
                        'lead':  active['melody'] and step == 0,
                        'pulse': active['pluck']  and step == 0,
                    }
                    viz.tick(hit_map)
            else:
                section = _section_at(bar)
                active_str = '+'.join(k for k, v in section.items() if v)
                print(f"  bar {bar+1:3d}/{n_bars}  [{active_str:<30}]  "
                      f"render={ms:.0f}ms  budget={bar_dur_ms:.0f}ms", end='\r')
                stream.write(np.column_stack([l, r]))

            if wav_file:
                pcm = (np.clip(np.column_stack([l, r]), -1, 1) * 32767).astype(np.int16)
                wav_file.writeframes(pcm.tobytes())
            bar += 1
    except KeyboardInterrupt:
        print(f"\nStopped at bar {bar}.")
        stop.set()
    finally:
        stop.set()
        if viz:
            viz.stop()
        stream.stop(); stream.close()
        if wav_file:
            wav_file.close()
            print(f"\nWAV saved → {wav_path}")
    print()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--stream', action='store_true', help='Real-time playback')
    p.add_argument('--viz',    action='store_true', help='Terminal CA visualiser')
    p.add_argument('--wav',    default=None,
                   help='Write WAV (default: hey_angel.wav when not streaming)')
    p.add_argument('--bars',   type=int, default=20,
                   help='Number of bars to render (default: 20 ≈ 35s)')
    p.add_argument('--volume', type=float, default=1.0)
    args = p.parse_args()

    dur_s = args.bars * 4 * 60 / BPM
    print(f"Hey Angel cover  {args.bars} bars @ {BPM:.0f} BPM  ({dur_s:.1f}s)")
    print(f"  G1 bass · C4→F#3 glide · E5 pluck · half-time kick · sidechain depth={SIDECHAIN_DEPTH}")

    renderer = HeyAngelRenderer(sr=SR, n_bars=args.bars)

    if args.stream:
        _stream(renderer, args.bars, args.volume, args.wav, use_viz=args.viz)
    else:
        wav_out = args.wav or 'hey_angel.wav'
        t0 = time.time()
        print(f"Rendering {args.bars} bars offline...")
        renderer.render_bars(args.bars)
        elapsed = time.time() - t0
        renderer.write_wav(wav_out)
        print(f"  {elapsed:.1f}s render  ({dur_s / elapsed:.1f}× realtime)")
        print(f"WAV saved → {wav_out}")


if __name__ == '__main__':
    main()
