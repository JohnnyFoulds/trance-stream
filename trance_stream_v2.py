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
args = parser.parse_args()

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
# Root always G minor (as per Switch Angel's setScale("g:minor")).
# We build a G natural minor scale and quantize all notes to it.

_G_NATURAL_MINOR = [0, 2, 3, 5, 7, 8, 10]   # semitone offsets from G

def scale_degree_to_midi(degree: int, root_midi: int = 55) -> int:
    """Map a scale degree (0-indexed, unbounded) to a MIDI note in G minor.
    root_midi 55 = G3.
    """
    octave, step = divmod(degree, 7)
    return root_midi + octave * 12 + _G_NATURAL_MINOR[step]


def quantize_to_scale(midi: int, root: int = 55) -> int:
    """Snap midi note to nearest G minor scale tone."""
    pc = (midi - root) % 12
    best = min(_G_NATURAL_MINOR, key=lambda x: min(abs(pc - x), 12 - abs(pc - x)))
    return midi + (best - pc)


def midi_to_freq(n: int) -> float:
    return 440.0 * (2.0 ** ((n - 69) / 12.0))


# Chord progression — 4 chords, 4 bars each (16 bars total per cycle).
# Chosen to sit naturally in G minor (i → VI → III → VII).
# Each entry is (root_degree, chord_tones_as_scale_degrees).
# Research: setCpm(140/4), setScale("g:minor"), progression implicit in bline.
_CHORD_PROG = [
    # (root_degree, [scale degrees for chord tones])
    (0,  [0, 2, 4]),   # Gm  (i)
    (5,  [5, 7, 9]),   # Cm  (iv)
    (3,  [3, 5, 7]),   # A#  (III)
    (4,  [4, 6, 8]),   # Dm  (v)
]
CHORD_BARS = 4   # bars per chord (matches bline/bstruct 4-bar blocks)

