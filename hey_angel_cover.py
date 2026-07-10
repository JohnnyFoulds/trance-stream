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

BPM  = 140.0534
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

# Bass pattern per bar — analysis §1: "3+5 sixteenth subdivision"
# G1 hit at step 0, F2 hit at step 3, fast portamento F2→G1 at step 4,
# then G1 continues through step 7 (no gap before next half-note).
# Each entry: (step_16th, midi_note, target_midi_for_porta, n_sixteenths)
BASS_PATTERN = [
    ( 0, 43, None, 3),   # G1: steps 0-2 (3 sixteenths = 326ms)
    ( 3, 53, None, 1),   # F2: step 3 (1 sixteenth = 109ms)
    ( 4, 53,   43, 1),   # F2→G1 portamento: step 4 (fast 109ms snap)
    ( 5, 43, None, 3),   # G1 continue: steps 5-7 (fills to step 8)
    ( 8, 43, None, 3),   # G1: steps 8-10
    (11, 53, None, 1),   # F2: step 11
    (12, 53,   43, 1),   # F2→G1 portamento: step 12
    (13, 43, None, 3),   # G1 continue: steps 13-15
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
# Reference (hey_angel_trimmed.wav) starts at t=6s of original — well into the groove.
# That means it begins with full arrangement already running.
# The analysis §3 arrangement is for the full track; when trimmed, we're at t=4.9s+
# which is "GROOVE: F2 bass, G1 drone, rolling arp, sidechain pump active".
SECTIONS = [
    # start  end  kick   bass   melody pluck  hihat
    (0,    99, True,  True,  True,  True,  True ),  # full groove from bar 0
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
        self._reverb = SchroederReverb(room_size=0.45, wet=0.15, sr=sr)

        self._gain_kick  = GAIN_KICK * 0.40
        self._gain_bass  = GAIN_BASS * 0.55  # F2 bass needs to be audible in chroma
        self._gain_lead  = 0.55              # melody is the dominant melodic element
        self._gain_hihat = GAIN_HIHAT * 0.5  # hihats subtle in Hey Angel
        self._gain_pluck = 0.16

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
        kick_only = np.zeros(spb, dtype=np.float32)  # sidechain key — kick only

        # 4-bar phrase structure:
        # bar%4==2: energy dips in last ~200ms (pre-drop, before phrase boundary)
        # bar%4==3: no bass/kick at step 0 (the actual phrase boundary rest)
        is_pre_phrase = (bar % 4 == 2)
        is_phrase_boundary = (bar % 4 == 3)

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
                kick_only[offset:end_bar] += kl[:n_in]
                if offset + len(kl) > spb:
                    tail = spb - offset
                    new_spill_l[:len(kl) - tail] += kl[tail:]
                    new_spill_r[:len(kl) - tail] += kr[tail:]
            spill_len = (int(np.nonzero(new_spill_l)[0][-1]) + 1
                         if np.any(new_spill_l != 0) else 0)
            if spill_len > 0:
                self._kick_spill_l = new_spill_l[:spill_len]
                self._kick_spill_r = new_spill_r[:spill_len]
            # Sidechain triggered by kick only (not full mix — bass/hihat must not re-trigger)
            kick_ref = kick_only

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
        bass_l = np.zeros(spb, dtype=np.float32)
        bass_r = np.zeros(spb, dtype=np.float32)
        if active['bass']:
            for step, note, target, dur in BASS_PATTERN:
                # Phrase boundary: bass skips first half-note (steps 0-7).
                # Sub-bass RMS at step0 ≈ 0.01 on phrase boundary bars (kick only, no bass).
                if is_phrase_boundary and step < 8:
                    continue
                onset = step * sp16
                n_smp = min(dur * sp16, spb - onset)
                if n_smp <= 0:
                    continue
                if target is not None:
                    bl, br = self._bass.render(
                        note, n_smp, gain=self._gain_bass,
                        portamento_s=float(n_smp) / self.sr,
                        target_midi=target,
                        vca_tau=2.0, bypass_acidenv=True)
                else:
                    # Narrow LPF on G1 drone to suppress G/G# harmonics in chroma.
                    # rlpf_to_hz(0.25) = 81Hz — passes G1=49Hz, kills G2=98Hz+
                    cutoff = 0.26 if note == 43 else 0.45
                    bl, br = self._bass.render(
                        note, n_smp, gain=self._gain_bass,
                        cutoff_slider=cutoff,
                        vca_tau=2.0, bypass_acidenv=True)
                bass_l[onset:onset + n_smp] += bl
                bass_r[onset:onset + n_smp] += br

        # ── Melody ────────────────────────────────────────────────────────────
        # Analysis §8 MIDI: t=0–1.2s: chromatic glide C4→F#3;
        # t=5.5–18s: F3/F2 sustained note (the dominant melody in trimmed reference).
        # From bar 4 onward (original t≈8s) we should hold at F3 continuously.
        melody_l = np.zeros(spb, dtype=np.float32)
        melody_r = np.zeros(spb, dtype=np.float32)
        if active['melody']:
            # Analysis §8: trimmed reference starts at original t=6s, where the
            # MIDI shows "F3/F2 sustained note (t=5.5–18s)". The dominant melody
            # through the whole reference clip is F3 held, not the C4→F#3 glide.
            # We still glide once at bar 0 to establish the gesture, then sustain.
            # Reference (trimmed from t=6s) is in the "F3/F2 sustained" section.
            # Every 4 bars, re-state the C4→F#3 glide then return to F3 sustain.
            if bar % 4 == 0:
                n_glide = min(int(MELODY_GLIDE_S * self.sr), spb)
                ml, mr = self._lead.render(
                    MELODY_START, n_glide,
                    target_midi=MELODY_END,
                    gain=self._gain_lead)
                melody_l[:n_glide] = ml
                melody_r[:n_glide] = mr
                n_sustain = spb - n_glide
                if n_sustain > 0:
                    sl, sr_ = self._lead.render(
                        65, n_sustain,  # transition to F3
                        gain=self._gain_lead)
                    melody_l[n_glide:] = sl
                    melody_r[n_glide:] = sr_
            else:
                # Sustained F3 (MIDI 65) and F#3 (MIDI 66) together — reference
                # shows equal F and F# chroma prominence throughout the clip,
                # consistent with two simultaneous voices or a slow tremolo.
                sl_f3,  _ = self._lead.render(65, spb, gain=self._gain_lead * 0.7)
                sl_fs3, _ = self._lead.render(66, spb, gain=self._gain_lead * 0.7)
                raw_melody = sl_f3 + sl_fs3
                melody_l[:] = raw_melody
                melody_r[:] = raw_melody

        # ── High pluck: E5, whole bar; also sustain D#4 for harmonic pad texture ─
        pluck_l = np.zeros(spb, dtype=np.float32)
        pluck_r = np.zeros(spb, dtype=np.float32)
        if active['pluck']:
            pl_e5, pr_e5 = self._pluck.render(PLUCK_NOTE, spb, gain=self._gain_pluck)
            # D#4/Eb4 (MIDI 63) — atmospheric pad from "other" stem; injects D# chroma
            pl_eb4, pr_eb4 = self._pluck.render(63, spb, gain=self._gain_pluck * 0.5)
            pluck_l = pl_e5 + pl_eb4
            pluck_r = pr_e5 + pr_eb4

        # Pre-phrase fade: at bar%4==2 (bar before a phrase boundary), reference energy
        # drops ~200ms before bar end (ref RMS falls from 0.22 to 0.13 at t=697ms).
        # Fade melody+bass+pluck from 1.0 to 0.35 in the last 220ms to match.
        if is_pre_phrase:
            fade_start = max(0, spb - int(0.22 * self.sr))
            fade_len = spb - fade_start
            if fade_len > 0:
                fade_env = np.ones(spb, dtype=np.float32)
                fade_env[fade_start:] = np.linspace(1.0, 0.35, fade_len, dtype=np.float32)
                melody_l *= fade_env; melody_r *= fade_env
                pluck_l  *= fade_env; pluck_r  *= fade_env
                bass_l   *= fade_env; bass_r   *= fade_env

        # ── Sidechain: apply once to the combined instrumental bus ───────────
        # Apply sidechain to sum of all pitched layers before mixing with kick.
        # One pass preserves the single pump per kick hit; multiple passes would
        # triple-apply the gain reduction and distort the pump shape.
        instr_l = bass_l + melody_l + pluck_l
        instr_r = bass_r + melody_r + pluck_r
        if kick_ref is not None:
            instr_l, instr_r = self._sc.process(instr_l, instr_r, kick_ref)

        mix_l += instr_l
        mix_r += instr_r

        # Phrase-boundary fade-in: at bar%4==3, the kick+bass are skipped at step0
        # so the reference starts quiet (~0.14 vs 0.22 normal). Our melody+pluck
        # keep the gen at ~0.20. Apply an exponential rise from 0.60 over 200ms
        # to match the reference transition shape after the phrase boundary.
        if is_phrase_boundary:
            t_s = np.arange(spb, dtype=np.float32) / self.sr
            tau = 0.15  # 150ms rise
            env_pb = (1.0 - 0.35 * np.exp(-t_s / tau)).astype(np.float32)
            mix_l *= env_pb; mix_r *= env_pb

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

    def render_bars_aligned(self, n: int, phase_offset_ms: float = 70.0) -> tuple:
        """Render n bars with a phase offset to align kick to reference grid.

        The reference hey_angel_trimmed.wav starts at t=6s of original, so its
        first kick lands at t=70ms (not t=0ms). Prepend that many ms of the
        tail of a "virtual" bar-0 to produce the correct phase alignment.
        """
        offset_samples = int(phase_offset_ms / 1000 * self.sr)
        # Render n+1 bars, then slice out [offset_samples : offset_samples + n*spb]
        all_l, all_r = [], []
        for _ in range(n + 1):
            l, r = self.render_bar()
            all_l.append(l); all_r.append(r)
        full_l = np.concatenate(all_l)
        full_r = np.concatenate(all_r)
        target_len = n * self._spb
        self._audio_l = [full_l[offset_samples:offset_samples + target_len]]
        self._audio_r = [full_r[offset_samples:offset_samples + target_len]]
        return self._audio_l[0], self._audio_r[0]

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
    p.add_argument('--bars',   type=int, default=15,
                   help='Number of bars to render (default: 15 ≈ 26s, matches reference length)')
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
