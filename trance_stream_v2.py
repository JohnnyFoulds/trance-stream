# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Procedural trance generator v2 — rebuilt from Switch Angel's actual Strudel code.

All synthesis parameters and patterns cited from:
  research/analysis/switch_angel_vocabulary.md
  research/extracted/*/summary.md  (OCR'd from her YouTube live-coding sessions)

Key architectural differences from trance_stream.py (v1):
  Kick:   beat(0,4,8,11,14,16) syncopated pattern, not simple four-on-floor
  Hihat:  white!16 every step, hpf(1200), triangle-LFO decay 0.05–0.12s [absent in v1]
  Clap:   backbeat steps 4,12 [absent in v1]
  Pad:    retrigger every 16th (seg 16), acidenv, smooth trancegate(1.5,45,1), open filter
  Lead:   notearp rhythmic pattern, acidenv, FM brown noise, heavy delay(0.7,0.8)
  Pulse:  pulse!16 FM-time-modulated texture layer [absent in v1]
  Filter: both voices open (~9–12 kHz base); lpenv sweeps on trigger [v1 had closed static LPF]
  Gate:   smooth cosine envelope cycling at 1.5x bar rate [v1 had binary LFSR on/off]
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import math
import os
import random
import sys
import wave as _wave
import struct as _struct
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import sounddevice as sd
from midiutil import MIDIFile

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description="Procedural Trance Stream v2")
parser.add_argument("-b", "--bpm", type=int, default=140)
parser.add_argument("-s", "--seed", type=str, default="center")
parser.add_argument("-v", "--volume", type=float, default=0.90)
parser.add_argument("-o", "--out_midi", type=str, default=None)
parser.add_argument("--bars", type=int, default=0)
parser.add_argument("--wav", type=str, default=None)
parser.add_argument("--mood", type=str, default="uplifting",
                    choices=["uplifting", "dark", "acid", "progressive", "dreamy"])
args = parser.parse_args()

# ---------------------------------------------------------------------------
# Song configuration — deterministic from seed + mood
# ---------------------------------------------------------------------------

_NOTEARP_VARIANTS: list[list[int]] = [
    # Original — hits on beats 1,2,3,4 with leading eighth
    [0, -1, -1, -1,  1,  0,  1, -1,  0, -1,  1,  0,  1, -1, -1, -1],
    # More active — 6 hits per bar
    [0, -1,  1, -1,  0,  1, -1,  1,  0, -1,  0, -1,  1,  0, -1,  1],
    # Sparse — 4 hits, mostly on downbeats
    [0, -1, -1, -1, -1, -1,  1, -1,  0, -1, -1, -1,  1, -1, -1, -1],
    # Syncopated — kicks on the offbeats
    [-1,  0, -1,  1, -1,  0, -1, -1, -1,  1, -1,  0, -1, -1,  1, -1],
    # Dense triplet feel
    [0,  1, -1,  0,  1, -1,  0,  1, -1,  0, -1,  1,  0,  1, -1, -1],
]

_SCALE_OFFSETS: dict[str, list[int]] = {
    "uplifting":   [0, 2, 3, 5, 7, 8, 10],   # natural minor
    "dark":        [0, 2, 3, 5, 7, 8, 10],   # natural minor, darker chord choices
    "acid":        [0, 2, 3, 5, 7, 8, 10],   # natural minor
    "progressive": [0, 2, 4, 5, 7, 9, 11],   # major — brighter
    "dreamy":      [0, 2, 3, 5, 7, 9, 10],   # dorian — bittersweet
}

# Chord progressions as list of [root_deg, third_deg, fifth_deg] triples
_CHORD_PROGS: dict[str, list[list[int]]] = {
    "uplifting":   [[0, 2, 4], [5, 0, 2], [3, 5, 0], [4, 6, 1]],  # i → iv → III → v
    "dark":        [[0, 2, 4], [5, 0, 2], [0, 2, 4], [6, 1, 3]],  # i → iv → i → viidim
    "acid":        [[0, 2, 4], [3, 5, 0], [5, 0, 2], [3, 5, 0]],  # i → III → iv → III
    "progressive": [[0, 2, 4], [3, 5, 0], [4, 6, 1], [1, 3, 5]],  # I → IV → V → ii
    "dreamy":      [[0, 2, 4], [5, 0, 2], [1, 3, 5], [3, 5, 0]],  # i → iv → ii → III
}

_MOOD_NAMES: dict[str, str] = {
    "uplifting":   "i-iv-III-v",
    "dark":        "i-iv-i-viidim",
    "acid":        "i-III-iv-III",
    "progressive": "I-IV-V-ii",
    "dreamy":      "i-iv-ii-III",
}

_NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


@dataclass
class SongConfig:
    root_midi: int
    scale_offsets: list[int]
    chord_prog: list[list[int]]
    notearp_pattern: list[int]
    stage_jitter: dict[str, int]
    filter_pb_bars: tuple[int, int]
    tgate_density: float
    # Derived display info
    mood: str
    seed: str
    arp_variant: int


def build_song_config(seed: str, mood: str) -> SongConfig:
    """Compute deterministic song configuration from seed + mood."""
    rng = random.Random(seed)

    # Root: MD5 of seed → MIDI note C2(36)–B2(47)
    root_midi = int(hashlib.md5(seed.encode()).hexdigest(), 16) % 12 + 36

    scale_offsets = _SCALE_OFFSETS[mood]
    chord_prog = _CHORD_PROGS[mood]

    # Notearp pattern
    arp_variant = rng.randint(0, len(_NOTEARP_VARIANTS) - 1)
    notearp_pattern = _NOTEARP_VARIANTS[arp_variant]

    # Stage jitter: ±2 bars on early stages, ±6 on late ones.
    # Small range on early stages so the full arrangement arrives quickly.
    _jitter_ranges = {
        "kick_on": (0, 0), "pad_on": (0, 0), "hihat_on": (0, 0),
        "kick_syncopated": (0, 0),
        "lead_root_on": (0, 2), "lead_melody_on": (0, 4),
        "pad_chord_on": (0, 4), "lead_voicing_on": (0, 4),
        "clap_on": (-2, 4), "pulse_on": (-4, 8), "fm_on": (-8, 8),
    }
    raw_jitter: dict[str, int] = {}
    for key, (lo, hi) in _jitter_ranges.items():
        raw_jitter[key] = rng.randint(lo, hi)

    # Filter pullback positions
    pb1 = rng.randint(20, 40)
    pb2 = rng.randint(60, 85)
    filter_pb_bars = (pb1, pb2)

    # Tgate density
    tgate_density = rng.uniform(0.65, 0.85)

    return SongConfig(
        root_midi=root_midi,
        scale_offsets=scale_offsets,
        chord_prog=chord_prog,
        notearp_pattern=notearp_pattern,
        stage_jitter=raw_jitter,
        filter_pb_bars=filter_pb_bars,
        tgate_density=tgate_density,
        mood=mood,
        seed=seed,
        arp_variant=arp_variant,
    )


# ---------------------------------------------------------------------------
# Timing constants
# ---------------------------------------------------------------------------

SAMPLE_RATE: int = 44100
STEPS_PER_BAR: int = 16
STEP_BEATS: float = 0.25          # one 16th note

step_duration: float = (60.0 / args.bpm) * STEP_BEATS
samples_per_step: int = int(SAMPLE_RATE * step_duration)
steps_per_second: float = SAMPLE_RATE / samples_per_step

# ---------------------------------------------------------------------------
# Scale / music theory
# ---------------------------------------------------------------------------
# Root and scale are determined by SongConfig (seed + mood).
# Helper functions accept scale_offsets and root_midi as parameters so they
# work with any config; default arguments kept for backwards compatibility.

def scale_degree_to_midi(degree: int, root_midi: int = 55,
                          scale_offsets: Optional[list[int]] = None) -> int:
    """Map a scale degree (0-indexed, unbounded) to a MIDI note.

    scale_offsets: semitone intervals of the scale (7 values).
    root_midi: MIDI root of the scale.
    """
    if scale_offsets is None:
        scale_offsets = [0, 2, 3, 5, 7, 8, 10]  # natural minor fallback
    octave, step = divmod(degree, 7)
    return root_midi + octave * 12 + scale_offsets[step]


def quantize_to_scale(midi: int, root: int = 55,
                       scale_offsets: Optional[list[int]] = None) -> int:
    """Snap midi note to nearest scale tone."""
    if scale_offsets is None:
        scale_offsets = [0, 2, 3, 5, 7, 8, 10]
    pc = (midi - root) % 12
    best = min(scale_offsets, key=lambda x: min(abs(pc - x), 12 - abs(pc - x)))
    return midi + (best - pc)


def midi_to_freq(n: int) -> float:
    return 440.0 * (2.0 ** ((n - 69) / 12.0))


CHORD_BARS = 4   # bars per chord (matches bline/bstruct 4-bar blocks)

def chord_for_bar(bar: int, cfg: "SongConfig") -> list[int]:
    """Return MIDI notes for the current chord block, using config's scale and root."""
    chord_idx = (bar // CHORD_BARS) % len(cfg.chord_prog)
    tone_degs = cfg.chord_prog[chord_idx]
    return [scale_degree_to_midi(d, cfg.root_midi + 12, cfg.scale_offsets)
            for d in tone_degs]

# ---------------------------------------------------------------------------
# Drum patterns
# ---------------------------------------------------------------------------
# Research: beat("0,4,8,11,14", 16) — kick AND clap on these steps.
# Hi-hat: white!16 every step (0–15).
# Clap simplified to backbeat (4, 12) for cleaner mix.

KICK_STEPS:  frozenset[int] = frozenset({0, 4, 8, 11, 14})
CLAP_STEPS:  frozenset[int] = frozenset({4, 12})
HIHAT_ALL_STEPS = True     # fires on all 16 steps

# ---------------------------------------------------------------------------
# Arrangement — additive stage model
# ---------------------------------------------------------------------------
# Research (switch_angel_song_structure.md): arc is strictly additive, no
# breakdown/drop.  Each entry = bar at which that element first appears.
# Timings synthesised from GWXCCBsOMSg (narrated) as primary reference,
# scaled to a ~128-bar session at 140 BPM.

STAGE_BARS: dict[str, int] = {
    "kick_on":           0,    # kick immediately
    "pad_on":            0,    # pad enters immediately with kick
    "lead_root_on":      2,    # lead enters fast
    "lead_melody_on":    4,    # melody + delay from bar 4
    "pad_chord_on":      4,    # pad chord movement from bar 4
    "lead_voicing_on":   8,    # voicing shift from bar 8
    "clap_on":           8,    # clap from bar 8
    "hihat_on":          0,    # hi-hat from bar 0 — high energy from the start
    "kick_syncopated":   0,    # syncopated kick immediately
    "fm_on":            32,    # FM opens in second half
    "pulse_on":         16,    # pulse texture from bar 16
}

# Simple 4-on-floor kick before syncopation upgrade.
KICK_STEPS_SIMPLE:      frozenset[int] = frozenset({0, 4, 8, 12})
KICK_STEPS_SYNCOPATED:  frozenset[int] = frozenset({0, 4, 8, 11, 14})

# Pad chord cycling degrees — from "<3@3 4 5 @3 6>*2".
# Changes every 2 bars.
_PAD_CHORD_DEGREES = [3, 4, 5, 6]

def pad_root_degree(bar: int, chord_active: bool) -> int:
    if not chord_active:
        return 0
    return _PAD_CHORD_DEGREES[(bar // 2) % len(_PAD_CHORD_DEGREES)]

# Lead voicing shift — from ".add 7 .add '<5 [4] 0 <0 2>>'"
# Before voicing stage: constant +7.  After: rotates per bar.
_LEAD_VOICING_SHIFTS = [12, 9, 7, 9]   # semitones added on top of chord root

def lead_voicing_semitones(bar: int, voicing_active: bool) -> int:
    if not voicing_active:
        return 7
    return _LEAD_VOICING_SHIFTS[bar % len(_LEAD_VOICING_SHIFTS)]

# ---------------------------------------------------------------------------
# Parameter arcs — continuous values that evolve over the session
# ---------------------------------------------------------------------------
# All documented in switch_angel_song_structure.md §B.6–B.9.

def _rlpf_to_hz(slider: float) -> float:
    """Convert Strudel rlpf slider value to Hz. Formula: (slider*12)^4."""
    v = max(0.01, slider) * 12.0
    return v ** 4.0

def filter_cutoff_arc(bar: int, pb_bars: tuple[int, int] = (32, 77)) -> float:
    """rlpf slider arc: 0.55 → 0.88 over ~128 bars, with two deliberate pullbacks.
    Research: gradual opening with pullbacks at ~bar 32 and ~bar 77.
    Floor raised to 0.55 (≈2.8 kHz) so pad/lead are audible from the start.
    pb_bars: (bar of first pullback, bar of second pullback) — seeded from SongConfig.
    """
    t = min(bar / 128.0, 1.0)
    t_pb1 = pb_bars[0] / 128.0
    t_pb2 = pb_bars[1] / 128.0
    # Start at 0.65 (~5 kHz) so the full arrangement is audible from bar 1.
    base = 0.65 + 0.23 * t
    pb1 = 0.12 * math.exp(-((t - t_pb1) ** 2) / 0.002)
    pb2 = 0.16 * math.exp(-((t - t_pb2) ** 2) / 0.003)
    slider = max(0.55, min(0.90, base - pb1 - pb2))
    return _rlpf_to_hz(slider)

def fm_depth_arc(bar: int, effective_stage_bars: dict) -> float:
    """FM depth: 0 for first ~96 bars, then ramps to 0.55 by bar 128.
    Research: fm(slider(0)) early, opens to 0.606 after ~2/3 through session.
    """
    if bar < effective_stage_bars["fm_on"]:
        return 0.0
    t = min((bar - effective_stage_bars["fm_on"]) / 32.0, 1.0)
    return t * 0.55

def delay_wet_arc(bar: int, effective_stage_bars: dict) -> float:
    """Lead delay wet: opens to wash ~bar 48, pulls back after ~bar 80.
    Research: delay(0.585→0.773→1.0→0.438) documented in 3fpx7Scysw4.
    """
    lm_bar = effective_stage_bars["lead_melody_on"]
    if bar < lm_bar:
        return 0.55
    peak_bar = lm_bar + 24
    if bar < peak_bar:
        t = (bar - lm_bar) / max(peak_bar - lm_bar, 1)
        return 0.55 + t * 0.25           # 0.55 → 0.80
    elif bar < peak_bar + 24:
        return 0.80                       # peak wash
    else:
        t = min((bar - (peak_bar + 24)) / 40.0, 1.0)
        return max(0.50, 0.80 - t * 0.30) # 0.80 → 0.50

def acidenv_arc(bar: int) -> float:
    """AcidEnv brightness: 0.44 → 0.85 steadily over session.
    Research: iu5rnQkfO6M 0.546→1.0; -pDO2RhcGhM 0.44→0.889.
    """
    t = min(bar / 128.0, 1.0)
    return 0.44 + t * 0.41

# ---------------------------------------------------------------------------
# Synthesis parameters — all cited from research
# ---------------------------------------------------------------------------

# Supersaw oscillator counts and detuning.
# Research: unison(5).detune(.6) on both pad and lead (= 60 cents total).
SAW_COUNT    = 5
DETUNE_CENTS = 60.0

# Filter cutoffs.
# Research: rlpf(0.877) ≈ 12,265 Hz (pad, very open);
#           rlpf(0.828) ≈ 9,743 Hz (lead, very open).
# lpenv(2) sweeps the filter briefly on each note trigger.
PAD_CUTOFF_BASE:  float = 12000.0
LEAD_CUTOFF_BASE: float = 9700.0
LPENV_DURATION_S: float = 0.06    # 60 ms sweep
LPENV_START_HZ:   float = 1200.0  # filter starts here, sweeps to base cutoff

# Trancegate — smooth cosine envelope, non-integer cycle rate.
# Research: trancegate(1.5, 45, 1).
# 1.5 cycles per bar → one gate cycle every 16/1.5 ≈ 10.67 steps.
TGATE_SPEED: float = 1.5    # gate cycles per bar
TGATE_DUTY:  float = 0.5    # open fraction per cycle (angle=45° ≈ 50%)

# Acidenv — fast attack, shaped decay.  Applied to every note trigger.
# Research: .acidenv(slider) where slider ≈ 0.5–0.7 in most frames.
# Decay raised to 200ms base so notes have presence before delay fills the gap.
ACIDENV_ATTACK_S: float = 0.003    # 3ms
ACIDENV_DECAY_S:  float = 0.20     # 200ms base (modulated by arc)

# Lead FM brown noise.  Research: .fm(.5).fmwave("brown").
# Implemented as brown noise phase modulation with depth 0.5.
LEAD_FM_DEPTH: float = 0.5

# Lead delay.  Research: .delay(.7), .delayfeedback(.8), .delaytime(1/4).
# 1/4 bar = 4 steps = quarter note delay time.
LEAD_DELAY_WET:      float = 0.70
LEAD_DELAY_FEEDBACK: float = 0.80
_delay_time_steps    = 4   # quarter note

# Voice levels (pre-limiter trim).
# Kick dominated the mix at 1.0 — pad/lead were inaudible.
# Target: kick ~25% of mix energy, pad+lead ~55%, drums ~20%.
KICK_LEVEL:  float = 0.40
HIHAT_LEVEL: float = 0.35
CLAP_LEVEL:  float = 0.45
PAD_LEVEL:   float = 1.40
LEAD_LEVEL:  float = 1.20
PULSE_LEVEL: float = 0.18

# Sidechain.  Research: .duck("3:4:5") → pad and lead duck on kick.
SIDECHAIN_DEPTH:   float = 0.08
SIDECHAIN_STEPS:   int   = 6     # recover over ~0.4 beat

# Master — lower drive so voices other than kick have headroom.
DRIVE: float = 1.4

# Notearp for lead — set at startup from SongConfig.notearp_pattern.
# 0 = chord root, 1 = chord third, 2 = chord fifth, -1 = rest.
# Default (variant 0) matches original Switch Angel pattern.
NOTEARP: list[int] = _NOTEARP_VARIANTS[0]

# ---------------------------------------------------------------------------
# Synthesis helpers
# ---------------------------------------------------------------------------

def _iir_lpf(signal: np.ndarray, cutoff_hz: float) -> np.ndarray:
    """One-pole IIR low-pass filter (in-place style, returns new array)."""
    a = (2.0 * math.pi * cutoff_hz) / (2.0 * math.pi * cutoff_hz + SAMPLE_RATE)
    out = np.empty_like(signal)
    y = 0.0
    for i in range(len(signal)):
        y = y + a * (float(signal[i]) - y)
        out[i] = y
    return out


def _iir_hpf(signal: np.ndarray, cutoff_hz: float) -> np.ndarray:
    """One-pole IIR high-pass filter."""
    a = (2.0 * math.pi * cutoff_hz) / (2.0 * math.pi * cutoff_hz + SAMPLE_RATE)
    out = np.empty_like(signal)
    y_lp = 0.0
    for i in range(len(signal)):
        y_lp = y_lp + a * (float(signal[i]) - y_lp)
        out[i] = signal[i] - y_lp
    return out


def _brown_noise(n: int, seed: int = 0) -> np.ndarray:
    """Generate brown (red) noise: integrated white noise, normalised."""
    rng = np.random.default_rng(seed)
    white = rng.standard_normal(n).astype(np.float32)
    brown = np.cumsum(white)
    # Normalise to ±1 range
    mx = float(np.abs(brown).max()) or 1.0
    return (brown / mx).astype(np.float32)


def acidenv(n_samples: int, amount: float = 0.55) -> np.ndarray:
    """Acid-style amplitude envelope: fast attack, shaped exponential decay.

    amount ∈ [0,1] — higher = longer sustain before decay.
    Research: .acidenv(slider(0.5–0.7)) on pad and lead voices.
    """
    t = np.arange(n_samples, dtype=np.float32) / SAMPLE_RATE
    attack_n = max(1, int(ACIDENV_ATTACK_S * SAMPLE_RATE))
    ramp = np.minimum(np.arange(n_samples, dtype=np.float32) / attack_n, 1.0)
    decay_tau = ACIDENV_DECAY_S * (0.3 + amount * 1.4)   # 30ms – 170ms
    decay = np.exp(-t / decay_tau)
    return (ramp * decay).astype(np.float32)


def lpenv(n_samples: int, base_cutoff: float) -> np.ndarray:
    """Per-step LP filter cutoff envelope: sweeps from low to base_cutoff.

    Research: .lpenv(2) — brief filter sweep on each note trigger.
    Returns array of per-sample cutoff frequencies.
    """
    sweep_n = int(LPENV_DURATION_S * SAMPLE_RATE)
    sweep_n = min(sweep_n, n_samples)
    env = np.full(n_samples, base_cutoff, dtype=np.float32)
    ramp = np.linspace(LPENV_START_HZ, base_cutoff, sweep_n, dtype=np.float32)
    env[:sweep_n] = ramp
    return env


def trancegate_envelope(
    step_in_bar: int,
    n_samples: int,
    speed: float = TGATE_SPEED,
    duty: float = TGATE_DUTY,
) -> np.ndarray:
    """Smooth cosine trancegate envelope for one step.

    Research: .trancegate(1.5, 45, 1) — smooth envelope cycling at 1.5x bar rate.
    The non-integer rate (1.5) creates polyrhythmic gate that drifts across the beat,
    generating the characteristic trance "breathing" feel.
    """
    phase_per_step = speed / STEPS_PER_BAR
    phase_start = (step_in_bar * phase_per_step) % 1.0
    phase_inc = phase_per_step / n_samples
    t = np.arange(n_samples, dtype=np.float32)
    phase = (phase_start + t * phase_inc) % 1.0
    # Smooth cosine: rises for first `duty` of cycle, falls for remainder
    env = np.where(
        phase < duty,
        0.5 * (1.0 - np.cos(np.pi * phase / duty)),
        0.5 * (1.0 + np.cos(np.pi * (phase - duty) / max(1.0 - duty, 1e-6))),
    )
    return env.astype(np.float32)


def synthesise_supersaw(
    midi_note: int,
    n_samples: int,
    cutoff_env: np.ndarray,
    amp_env: np.ndarray,
    osc_phases: Optional[np.ndarray] = None,
    iir_state: Optional[np.ndarray] = None,
    fm_noise: Optional[np.ndarray] = None,
    fm_depth: float = 0.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Render n_samples of a supersaw note with per-sample filter and amp envelopes.

    Returns (buf_l, buf_r, updated_osc_phases, updated_iir_state).
    fm_depth is the live arc value (0 early session → 0.55 late session).
    """
    if osc_phases is None:
        osc_phases = np.zeros(SAW_COUNT, dtype=np.float32)
    if iir_state is None:
        iir_state = np.zeros(2, dtype=np.float32)

    spread = DETUNE_CENTS / 1200.0
    offsets = np.linspace(-spread / 2.0, spread / 2.0, SAW_COUNT)
    base_freq = midi_to_freq(midi_note)
    freqs = base_freq * (2.0 ** offsets)

    buf_l = np.zeros(n_samples, dtype=np.float32)
    buf_r = np.zeros(n_samples, dtype=np.float32)

    pan = np.linspace(-1.0, 1.0, SAW_COUNT, dtype=np.float32)
    angles = (pan + 1.0) * (math.pi / 4.0)
    pan_l = np.cos(angles)
    pan_r = np.sin(angles)

    iir_L, iir_R = float(iir_state[0]), float(iir_state[1])

    for i in range(n_samples):
        fm_mod = float(fm_noise[i]) * fm_depth * 0.02 if (fm_noise is not None and fm_depth > 0.0) else 0.0

        sample_l = 0.0
        sample_r = 0.0
        for v in range(SAW_COUNT):
            delta = (freqs[v] * (1.0 + fm_mod)) / SAMPLE_RATE
            osc_phases[v] = (osc_phases[v] + delta) % 1.0
            saw = 2.0 * osc_phases[v] - 1.0
            sample_l += pan_l[v] * saw
            sample_r += pan_r[v] * saw

        sample_l /= SAW_COUNT
        sample_r /= SAW_COUNT

        cutoff = max(80.0, float(cutoff_env[i]))
        a = (2.0 * math.pi * cutoff) / (2.0 * math.pi * cutoff + SAMPLE_RATE)
        iir_L = iir_L + a * (sample_l - iir_L)
        iir_R = iir_R + a * (sample_r - iir_R)

        gain = float(amp_env[i])
        buf_l[i] = iir_L * gain
        buf_r[i] = iir_R * gain

    iir_state[0] = iir_L
    iir_state[1] = iir_R
    return buf_l, buf_r, osc_phases, iir_state


# ---------------------------------------------------------------------------
# Kick synthesis — TR-909 style
# ---------------------------------------------------------------------------
# Research: s("bd:3!4").dec(.3).bank("tr909") — sample-based in Strudel.
# We approximate the TR-909 kick with: sine sweep + click transient.

def synthesise_kick() -> tuple[np.ndarray, np.ndarray]:
    n = int(SAMPLE_RATE * 0.25)     # 250ms total
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE

    # Frequency sweep: 180Hz → 50Hz over 80ms
    f0, f1 = 180.0, 50.0
    sweep_t = 0.08
    freq = f0 * np.exp(np.log(f1 / f0) * np.minimum(t / sweep_t, 1.0))
    phase = np.cumsum(freq / SAMPLE_RATE)
    body = np.sin(2.0 * math.pi * phase)

    # Amplitude envelope: punchy decay
    body_env = np.exp(-t / 0.06)

    # Click transient: sharp noise burst at attack (~2ms)
    click_n = int(0.002 * SAMPLE_RATE)
    click_env = np.exp(-t[:click_n] / 0.0005)
    click = np.random.randn(click_n).astype(np.float32) * click_env * 0.4

    buf = (body * body_env).astype(np.float32)
    buf[:click_n] += click

    # Normalize
    peak = float(np.abs(buf).max()) or 1.0
    buf = buf / peak * 0.95
    return buf, buf.copy()


# ---------------------------------------------------------------------------
# Hi-hat synthesis
# ---------------------------------------------------------------------------
# Research: s("white!16").dec(tri.fast(4).range(0.05,.12)).gain(.5).hpf(1200)
# White noise bursts every 16th, high-passed at 1200 Hz.
# Decay time modulated by triangle wave cycling every 4 bars.

def synthesise_hihat(decay_s: float = 0.08) -> tuple[np.ndarray, np.ndarray]:
    """Synthesise one hi-hat hit with given decay time."""
    n = int(SAMPLE_RATE * (decay_s * 4 + 0.01))
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    noise = np.random.randn(n).astype(np.float32)
    env = np.exp(-t / decay_s)
    buf = (noise * env * 0.5).astype(np.float32)
    # HPF at 1200 Hz — removes low-end rumble
    buf = _iir_hpf(buf, 1200.0)
    peak = float(np.abs(buf).max()) or 1.0
    buf = (buf / peak * 0.7).astype(np.float32)
    return buf, buf.copy()


def hihat_decay(step: int, bar: int) -> float:
    """Triangle LFO decay time: 0.05–0.12s cycling every 4 bars.
    Research: tri.fast(4).range(0.05, .12) — 4 cycles per bar, range 0.05–0.12.
    """
    phase = ((bar * STEPS_PER_BAR + step) * 4 / STEPS_PER_BAR) % 1.0
    tri = 1.0 - abs(2.0 * phase - 1.0)
    return 0.05 + tri * 0.07


# ---------------------------------------------------------------------------
# Clap synthesis
# ---------------------------------------------------------------------------
# Research: s("jcp:2!4").struct("<- 1>*4") — backbeat clap sample.
# Approximated with band-passed noise burst.

def synthesise_clap() -> tuple[np.ndarray, np.ndarray]:
    n = int(SAMPLE_RATE * 0.07)
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE
    noise = np.random.randn(n).astype(np.float32)
    env = np.exp(-t / 0.025)
    buf = (noise * env * 0.6).astype(np.float32)
    buf = _iir_lpf(buf, 5000.0)
    buf = _iir_hpf(buf, 300.0)
    peak = float(np.abs(buf).max()) or 1.0
    buf = (buf / peak * 0.85).astype(np.float32)
    return buf, buf.copy()


# ---------------------------------------------------------------------------
# Pulse texture layer
# ---------------------------------------------------------------------------
# Research: s("pulse!16").dec(.1).fm(time).fmh(time) — subtle shimmer layer.

def synthesise_pulse(step: int, total_step: int) -> tuple[np.ndarray, np.ndarray]:
    """Short pulse/noise burst with time-varying FM texture."""
    n = samples_per_step
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE

    # Frequency: time-varying — drifts slowly based on global step
    freq_base = 200.0 + 800.0 * ((math.sin(total_step * 0.01) + 1.0) / 2.0)
    phase_inc = freq_base / SAMPLE_RATE
    phase = np.cumsum(np.full(n, phase_inc, dtype=np.float32))
    pulse = np.sign(np.sin(2.0 * math.pi * phase)) * 0.5   # pulse wave

    env = np.exp(-t / 0.1)
    noise = np.random.randn(n).astype(np.float32) * 0.3
    buf = ((pulse + noise) * env).astype(np.float32)
    buf = _iir_lpf(buf, 3000.0)
    buf = _iir_hpf(buf, 400.0)
    return buf * 0.6, buf.copy() * 0.6


# ---------------------------------------------------------------------------
# Feedback delay (for lead)
# ---------------------------------------------------------------------------
# Research: .delay(.7).delayfeedback(.8).delaytime(1/4)
# 1/4 = quarter note = 4 steps delay time.

class FeedbackDelay:
    def __init__(self, delay_steps: int = _delay_time_steps) -> None:
        delay_samples = delay_steps * samples_per_step
        self.buf_l = np.zeros(delay_samples, dtype=np.float32)
        self.buf_r = np.zeros(delay_samples, dtype=np.float32)
        self.pos = 0
        self.size = delay_samples

    def process(
        self,
        dry_l: np.ndarray,
        dry_r: np.ndarray,
        wet: float = LEAD_DELAY_WET,
        feedback: float = LEAD_DELAY_FEEDBACK,
    ) -> tuple[np.ndarray, np.ndarray]:
        out_l = np.empty_like(dry_l)
        out_r = np.empty_like(dry_r)
        for i in range(len(dry_l)):
            echo_l = float(self.buf_l[self.pos])
            echo_r = float(self.buf_r[self.pos])
            self.buf_l[self.pos] = np.float32(float(dry_l[i]) + echo_l * feedback)
            self.buf_r[self.pos] = np.float32(float(dry_r[i]) + echo_r * feedback)
            self.pos = (self.pos + 1) % self.size
            out_l[i] = np.float32(float(dry_l[i]) * (1.0 - wet) + echo_l * wet)
            out_r[i] = np.float32(float(dry_r[i]) * (1.0 - wet) + echo_r * wet)
        return out_l, out_r


# ---------------------------------------------------------------------------
# Simple FDN reverb (unchanged from v1 — works well)
# ---------------------------------------------------------------------------

_REVERB_DELAYS = [1847, 1699, 2053, 2251]
_REVERB_FEEDBACK = 0.82

class SimpleFDN:
    def __init__(self) -> None:
        self.bufs = [np.zeros(d, dtype=np.float32) for d in _REVERB_DELAYS]
        self.pos = [0] * 4

    def process(self, x: np.ndarray, wet: float = 0.20) -> np.ndarray:
        out = np.empty_like(x)
        for s in range(len(x)):
            outputs = [float(self.bufs[i][self.pos[i]]) for i in range(4)]
            mixed = (sum(outputs)) * 0.25
            xf = float(x[s])
            for i in range(4):
                self.bufs[i][self.pos[i]] = np.float32(xf * 0.015 + mixed * _REVERB_FEEDBACK)
                self.pos[i] = (self.pos[i] + 1) % _REVERB_DELAYS[i]
            out[s] = np.float32(xf * (1.0 - wet) + mixed * wet)
        return out


# ---------------------------------------------------------------------------
# Pre-buffered note accumulator (for drums)
# ---------------------------------------------------------------------------

@dataclass
class PrerenderedNote:
    buf_l: np.ndarray
    buf_r: np.ndarray
    pos: int = 0


def drain_notes(notes: list[PrerenderedNote], n: int) -> tuple[np.ndarray, np.ndarray]:
    mix_l = np.zeros(n, dtype=np.float32)
    mix_r = np.zeros(n, dtype=np.float32)
    expired: list[int] = []
    for i, note in enumerate(notes):
        avail = len(note.buf_l) - note.pos
        if avail <= 0:
            expired.append(i)
            continue
        chunk = min(n, avail)
        mix_l[:chunk] += note.buf_l[note.pos:note.pos + chunk]
        mix_r[:chunk] += note.buf_r[note.pos:note.pos + chunk]
        note.pos += n
        if note.pos >= len(note.buf_l):
            expired.append(i)
    for i in reversed(expired):
        del notes[i]
    return mix_l, mix_r


# ---------------------------------------------------------------------------
# Arrangement state
# ---------------------------------------------------------------------------

@dataclass
class ArrangementState:
    step: int = 0
    # Voice gains (ramped toward targets each step)
    kick_gain:  float = 0.0
    hihat_gain: float = 0.0
    clap_gain:  float = 0.0
    pad_gain:   float = 0.0
    lead_gain:  float = 0.0
    pulse_gain: float = 0.0
    # Sidechain
    sidechain_env: float = 1.0
    # Master volume
    master_vol: float = 0.0
    # Pad oscillator state (3 voices: root, root-14, root-21)
    pad_osc_phases: list = field(default_factory=lambda: [None, None, None])
    pad_iir_states: list = field(default_factory=lambda: [None, None, None])
    pad_current_notes: list = field(default_factory=lambda: [-1, -1, -1])
    # Lead oscillator state (reset on each notearp trigger)
    lead_osc_phases: np.ndarray = field(default_factory=lambda: np.zeros(SAW_COUNT, dtype=np.float32))
    lead_iir_state:  np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float32))
    # Brown noise seed index (advances per lead note)
    brown_seed: int = 0


def _stage_active(bar: int, key: str, eff_stage_bars: dict) -> bool:
    return bar >= eff_stage_bars[key]


def _target_gain(bar: int, voice: str, eff_stage_bars: dict) -> float:
    """Return target gain for a voice at a given bar."""
    if voice == "kick":
        return 1.0 if _stage_active(bar, "kick_on", eff_stage_bars) else 0.0
    if voice == "hihat":
        return 0.75 if _stage_active(bar, "hihat_on", eff_stage_bars) else 0.0
    if voice == "clap":
        return 0.8 if _stage_active(bar, "clap_on", eff_stage_bars) else 0.0
    if voice == "pad":
        return 1.0 if _stage_active(bar, "pad_on", eff_stage_bars) else 0.0
    if voice == "lead":
        return 1.0 if _stage_active(bar, "lead_root_on", eff_stage_bars) else 0.0
    if voice == "pulse":
        return 0.6 if _stage_active(bar, "pulse_on", eff_stage_bars) else 0.0
    return 0.0


def advance_arrangement(state: ArrangementState, bar: int, target_vol: float,
                        eff_stage_bars: dict) -> None:
    state.step += 1

    for v in ("kick", "hihat", "clap", "pad", "lead", "pulse"):
        cur = getattr(state, f"{v}_gain")
        tgt = _target_gain(bar, v, eff_stage_bars)
        setattr(state, f"{v}_gain", cur + (tgt - cur) * 0.04)

    state.sidechain_env = min(1.0, state.sidechain_env + 1.0 / SIDECHAIN_STEPS)
    state.master_vol = min(target_vol, state.master_vol + target_vol / (STEPS_PER_BAR * 4))


# ---------------------------------------------------------------------------
# Mix and limit
# ---------------------------------------------------------------------------

def mix_and_limit(
    voices: list[tuple[np.ndarray, np.ndarray]],
    master_vol: float,
) -> tuple[np.ndarray, np.ndarray]:
    n = len(voices[0][0])
    mix_l = np.zeros(n, dtype=np.float32)
    mix_r = np.zeros(n, dtype=np.float32)
    for l, r in voices:
        mix_l += l
        mix_r += r
    mix_l = np.tanh(mix_l * master_vol * DRIVE).astype(np.float32)
    mix_r = np.tanh(mix_r * master_vol * DRIVE).astype(np.float32)
    return mix_l, mix_r


# ---------------------------------------------------------------------------
# WAV writer
# ---------------------------------------------------------------------------

def write_wav(path: str, chunks: list[np.ndarray]) -> None:
    if not chunks:
        return
    data = np.concatenate(chunks, axis=0)
    data = np.clip(data, -1.0, 1.0)
    pcm = (data * 32767.0).astype(np.int16)
    try:
        with _wave.open(path, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm.tobytes())
        logger.info("WAV written to %s", path)
    except OSError as exc:
        logger.error("Failed to write WAV: %s", exc)


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s",
                        stream=sys.stderr)

    # ------------------------------------------------------------------
    # Build deterministic song config from seed + mood
    # ------------------------------------------------------------------
    cfg = build_song_config(args.seed, args.mood)

    # Apply stage jitter to STAGE_BARS, preserving order and non-negative values.
    # Build effective stage bars: clamp so each stage >= 0 and >= prev stage + 4.
    _stage_order = [
        "kick_on", "pad_on", "lead_root_on", "lead_melody_on",
        "pad_chord_on", "lead_voicing_on", "clap_on", "fm_on",
        "pulse_on", "hihat_on", "kick_syncopated",
    ]
    eff_stage_bars: dict[str, int] = {}
    for key in _stage_order:
        raw = STAGE_BARS[key] + cfg.stage_jitter[key]
        eff_stage_bars[key] = max(0, raw)

    # Print startup config line
    root_pc = cfg.root_midi % 12
    root_name = _NOTE_NAMES[root_pc]
    scale_suffix = "m" if cfg.scale_offsets[2] == 3 else ("dor" if cfg.scale_offsets[5] == 9 else "")
    prog_name = _MOOD_NAMES[cfg.mood]
    print(
        f"[v2] seed={args.seed} mood={cfg.mood} root={root_name} "
        f"key={root_name}{scale_suffix} prog={prog_name} arp_variant={cfg.arp_variant}"
    )

    wav_mode = args.wav is not None
    wav_chunks: list[np.ndarray] = []
    stream = None

    if not wav_mode:
        try:
            stream = sd.OutputStream(samplerate=SAMPLE_RATE, channels=2, dtype="float32")
            stream.start()
        except sd.PortAudioError as exc:
            logger.error("Audio device error: %s", exc)
            sys.exit(1)

    midi = MIDIFile(1)
    midi.addTempo(0, 0, args.bpm)

    state = ArrangementState(
        kick_gain  = _target_gain(0, "kick",  eff_stage_bars),
        hihat_gain = _target_gain(0, "hihat", eff_stage_bars),
        clap_gain  = _target_gain(0, "clap",  eff_stage_bars),
        pad_gain   = _target_gain(0, "pad",   eff_stage_bars),
        lead_gain  = _target_gain(0, "lead",  eff_stage_bars),
        pulse_gain = _target_gain(0, "pulse", eff_stage_bars),
        master_vol = args.volume,
    )
    lead_delay = FeedbackDelay()
    pad_reverb_l = SimpleFDN()
    pad_reverb_r = SimpleFDN()
    lead_reverb_l = SimpleFDN()
    lead_reverb_r = SimpleFDN()

    kick_notes:  list[PrerenderedNote] = []
    hihat_notes: list[PrerenderedNote] = []
    clap_notes:  list[PrerenderedNote] = []

    fade_out = False
    fade_out_steps = 32 * STEPS_PER_BAR
    nan_warned = False

    try:
        while True:
            step_in_bar = state.step % STEPS_PER_BAR
            bar = state.step // STEPS_PER_BAR
            beat_time = float(state.step) * STEP_BEATS

            # Stop check
            flag = f"fade_{os.getpid()}.flag"
            if os.path.exists(flag):
                fade_out = True
                os.remove(flag)
            if args.bars > 0 and state.step >= args.bars * STEPS_PER_BAR:
                fade_out = True

            if fade_out:
                state.master_vol -= args.volume / fade_out_steps
                if state.master_vol <= 0.0:
                    state.master_vol = 0.0
                    if not wav_mode:
                        stream.write(np.zeros((samples_per_step, 2), dtype=np.float32))
                    break
            else:
                advance_arrangement(state, bar, args.volume, eff_stage_bars)

            # ----------------------------------------------------------------
            # Stage flags and arc values for this bar
            # ----------------------------------------------------------------
            pad_chord_active    = _stage_active(bar, "pad_chord_on", eff_stage_bars)
            lead_melody_active  = _stage_active(bar, "lead_melody_on", eff_stage_bars)
            lead_voicing_active = _stage_active(bar, "lead_voicing_on", eff_stage_bars)
            kick_steps = (KICK_STEPS_SYNCOPATED
                          if _stage_active(bar, "kick_syncopated", eff_stage_bars)
                          else KICK_STEPS_SIMPLE)

            live_cutoff    = filter_cutoff_arc(bar, cfg.filter_pb_bars)
            live_fm_depth  = fm_depth_arc(bar, eff_stage_bars)
            live_delay_wet = delay_wet_arc(bar, eff_stage_bars)
            live_acidenv   = acidenv_arc(bar)

            # ----------------------------------------------------------------
            # Chord / scale
            # ----------------------------------------------------------------
            pad_degree = pad_root_degree(bar, pad_chord_active)
            pad_root_note = scale_degree_to_midi(pad_degree, cfg.root_midi + 12,
                                                 cfg.scale_offsets)
            pad_notes_midi = [pad_root_note, pad_root_note - 14, pad_root_note - 21]

            voicing_shift = lead_voicing_semitones(bar, lead_voicing_active)
            chord = chord_for_bar(bar, cfg)   # [root, third, fifth]

            # ----------------------------------------------------------------
            # Kick
            # ----------------------------------------------------------------
            kick_l_step = np.zeros(samples_per_step, dtype=np.float32)
            kick_r_step = np.zeros(samples_per_step, dtype=np.float32)
            if step_in_bar in kick_steps and state.kick_gain > 0.01:
                kl, kr = synthesise_kick()
                kick_notes.append(PrerenderedNote(kl, kr))
                if state.sidechain_env > SIDECHAIN_DEPTH:
                    state.sidechain_env = SIDECHAIN_DEPTH
                midi.addNote(0, 4, 36, beat_time, STEP_BEATS, 100)
            kl, kr = drain_notes(kick_notes, samples_per_step)
            kick_l_step = kl * state.kick_gain * KICK_LEVEL
            kick_r_step = kr * state.kick_gain * KICK_LEVEL

            # ----------------------------------------------------------------
            # Hi-hat — every step once hihat_on stage active
            # ----------------------------------------------------------------
            hihat_l_step = np.zeros(samples_per_step, dtype=np.float32)
            hihat_r_step = np.zeros(samples_per_step, dtype=np.float32)
            if state.hihat_gain > 0.01:
                decay = hihat_decay(step_in_bar, bar)
                hl, hr = synthesise_hihat(decay)
                hihat_notes.append(PrerenderedNote(hl, hr))
            hml, hmr = drain_notes(hihat_notes, samples_per_step)
            pan_hh = 0.7 if step_in_bar % 2 == 0 else 0.3
            hihat_l_step = hml * state.hihat_gain * HIHAT_LEVEL * pan_hh
            hihat_r_step = hmr * state.hihat_gain * HIHAT_LEVEL * (1.0 - pan_hh)

            # ----------------------------------------------------------------
            # Clap — backbeat
            # ----------------------------------------------------------------
            if step_in_bar in CLAP_STEPS and state.clap_gain > 0.01:
                cl, cr = synthesise_clap()
                clap_notes.append(PrerenderedNote(cl, cr))
            cml, cmr = drain_notes(clap_notes, samples_per_step)
            clap_l_step = cml * state.clap_gain * CLAP_LEVEL
            clap_r_step = cmr * state.clap_gain * CLAP_LEVEL

            # ----------------------------------------------------------------
            # Pad — seg 16 retrigger, acidenv, trancegate, live filter arc
            # Before pad_chord_on: single root.  After: cycling chord degrees.
            # ----------------------------------------------------------------
            pad_l_step = np.zeros(samples_per_step, dtype=np.float32)
            pad_r_step = np.zeros(samples_per_step, dtype=np.float32)

            if state.pad_gain > 0.01:
                if step_in_bar == 0:
                    state.pad_osc_phases = [None, None, None]
                    state.pad_iir_states = [None, None, None]
                    state.pad_current_notes = list(pad_notes_midi)

                amp_env = acidenv(samples_per_step, amount=live_acidenv)
                cut_env = lpenv(samples_per_step, live_cutoff)
                gate_env = trancegate_envelope(step_in_bar, samples_per_step,
                                               duty=cfg.tgate_density)

                for vi, note in enumerate(state.pad_current_notes):
                    if note < 0:
                        continue
                    bl, br, new_phases, new_iir = synthesise_supersaw(
                        note, samples_per_step, cut_env, amp_env,
                        osc_phases=state.pad_osc_phases[vi],
                        iir_state=state.pad_iir_states[vi],
                    )
                    state.pad_osc_phases[vi] = new_phases
                    state.pad_iir_states[vi] = new_iir
                    pad_l_step += bl
                    pad_r_step += br

                pad_l_step *= gate_env * state.sidechain_env
                pad_r_step *= gate_env * state.sidechain_env
                pad_l_step = pad_reverb_l.process(pad_l_step, wet=0.25)
                pad_r_step = pad_reverb_r.process(pad_r_step, wet=0.25)
                pad_l_step *= state.pad_gain * PAD_LEVEL
                pad_r_step *= state.pad_gain * PAD_LEVEL

            # ----------------------------------------------------------------
            # Lead — single root before lead_melody_on, notearp after.
            # Voicing shift applied after lead_voicing_on.
            # FM depth, filter cutoff, delay wet all follow live arcs.
            # ----------------------------------------------------------------
            lead_l_step = np.zeros(samples_per_step, dtype=np.float32)
            lead_r_step = np.zeros(samples_per_step, dtype=np.float32)

            if state.lead_gain > 0.01:
                if not lead_melody_active:
                    # Stage 3: single root note, held — retrigger every bar
                    fire_note = step_in_bar == 0
                    arp_tone_idx = 0 if fire_note else -1
                else:
                    arp_tone_idx = cfg.notearp_pattern[step_in_bar]

                if arp_tone_idx >= 0:
                    base_note = chord[min(arp_tone_idx, len(chord) - 1)]
                    note = base_note + voicing_shift
                    note = max(48, min(96, note))   # clamp to sane range

                    fm_buf = _brown_noise(samples_per_step, seed=state.brown_seed) if live_fm_depth > 0.0 else None
                    state.brown_seed = (state.brown_seed + 1) % 65536

                    state.lead_osc_phases = np.zeros(SAW_COUNT, dtype=np.float32)
                    state.lead_iir_state  = np.zeros(2, dtype=np.float32)

                    amp_env = acidenv(samples_per_step, amount=live_acidenv)
                    cut_env = lpenv(samples_per_step, live_cutoff)

                    bl, br, new_phases, new_iir = synthesise_supersaw(
                        note, samples_per_step, cut_env, amp_env,
                        osc_phases=state.lead_osc_phases,
                        iir_state=state.lead_iir_state,
                        fm_noise=fm_buf,
                        fm_depth=live_fm_depth,
                    )
                    state.lead_osc_phases = new_phases
                    state.lead_iir_state  = new_iir
                    lead_l_step = bl
                    lead_r_step = br
                    midi.addNote(0, 0, note, beat_time, STEP_BEATS, 75)

                lead_l_step, lead_r_step = lead_delay.process(
                    lead_l_step, lead_r_step,
                    wet=live_delay_wet, feedback=LEAD_DELAY_FEEDBACK,
                )
                lead_l_step *= state.sidechain_env
                lead_r_step *= state.sidechain_env
                lead_l_step = lead_reverb_l.process(lead_l_step, wet=0.12)
                lead_r_step = lead_reverb_r.process(lead_r_step, wet=0.12)
                lead_l_step *= state.lead_gain * LEAD_LEVEL
                lead_r_step *= state.lead_gain * LEAD_LEVEL

            # ----------------------------------------------------------------
            # Pulse texture
            # ----------------------------------------------------------------
            pulse_l_step = np.zeros(samples_per_step, dtype=np.float32)
            pulse_r_step = np.zeros(samples_per_step, dtype=np.float32)
            if state.pulse_gain > 0.01:
                pl, pr = synthesise_pulse(step_in_bar, state.step)
                pulse_l_step = pl * state.pulse_gain * PULSE_LEVEL
                pulse_r_step = pr * state.pulse_gain * PULSE_LEVEL

            # ----------------------------------------------------------------
            # Mix and limit
            # ----------------------------------------------------------------
            voices = [
                (kick_l_step,  kick_r_step),
                (hihat_l_step, hihat_r_step),
                (clap_l_step,  clap_r_step),
                (pad_l_step,   pad_r_step),
                (lead_l_step,  lead_r_step),
                (pulse_l_step, pulse_r_step),
            ]
            mix_l, mix_r = mix_and_limit(voices, state.master_vol)

            if not (np.isfinite(mix_l).all() and np.isfinite(mix_r).all()):
                if not nan_warned:
                    logger.warning("NaN/Inf in audio buffer — silencing")
                    nan_warned = True
                mix_l = np.zeros(samples_per_step, dtype=np.float32)
                mix_r = np.zeros(samples_per_step, dtype=np.float32)

            # ----------------------------------------------------------------
            # Output
            # ----------------------------------------------------------------
            if wav_mode:
                wav_chunks.append(np.column_stack([mix_l, mix_r]).astype(np.float32))
            else:
                stream.write(np.column_stack([mix_l, mix_r]))

            if step_in_bar == 0 and not fade_out:
                cutoff_k = live_cutoff / 1000.0
                n_active = sum(1 for v in eff_stage_bars.values() if bar >= v)
                print(
                    f"[v2] bar={bar+1:4d}  stages={n_active}/11"
                    f"  K:{state.kick_gain:.2f} P:{state.pad_gain:.2f} L:{state.lead_gain:.2f}"
                    f"  filt={cutoff_k:.1f}kHz fm={live_fm_depth:.2f} dly={live_delay_wet:.2f}"
                )

        if wav_mode:
            write_wav(args.wav, wav_chunks)
        else:
            stream.stop()
            stream.close()
        if args.out_midi:
            with open(args.out_midi, "wb") as f:
                midi.writeFile(f)

    except KeyboardInterrupt:
        if wav_mode:
            write_wav(args.wav, wav_chunks)
        else:
            if stream:
                stream.stop()
                stream.close()
        if args.out_midi:
            with open(args.out_midi, "wb") as f:
                midi.writeFile(f)
        sys.exit(0)

    except sd.PortAudioError as exc:
        logger.error("Audio stream error: %s", exc)
        if stream:
            try:
                stream.stop(); stream.close()
            except Exception:
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()