def chord_for_bar(bar: int) -> list[int]:
    """Return MIDI notes for the current chord block."""
    chord_idx = (bar // CHORD_BARS) % len(_CHORD_PROG)
    root_deg, tone_degs = _CHORD_PROG[chord_idx]
    return [scale_degree_to_midi(d) for d in tone_degs]

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
# Arrangement phases
# ---------------------------------------------------------------------------

PHASE_BARS = 16
INTRO_BARS = 4
PHASE_SEQUENCE = ["Intro", "Groove", "Breakdown", "Buildup", "Drop"]

# Gain targets per phase for each voice.
# Research: build order = kick → pad → lead.  Lead absent in Intro/Breakdown.
PHASE_GAINS: dict[str, dict[str, float]] = {
    "Intro":     {"kick": 0.5, "hihat": 0.4, "clap": 0.0,
                  "pad": 0.8, "lead": 0.0, "pulse": 0.4},
    "Groove":    {"kick": 1.0, "hihat": 0.8, "clap": 0.7,
                  "pad": 1.0, "lead": 1.0, "pulse": 0.3},
    "Breakdown": {"kick": 0.0, "hihat": 0.3, "clap": 0.0,
                  "pad": 1.0, "lead": 0.6, "pulse": 0.5},
    "Buildup":   {"kick": 0.5, "hihat": 1.0, "clap": 0.5,
                  "pad": 1.0, "lead": 0.0, "pulse": 0.6},
    "Drop":      {"kick": 1.0, "hihat": 0.8, "clap": 0.7,
                  "pad": 1.0, "lead": 1.0, "pulse": 0.3},
}

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
LPENV_DURATION_S: float = 0.08    # 80 ms sweep up from low cutoff
LPENV_START_HZ:   float = 400.0   # filter starts here, sweeps to base cutoff

# Trancegate — smooth cosine envelope, non-integer cycle rate.
# Research: trancegate(1.5, 45, 1).
# 1.5 cycles per bar → one gate cycle every 16/1.5 ≈ 10.67 steps.
TGATE_SPEED: float = 1.5    # gate cycles per bar
TGATE_DUTY:  float = 0.5    # open fraction per cycle (angle=45° ≈ 50%)

# Acidenv — fast attack, shaped decay.  Applied to every note trigger.
# Research: .acidenv(slider) where slider ≈ 0.5–0.7 in most frames.
ACIDENV_ATTACK_S: float = 0.003    # 3ms
ACIDENV_DECAY_S:  float = 0.10     # 100ms (can be modulated)

# Lead FM brown noise.  Research: .fm(.5).fmwave("brown").
# Implemented as brown noise phase modulation with depth 0.5.
LEAD_FM_DEPTH: float = 0.5

# Lead delay.  Research: .delay(.7), .delayfeedback(.8), .delaytime(1/4).
# 1/4 bar = 4 steps = quarter note delay time.
LEAD_DELAY_WET:      float = 0.70
LEAD_DELAY_FEEDBACK: float = 0.80
_delay_time_steps    = 4   # quarter note

# Voice levels (pre-limiter trim)
KICK_LEVEL:  float = 1.00
HIHAT_LEVEL: float = 0.55
CLAP_LEVEL:  float = 0.65
PAD_LEVEL:   float = 1.10
LEAD_LEVEL:  float = 0.80
PULSE_LEVEL: float = 0.12

# Sidechain.  Research: .duck("3:4:5") → pad and lead duck on kick.
SIDECHAIN_DEPTH:   float = 0.04
SIDECHAIN_STEPS:   int   = 6     # recover over ~0.4 beat

# Master
DRIVE: float = 2.5   # soft-clip drive

# Notearp for lead — 16-step pattern of chord-tone indices (0,1,2) or -1=rest.
# Derived from "< <- - - -> 0 1@2 0 1 0 1>*16" in Coding Trance IV.
# 0 = chord root, 1 = chord third, 2 = chord fifth.
# The heavy delay fills in the gaps, creating the wash characteristic of her lead.
NOTEARP: list[int] = [
    0, -1, -1, -1,   # beat 1: root + 3 rests
    1,  0,  1, -1,   # beat 2: third, root, third, rest
    0, -1,  1,  0,   # beat 3: root, rest, third, root
    1, -1, -1, -1,   # beat 4: third + 3 rests
]

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
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Render n_samples of a supersaw note with per-sample filter and amp envelopes.

    Returns (buf_l, buf_r, updated_osc_phases, updated_iir_state).
    osc_phases shape (SAW_COUNT,); iir_state shape (2,) = [L, R].
    fm_noise: optional brown noise for FM modulation (shape n_samples).
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
        # FM: modulate each oscillator phase increment with brown noise
        fm_mod = float(fm_noise[i]) * LEAD_FM_DEPTH if fm_noise is not None else 0.0

        sample_l = 0.0
        sample_r = 0.0
        for v in range(SAW_COUNT):
            delta = (freqs[v] * (1.0 + fm_mod * 0.02)) / SAMPLE_RATE
            osc_phases[v] = (osc_phases[v] + delta) % 1.0
            saw = 2.0 * osc_phases[v] - 1.0
            sample_l += pan_l[v] * saw
            sample_r += pan_r[v] * saw

        sample_l /= SAW_COUNT
        sample_r /= SAW_COUNT

        # Per-sample 2-pole IIR LPF (cascade two 1-poles for 12 dB/oct)
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
    phase: str = "Intro"
    phase_bar: int = 0
    # Current voice gains (interpolate towards targets)
    kick_gain:  float = 0.5
    hihat_gain: float = 0.4
    clap_gain:  float = 0.0
    pad_gain:   float = 0.8
    lead_gain:  float = 0.0
    pulse_gain: float = 0.4
    # Sidechain
    sidechain_env: float = 1.0
    # Master volume
    master_vol: float = 0.0
    # Pad oscillator state (sustained across steps for each voice note)
    pad_osc_phases: list = field(default_factory=lambda: [None, None, None])
    pad_iir_states: list = field(default_factory=lambda: [None, None, None])
    pad_current_notes: list = field(default_factory=lambda: [-1, -1, -1])
    # Lead oscillator state (reset on each notearp trigger)
    lead_osc_phases: np.ndarray = field(default_factory=lambda: np.zeros(SAW_COUNT, dtype=np.float32))
    lead_iir_state:  np.ndarray = field(default_factory=lambda: np.zeros(2, dtype=np.float32))
    # Brown noise seed index (advances per lead note)
    brown_seed: int = 0


def advance_arrangement(state: ArrangementState, target_vol: float) -> None:
    """Advance step counter, handle phase transitions, ramp gains."""
    state.step += 1
    step_in_bar = (state.step - 1) % STEPS_PER_BAR
    bar = (state.step - 1) // STEPS_PER_BAR

    if step_in_bar == 0 and state.step > STEPS_PER_BAR:
        state.phase_bar += 1
        phase_len = INTRO_BARS if state.phase == "Intro" else PHASE_BARS
        if state.phase_bar >= phase_len:
            idx = PHASE_SEQUENCE.index(state.phase)
            next_idx = (idx + 1) % len(PHASE_SEQUENCE)
            if next_idx == 0:
                next_idx = 1
            state.phase = PHASE_SEQUENCE[next_idx]
            state.phase_bar = 0
            # Silence beat before Drop
            if state.phase == "Drop":
                for v in ("kick", "hihat", "clap", "pad", "lead", "pulse"):
                    setattr(state, f"{v}_gain", 0.0)

    # Ramp voice gains toward phase targets
    target = PHASE_GAINS[state.phase]
    for v in ("kick", "hihat", "clap", "pad", "lead", "pulse"):
        cur = getattr(state, f"{v}_gain")
        tgt = target[v]
        setattr(state, f"{v}_gain", cur + (tgt - cur) * 0.05)

    # Sidechain recovery
    state.sidechain_env = min(1.0, state.sidechain_env + 1.0 / SIDECHAIN_STEPS)

    # Master volume ramp
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

    state = ArrangementState()
    lead_delay = FeedbackDelay()
    pad_reverb_l = SimpleFDN()
    pad_reverb_r = SimpleFDN()
    lead_reverb_l = SimpleFDN()
    lead_reverb_r = SimpleFDN()

    kick_notes:  list[PrerenderedNote] = []
    hihat_notes: list[PrerenderedNote] = []
    clap_notes:  list[PrerenderedNote] = []

    # Pre-generate a kick and clap so they're ready
    kick_l, kick_r = synthesise_kick()
    clap_l, clap_r = synthesise_clap()

    rng = random.Random(args.seed)
    noise_rng = np.random.default_rng(int(hashlib.md5(args.seed.encode()).hexdigest(), 16) & 0xFFFFFFFF)

    fade_out = False
    fade_out_steps = PHASE_BARS * STEPS_PER_BAR
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
                state.master_vol -= args.volume / (fade_out_steps)
                if state.master_vol <= 0.0:
                    state.master_vol = 0.0
                    if not wav_mode:
                        stream.write(np.zeros((samples_per_step, 2), dtype=np.float32))
                    break
            else:
                advance_arrangement(state, args.volume)

            # ----------------------------------------------------------------
            # Current chord
            # ----------------------------------------------------------------
            chord = chord_for_bar(bar)   # [root, third, fifth] MIDI notes

            # ----------------------------------------------------------------
            # Kick — steps {0,4,8,11,14}
            # ----------------------------------------------------------------
            kick_l_step = np.zeros(samples_per_step, dtype=np.float32)
            kick_r_step = np.zeros(samples_per_step, dtype=np.float32)
            if step_in_bar in KICK_STEPS and state.kick_gain > 0.01:
                kl, kr = synthesise_kick()
                kick_notes.append(PrerenderedNote(kl, kr))
                if state.sidechain_env > SIDECHAIN_DEPTH:
                    state.sidechain_env = SIDECHAIN_DEPTH
                midi.addNote(0, 4, 36, beat_time, STEP_BEATS, 100)
            kl, kr = drain_notes(kick_notes, samples_per_step)
            kick_l_step = kl * state.kick_gain * KICK_LEVEL
            kick_r_step = kr * state.kick_gain * KICK_LEVEL

            # ----------------------------------------------------------------
            # Hi-hat — every step, variable decay
            # ----------------------------------------------------------------
            decay = hihat_decay(step_in_bar, bar)
            hl, hr = synthesise_hihat(decay)
            hihat_notes.append(PrerenderedNote(hl, hr))
            hml, hmr = drain_notes(hihat_notes, samples_per_step)
            # Slight stereo panning — alternates left/right
            pan = 0.7 if step_in_bar % 2 == 0 else 0.3
            hihat_l_step = hml * state.hihat_gain * HIHAT_LEVEL * pan
            hihat_r_step = hmr * state.hihat_gain * HIHAT_LEVEL * (1.0 - pan)

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
            # Pad — retrigger every step (seg 16) with acidenv + trancegate
            # Research: .seg(16) = retrigger every 16th note.
            # Voices: chord root + add("-14,-21") spread.
            # ----------------------------------------------------------------
            pad_l_step = np.zeros(samples_per_step, dtype=np.float32)
            pad_r_step = np.zeros(samples_per_step, dtype=np.float32)

            if state.pad_gain > 0.01:
                # Pad note = chord root + pad voicing offsets
                pad_root = chord[0]   # chord root MIDI
                pad_notes = [pad_root, pad_root - 14, pad_root - 21]

                # (Re)init oscillator state when chord changes
                if step_in_bar == 0 and bar % CHORD_BARS == 0:
                    state.pad_osc_phases = [None, None, None]
                    state.pad_iir_states = [None, None, None]
                    state.pad_current_notes = list(pad_notes)

                # Retrigger envelope and filter envelope every step (seg 16)
                amp_env = acidenv(samples_per_step, amount=0.55)
                cut_env = lpenv(samples_per_step, PAD_CUTOFF_BASE)

                # Trancegate applied after render
                gate_env = trancegate_envelope(step_in_bar, samples_per_step)

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

                # Apply trancegate and sidechain
                pad_l_step *= gate_env * state.sidechain_env
                pad_r_step *= gate_env * state.sidechain_env

                # Reverb
                pad_l_step = pad_reverb_l.process(pad_l_step, wet=0.25)
                pad_r_step = pad_reverb_r.process(pad_r_step, wet=0.25)

                pad_l_step *= state.pad_gain * PAD_LEVEL
                pad_r_step *= state.pad_gain * PAD_LEVEL

            # ----------------------------------------------------------------
            # Lead — notearp pattern, acidenv, FM brown noise, heavy delay
            # Research: notearp("< <- - - -> 0 1@2 0 1 0 1>*16"),
            #           .fm(.5).fmwave("brown"), .delay(.7).delayfeedback(.8)
            # ----------------------------------------------------------------
            lead_l_step = np.zeros(samples_per_step, dtype=np.float32)
            lead_r_step = np.zeros(samples_per_step, dtype=np.float32)

            if state.lead_gain > 0.01:
                arp_tone_idx = NOTEARP[step_in_bar]

                if arp_tone_idx >= 0:
                    note = chord[min(arp_tone_idx, len(chord) - 1)]
                    # Brown noise FM buffer for this note
                    fm_buf = _brown_noise(samples_per_step, seed=state.brown_seed)
                    state.brown_seed = (state.brown_seed + 1) % 65536

                    # Reset oscillator and filter state on each note trigger
                    state.lead_osc_phases = np.zeros(SAW_COUNT, dtype=np.float32)
                    state.lead_iir_state  = np.zeros(2, dtype=np.float32)

                    amp_env = acidenv(samples_per_step, amount=0.60)
                    cut_env = lpenv(samples_per_step, LEAD_CUTOFF_BASE)

                    bl, br, new_phases, new_iir = synthesise_supersaw(
                        note, samples_per_step, cut_env, amp_env,
                        osc_phases=state.lead_osc_phases,
                        iir_state=state.lead_iir_state,
                        fm_noise=fm_buf,
                    )
                    state.lead_osc_phases = new_phases
                    state.lead_iir_state  = new_iir

                    lead_l_step = bl
                    lead_r_step = br

                    midi.addNote(0, 0, note, beat_time, STEP_BEATS, 75)
                else:
                    # No new note — render silence (delay will fill it)
                    pass

                # Apply feedback delay (heavy wet)
                lead_l_step, lead_r_step = lead_delay.process(lead_l_step, lead_r_step)

                # Sidechain
                lead_l_step *= state.sidechain_env
                lead_r_step *= state.sidechain_env

                # Reverb (lighter on lead — delay already adds space)
                _lw = 0.30 if state.phase == "Breakdown" else 0.12
                lead_l_step = lead_reverb_l.process(lead_l_step, wet=_lw)
                lead_r_step = lead_reverb_r.process(lead_r_step, wet=_lw)

                lead_l_step *= state.lead_gain * LEAD_LEVEL
                lead_r_step *= state.lead_gain * LEAD_LEVEL

            # ----------------------------------------------------------------
            # Pulse texture — every step, FM-modulated
            # Research: s("pulse!16").dec(.1).fm(time).fmh(time)
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

            # NaN guard
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

            # Terminal line
            if step_in_bar == 0:
                chord_name = ["Gm", "Cm", "A#", "Dm"][(bar // CHORD_BARS) % 4]
                print(
                    f"[v2] [Bar {bar+1:4d}] [{state.phase[:4]}] [{chord_name}]"
                    f"  K:{state.kick_gain:.2f} H:{state.hihat_gain:.2f}"
                    f" P:{state.pad_gain:.2f} L:{state.lead_gain:.2f}"
                    f"  vol={state.master_vol:.2f}"
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
