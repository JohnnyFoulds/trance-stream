# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
#
# Source: https://github.com/JohnnyFoulds/retro-game-stream
"""Procedural trance music generator in the style of Switch Angel's live sets.

Streams stereo audio to the system output device in real time, exports MIDI on
exit, and participates in the ``stream_dj.py`` crossfade ecosystem via flag-file
IPC.  Run ``python trance_stream.py --help`` for CLI options.  Write
``fade_<pid>.flag`` to trigger a graceful 4-bar fade-out and clean exit.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import logging
import math
import os
import random
import sys
from dataclasses import dataclass
from typing import Optional

import numpy as np
import sounddevice as sd
from midiutil import MIDIFile

logger = logging.getLogger(__name__)

# --- CLI ARGUMENT PARSER ---

parser = argparse.ArgumentParser(description="Procedural Trance Stream")
parser.add_argument(
    "-m", "--mood",
    type=str,
    default="uplifting",
    choices=["uplifting", "dark", "acid", "progressive", "ambient"],
    help="Harmonic mood / chord progression",
)
parser.add_argument(
    "-b", "--bpm",
    type=int,
    default=140,
    help="Tempo in BPM (120-150)",
)
parser.add_argument(
    "-s", "--seed",
    type=str,
    default="center",
    help="Text seed for deterministic generation",
)
parser.add_argument(
    "-v", "--volume",
    type=float,
    default=0.90,
    help="Master volume (0.0-1.0)",
)
parser.add_argument(
    "--fade_in",
    type=int,
    default=0,
    help="Fade in over N bars (used by DJ script)",
)
parser.add_argument(
    "-o", "--out_midi",
    type=str,
    default=None,
    help="MIDI output file path",
)
parser.add_argument(
    "--bars",
    type=int,
    default=0,
    help="Stop after N bars (0 = infinite)",
)
parser.add_argument(
    "--wav",
    type=str,
    default=None,
    metavar="PATH",
    help="Render to WAV file instead of live audio output",
)
args = parser.parse_args()

# --- CONFIGURATION & TIME SCALING ---

SAMPLE_RATE: int = 44100
STEP_BEATS: float = 0.25          # one 16th note in beats
STEPS_PER_BAR: int = 16
BEATS_PER_BAR: int = 4
CA_RULE: int = 30
CA_WIDTH: int = 32

# Register boundaries (MIDI note numbers)
BASS_LOW: int = 36    # C2
BASS_HIGH: int = 60   # C4
LEAD_LOW: int = 60    # C4  — expanded to two octaves for melodic range
LEAD_HIGH: int = 84   # C6
ARP_LOW: int = 72     # C5  — arp soars above the lead (trance convention)
ARP_HIGH: int = 96    # C7
PAD_LOW: int = 62     # D4 — mid-register anchor note for pad
PAD_HIGH: int = 74    # D5

# Phrase / bar shaping
MAX_LEAD_INTERVAL: int = 7
MIN_PHRASE_BARS: int = 4
PHRASE_SHORT: int = 64    # steps (4 bars)
PHRASE_LONG: int = 128    # steps (8 bars)
REST_PROBABILITY: float = 0.15
ARP_REST_PROBABILITY: float = 0.10
BAR_DIRECTION_DESCENT_THRESHOLD: int = 5
BAR_SPARSE_THRESHOLD: int = 2

# Arrangement
PHASE_BARS: int = 16
INTRO_PHASE_BARS: int = 4     # Intro is shorter so music starts quickly
PHASE_TRANSITION_BARS: int = 2
FADE_OUT_BARS: int = 4

# MIDI
VELOCITY_MIN: int = 20
VELOCITY_MAX: int = 115
KICK_VELOCITY: int = 100
CHORD_DURATION_BARS: int = 4

# Oscillator counts and detuning (starter values; tune by ear)
SAW_COUNT_LEAD: int = 7
SAW_COUNT_BASS: int = 3
SAW_COUNT_PAD: int = 7
DETUNE_CENTS_LEAD: float = 120.0   # ~20 cents per pair across 7 saws — wide chorus
DETUNE_CENTS_BASS: float = 8.0
DETUNE_CENTS_PAD: float = 50.0

# Per-voice level trims (applied at note creation; tune by ear)
KICK_LEVEL: float = 1.00   # kick is the anchor
BASS_LEVEL: float = 0.00   # unused — low end comes from pad -14/-21 voicing
LEAD_LEVEL: float = 2.40   # 3-voice stack (÷3 per voice = 0.80 each)
ARP_LEVEL:  float = 0.90   # high-register arp
PAD_LEVEL:  float = 1.20   # pad carries the bass — needs more headroom

# Kick synthesis (starter values; tune by ear)
KICK_F0: float = 160.0    # Hz, sweep start
KICK_F1: float = 50.0     # Hz, sweep end
KICK_DECAY_S: float = 0.10   # longer body gives more thump
KICK_ENV_TAU: float = 0.035  # slower attack decay = more audible transient

# Arp synthesis
ARP_DECAY_TAU: float = 0.18
ARP_CUTOFF_HZ: float = 4500.0   # tame harshness without killing the sheen

# Sidechain (starter values; tune by ear)
SIDECHAIN_DEPTH: float = 0.05  # duck bass/pad almost to silence on kick hit
SIDECHAIN_RELEASE: int = 7     # recover in ~0.4 beat — perceptible pump at 140 BPM

# Trance gate
TGATE_SEEDS: list[int] = [
    45, 116, 99, 100, 107, 53, 57, 58,
    67, 81, 89, 115, 8, 118, 120, 149,
]
TGATE_ATTENUATION: float = 0.0   # fully mute closed slots (not just attenuate)
TGATE_RAMP_MS: float = 8.0      # 8ms ramp removes clicks without blurring the gate

# Filter LFO
LEAD_CUTOFF_BASE: float = 3500.0   # LFO audible; sweeps 1500–5500 Hz
LEAD_CUTOFF_SWEEP: float = 2000.0
LEAD_LFO_RATE: float = 0.15
BASS_CUTOFF_BASE: float = 900.0
BASS_CUTOFF_SWEEP: float = 400.0
BASS_LFO_RATE: float = 0.08
PAD_CUTOFF_BASE: float = 1800.0   # matches rlpf(0.539) ≈ 1748 Hz
PAD_CUTOFF_SWEEP: float = 600.0
PAD_LFO_RATE: float = 0.05

# Soft-clip drive (tune by ear)
DRIVE: float = 3.0   # soft-clip limiter — limits peaks to near 0 dBFS

# CA bit positions (spread across 32-wide row)
LEAD_GATE: int = 5
ARP_GATE: int = 11
PHRASE_BIT: int = 17
ARP_DIR_BIT: int = 23

# Phase target voice gains
PHASE_TARGET_GAINS: dict[str, dict[str, float]] = {
    # bass gain is always 0 — low end comes from the pad's -14/-21 voicing
    "Intro":     {"kick": 0.4, "bass": 0.0, "lead": 0.0,
                  "arp": 0.7, "pad": 0.7, "snare": 0.0},
    "Groove":    {"kick": 1.0, "bass": 0.0, "lead": 1.0,
                  "arp": 0.0, "pad": 1.0, "snare": 0.0},
    "Breakdown": {"kick": 0.0, "bass": 0.0, "lead": 0.7,
                  "arp": 1.0, "pad": 1.0, "snare": 0.0},
    "Buildup":   {"kick": 0.5, "bass": 0.0, "lead": 0.0,
                  "arp": 1.0, "pad": 1.0, "snare": 0.0},
    "Drop":      {"kick": 1.0, "bass": 0.0, "lead": 1.0,
                  "arp": 0.0, "pad": 1.0, "snare": 0.0},
}
PHASE_SEQUENCE: list[str] = [
    "Intro", "Groove", "Breakdown", "Buildup", "Drop",
]

# Bass note durations per pattern (steps)
_BASS_NOTE_STEPS: dict[str, int] = {
    "rolling": 4,
    "offbeat": 4,
    "tb303": 4,
    "broken_octave": 4,
    "sustain": CHORD_DURATION_BARS * STEPS_PER_BAR,
}

# Noise riser amplitude increment per step (Build-up only)
_NOISE_RISER_STEP: float = 1.0 / max(
    1, (PHASE_BARS - 4) * STEPS_PER_BAR
)

# MIDI GM program numbers
_GM_LEAD: int = 80
_GM_ARP: int = 80
_GM_BASS: int = 38
_GM_PAD: int = 89
_GM_KICK: int = 116

# Phase display codes (fixed 4 chars)
_PHASE_CODES: dict[str, str] = {
    "Intro":     "Intr",
    "Groove":    "Grv ",
    "Breakdown": "Bkdn",
    "Buildup":   "Bld ",
    "Drop":      "Drop",
}

# --- MUSIC THEORY: MOODS & CHORDS ---

CHORD_INTERVALS: dict[str, list[int]] = {
    "minor":  [0, 3, 7],
    "major":  [0, 4, 7],
    "minor7": [0, 3, 7, 10],
    "major7": [0, 4, 7, 11],
}

DEGREE_SEMITONES: dict[str, int] = {
    "i": 0,  "I": 0,
    "III": 3,
    "iv": 5, "IV": 5,
    "v": 7,  "V": 7,
    "VI": 8,
    "VII": 10,
}

_NOTE_NAMES: list[str] = [
    "C", "C#", "D", "D#", "E", "F",
    "F#", "G", "G#", "A", "A#", "B",
]


@dataclass
class MoodDef:
    """Definition of a harmonic mood: chord progression, bass pattern, arp direction.

    :param progression: List of ``(semitones_above_root, quality)`` pairs.
    :param bass_pattern: Named bass rhythm pattern.
    :param arp_direction: Starting arp direction: ``'up'``, ``'down'``, or
        ``'updown'``.
    """

    progression: list[tuple[int, str]]
    bass_pattern: str
    arp_direction: str


MOODS: dict[str, MoodDef] = {
    "uplifting": MoodDef(
        progression=[
            (0, "minor"), (8, "major"), (3, "major"), (10, "major"),
        ],
        bass_pattern="rolling",
        arp_direction="up",
    ),
    "dark": MoodDef(
        progression=[
            (0, "minor"), (5, "minor"), (7, "minor"), (0, "minor"),
        ],
        bass_pattern="offbeat",
        arp_direction="updown",
    ),
    "acid": MoodDef(
        progression=[
            (0, "minor"), (10, "major"), (8, "major"), (10, "major"),
        ],
        bass_pattern="tb303",
        arp_direction="up",
    ),
    "progressive": MoodDef(
        progression=[
            (0, "minor"), (5, "minor"), (0, "major"), (10, "major"),
        ],
        bass_pattern="broken_octave",
        arp_direction="down",
    ),
    "ambient": MoodDef(
        progression=[
            (0, "major7"), (10, "major7"), (8, "major7"), (10, "major7"),
        ],
        bass_pattern="sustain",
        arp_direction="up",
    ),
}


def midi_to_freq(midi_note: int) -> float:
    """Convert a MIDI note number to frequency in Hz.

    :param midi_note: MIDI note number (0-127).
    :returns: Frequency in Hz.
    """
    return 440.0 * (2.0 ** ((midi_note - 69) / 12.0))


def derive_root(seed: str) -> int:
    """Derive a deterministic MIDI root note from a text seed.

    Uses MD5 of the seed string to produce a root in ``[48, 59]`` (C3-B3).

    :param seed: CLI ``--seed`` string.
    :returns: MIDI note number for the tonic.
    """
    digest = int(hashlib.md5(seed.encode()).hexdigest(), 16)
    return 48 + (digest % 12)


def build_chord(
    root: int,
    degree_semitones: int,
    quality: str,
) -> list[int]:
    """Build chord tones in the bass register ``[BASS_LOW, BASS_HIGH]``.

    Constructs the chord from its root (``root + degree_semitones``) and the
    intervals in ``CHORD_INTERVALS[quality]``.  Any tone above ``BASS_HIGH``
    is octave-shifted down until it is within range.

    :param root: Scale root MIDI note.
    :param degree_semitones: Semitones above root to the chord root.
    :param quality: Chord quality key in ``CHORD_INTERVALS``.
    :returns: List of MIDI note numbers within ``[BASS_LOW, BASS_HIGH]``.
    """
    chord_root = root + degree_semitones
    tones = [chord_root + interval for interval in CHORD_INTERVALS[quality]]
    result = []
    for tone in tones:
        while tone > BASS_HIGH:
            tone -= 12
        while tone < BASS_LOW:
            tone += 12
        result.append(tone)
    return result


def chord_to_register(
    chord: list[int],
    low: int,
    high: int,
) -> list[int]:
    """Transpose bass-register chord tones into a target register.

    Generates ALL octave transpositions of each chord tone that fall within
    ``[low, high]``, giving the caller a full pool of candidate notes across
    the entire register rather than a single note per chord tone.  Use this
    for note-selection pools (lead, arp).

    For sustained voicings where only one chord per octave is needed, use
    :func:`chord_close_voicing` instead.

    :param chord: Bass-register chord tones (from :func:`build_chord`).
    :param low: Target register lower bound (MIDI).
    :param high: Target register upper bound (MIDI).
    :returns: Sorted, deduplicated list of MIDI notes within ``[low, high]``.
    """
    result = []
    for tone in chord:
        # Walk down to the first transposition below or at `low`
        while tone > low:
            tone -= 12
        while tone < low:
            tone += 12
        # Collect all transpositions within [low, high]
        while tone <= high:
            result.append(tone)
            tone += 12
    return sorted(set(result))


def chord_wide_voicing(
    chord: list[int],
    mid_note: int,
) -> list[int]:
    """Switch Angel's pad voicing: mid note + -14 and -21 semitones below.

    This matches her Strudel .add("-14,-21") on orbit 2. The two low notes
    ARE the bass — there is no separate bass synth in her setup. The mid note
    sits in the D4-D5 register; the low notes land in the bass/sub register
    and provide the low-end body the kick sits on top of.

    :param chord: Unused — voicing is interval-relative to mid_note.
    :param mid_note: Central MIDI note in mid register.
    :returns: Three-note list [mid-21, mid-14, mid].
    """
    return [mid_note - 21, mid_note - 14, mid_note]


def chord_close_voicing(
    chord: list[int],
    low: int,
) -> list[int]:
    """Build a close-position chord voicing starting from ``low``.

    Transposes each chord tone to the lowest octave at or above ``low``,
    keeping notes in ascending order within a single octave span.  Used for
    the pad voice where playing multiple octaves would cause muddiness.

    :param chord: Bass-register chord tones (from :func:`build_chord`).
    :param low: Target register lower bound (MIDI).
    :returns: Sorted list of MIDI notes, all within ``[low, low + 11]``.
    """
    result = []
    for tone in chord:
        while tone < low:
            tone += 12
        while tone > low + 11:
            tone -= 12
        result.append(tone)
    return sorted(set(result))


def chord_display_name(
    root: int,
    degree_semitones: int,
    quality: str,
) -> str:
    """Return a 4-character fixed-width chord name for the terminal visualiser.

    :param root: Scale root MIDI note.
    :param degree_semitones: Semitones above root to the chord root.
    :param quality: Chord quality key.
    :returns: 4-char string, e.g. ``'Am  '``, ``'Gmaj'``.
    """
    chord_root = (root + degree_semitones) % 12
    note = _NOTE_NAMES[chord_root]
    suffix = "m" if "minor" in quality else ""
    if quality == "major7":
        suffix = "M7"
    elif quality == "minor7":
        suffix = "m7"
    name = f"{note}{suffix}"
    return name.ljust(4)[:4]


def build_progression(
    root: int,
    mood: MoodDef,
) -> list[list[int]]:
    """Build the full chord progression as bass-register note lists.

    :param root: Scale root MIDI note from :func:`derive_root`.
    :param mood: Active :class:`MoodDef`.
    :returns: List of chord tone lists, one per chord in the progression.
    """
    return [
        build_chord(root, deg, qual)
        for deg, qual in mood.progression
    ]


# --- GENERATIVE ENGINE ---

def _get_next_ca_state(
    state: np.ndarray,
    rule: int,
) -> np.ndarray:
    """Advance a 1-D cellular automaton by one step using a Wolfram rule.

    Uses circular (wraparound) boundary conditions.

    :param state: Current CA row, shape ``(CA_WIDTH,)``, dtype int.
    :param rule: Wolfram rule integer (e.g. 30).
    :returns: Next CA row, same shape and dtype.
    """
    next_state = np.zeros_like(state)
    n = len(state)
    for i in range(n):
        left = state[i - 1] if i > 0 else state[n - 1]
        centre = state[i]
        right = state[i + 1] if i < n - 1 else state[0]
        idx = (left << 2) | (centre << 1) | right
        next_state[i] = (rule >> idx) & 1
    return next_state


@dataclass
class EngineState:
    """Complete generative engine state; passed through each step of the main loop.

    All fields except ``rng`` are value types or numpy arrays so the state can
    be copied cheaply.  ``rng`` is shared by reference — callers must not
    replace it.
    """

    ca_row: np.ndarray           # shape (CA_WIDTH,), dtype int
    step: int                    # global step counter (0-indexed)
    prev_lead_note: Optional[int]  # last lead MIDI note; None at phrase start
    lead_leap_pending: bool      # True → next lead note must resolve contrary
    prev_arp_index: int          # last arp pool index
    arp_direction: int           # +1 ascending, -1 descending
    phrase_step: int             # steps elapsed in current phrase
    phrase_length: int           # phrase length in steps
    phrase_high_note: int        # highest lead note in this phrase
    bar_note_count: int          # lead notes fired this bar
    bar_net_direction: int       # sum of semitone intervals this bar
    phase: str                   # arrangement phase name
    phase_bar: int               # bars elapsed in current phase
    transition_step: int         # steps remaining in gain ramp (0 = stable)
    kick_gain: float
    bass_gain: float
    lead_gain: float
    arp_gain: float
    pad_gain: float
    snare_gain: float
    sidechain_env: float         # 0.0-1.0; multiplied onto bass/pad
    lead_lfo_phase: float        # 0.0-1.0
    bass_lfo_phase: float
    pad_lfo_phase: float
    lead_tgate_pattern: list[int]
    pad_tgate_pattern: list[int]
    master_volume_current: float  # real-time master volume (tracks fade-in/out)
    fade_out_step: int           # steps elapsed since fade-out triggered (unused; reserved)
    noise_riser_amplitude: float  # Build-up white noise riser level
    rng: random.Random           # seeded RNG; sole source of musical randomness


@dataclass
class ActiveNote:
    """Live supersaw oscillator state for one sounding note.

    Held in a per-voice accumulator list; rendered each step by
    :func:`render_supersaw_step`.
    """

    osc_phases: np.ndarray  # (saw_count,) float32 phase accumulators
    iir_L: float            # IIR filter state, left channel
    iir_R: float            # IIR filter state, right channel
    gain: float             # amplitude scalar (velocity-derived)
    midi_note: int
    saw_count: int
    detune_cents: float
    steps_remaining: int    # decremented by main loop; removed at zero


@dataclass
class ArpNote:
    """Pre-computed waveform buffer for one arp or kick hit.

    Both voices pre-compute their full waveform at note-on time and consume it
    by advancing ``sample_pos`` each step.
    """

    buffer_l: np.ndarray   # float32, full note duration
    buffer_r: np.ndarray   # float32, full note duration
    sample_pos: int        # current read position


def initialise_engine(seed: str) -> EngineState:
    """Initialise the generative engine from a text seed.

    Seeds the CA row and ``EngineState.rng`` from ``seed`` so that all
    subsequent output is deterministic (FR-2).

    :param seed: CLI ``--seed`` string.
    :returns: Fully initialised :class:`EngineState`.
    """
    rng = random.Random(seed)

    ca_row = np.zeros(CA_WIDTH, dtype=int)
    if seed == "center":
        ca_row[CA_WIDTH // 2] = 1
    else:
        for i in range(CA_WIDTH):
            ca_row[i] = rng.randint(0, 1)

    intro_gains = PHASE_TARGET_GAINS["Intro"]
    lead_pat = tgate_pattern(rng.choice(TGATE_SEEDS))
    pad_pat = tgate_pattern(rng.choice(TGATE_SEEDS))

    return EngineState(
        ca_row=ca_row,
        step=0,
        prev_lead_note=None,
        lead_leap_pending=False,
        prev_arp_index=0,
        arp_direction=1,
        phrase_step=0,
        phrase_length=PHRASE_SHORT,
        phrase_high_note=LEAD_LOW,
        bar_note_count=0,
        bar_net_direction=0,
        phase="Intro",
        phase_bar=0,
        transition_step=0,
        kick_gain=intro_gains["kick"],
        bass_gain=intro_gains["bass"],
        lead_gain=intro_gains["lead"],
        arp_gain=intro_gains["arp"],
        pad_gain=intro_gains["pad"],
        snare_gain=intro_gains["snare"],
        sidechain_env=1.0,
        lead_lfo_phase=0.0,
        bass_lfo_phase=0.0,
        pad_lfo_phase=0.0,
        lead_tgate_pattern=lead_pat,
        pad_tgate_pattern=pad_pat,
        master_volume_current=0.0,
        fade_out_step=0,
        noise_riser_amplitude=0.0,
        rng=rng,
    )


def advance_engine(
    state: EngineState,
    steps_per_second: float,
) -> EngineState:
    """Advance the engine by one step and return the updated state.

    Updates the CA row, increments counters, handles phrase/bar/phase
    boundaries, ramps voice gains, advances LFO phases, and recovers the
    sidechain envelope.  Does not touch ``master_volume_current`` (owned by
    the main loop which has access to CLI args).

    :param state: Current engine state.
    :param steps_per_second: Derived from BPM; used for LFO rate conversion.
    :returns: Updated :class:`EngineState`.
    """
    # Advance CA
    state.ca_row = _get_next_ca_state(state.ca_row, CA_RULE)
    state.step += 1
    state.phrase_step += 1

    step_in_bar = (state.step - 1) % STEPS_PER_BAR  # 0-based within bar
    is_bar_start = (step_in_bar == 0)

    # Bar boundary: reset bar counters and increment phase_bar.
    # step > STEPS_PER_BAR guards against incrementing phase_bar on bar 0.
    if is_bar_start and state.step > STEPS_PER_BAR:
        state.bar_note_count = 0
        state.bar_net_direction = 0
        state.phase_bar += 1
        # Re-roll tgate patterns every bar so the gate is never mechanically
        # identical between bars (matches Switch Angel's rand-based gate).
        state.lead_tgate_pattern = tgate_pattern(
            state.rng.choice(TGATE_SEEDS)
        )
        state.pad_tgate_pattern = tgate_pattern(
            state.rng.choice(TGATE_SEEDS)
        )

        # Phase transition
        phase_len = INTRO_PHASE_BARS if state.phase == "Intro" else PHASE_BARS
        if state.phase_bar >= phase_len:
            current_idx = PHASE_SEQUENCE.index(state.phase)
            # After Intro completes, advance and skip Intro on repeat
            next_idx = (current_idx + 1) % len(PHASE_SEQUENCE)
            if next_idx == 0:  # would wrap back to Intro
                next_idx = 1   # skip to Groove
            state.phase = PHASE_SEQUENCE[next_idx]
            state.phase_bar = 0
            state.transition_step = PHASE_TRANSITION_BARS * STEPS_PER_BAR
            # Silence beat: zero all gains at the Buildup→Drop boundary so the
            # single-beat gap before the Drop lands with maximum impact.
            if state.phase == "Drop":
                for v in ("kick", "bass", "lead", "arp", "pad", "snare"):
                    setattr(state, f"{v}_gain", 0.0)
            state.lead_tgate_pattern = tgate_pattern(
                state.rng.choice(TGATE_SEEDS)
            )
            state.pad_tgate_pattern = tgate_pattern(
                state.rng.choice(TGATE_SEEDS)
            )
            state.noise_riser_amplitude = 0.0

    # Phrase boundary
    phrase_guard = MIN_PHRASE_BARS * STEPS_PER_BAR
    if (state.ca_row[PHRASE_BIT] == 1
            and state.phrase_step >= phrase_guard):
        state.phrase_step = 0
        state.phrase_length = state.rng.choice(
            [PHRASE_SHORT, PHRASE_LONG]
        )
        state.prev_lead_note = None
        state.phrase_high_note = state.phrase_high_note // 2

    # Voice gain ramps toward phase target
    if state.transition_step > 0:
        target = PHASE_TARGET_GAINS[state.phase]
        denom = float(state.transition_step)
        for voice in ("kick", "bass", "lead", "arp", "pad", "snare"):
            cur = getattr(state, f"{voice}_gain")
            tgt = target[voice]
            setattr(state, f"{voice}_gain", cur + (tgt - cur) / denom)
        state.transition_step -= 1

    # LFO phase advance
    state.lead_lfo_phase = (
        state.lead_lfo_phase + LEAD_LFO_RATE / steps_per_second
    ) % 1.0
    state.bass_lfo_phase = (
        state.bass_lfo_phase + BASS_LFO_RATE / steps_per_second
    ) % 1.0
    state.pad_lfo_phase = (
        state.pad_lfo_phase + PAD_LFO_RATE / steps_per_second
    ) % 1.0

    # Sidechain recovery
    state.sidechain_env = min(
        1.0, state.sidechain_env + 1.0 / SIDECHAIN_RELEASE
    )

    return state


def select_lead_note(
    state: EngineState,
    chord: list[int],
    step_in_bar: int,
) -> Optional[int]:
    """Select the lead melody note for the current step.

    The lead fires once per bar (step_in_bar == 0).  Instead of a random
    walk, it follows a phrase shape: a short melodic contour of scale-degree
    offsets that repeats across bars and shifts when the chord changes.

    The phrase is generated from the chord pool and a CA-seeded contour so
    each seed and chord produces a different but musically coherent phrase.

    :param state: Current engine state (mutated: updates note-tracking fields).
    :param chord: Current chord tones in bass register.
    :param step_in_bar: 0-based step index within bar (0-15).
    :returns: MIDI note in ``[LEAD_LOW, LEAD_HIGH]``, or ``None`` (hold).
    """
    # Lead fires ONCE per chord block (every CHORD_DURATION_BARS bars) and
    # holds for the full block. The trance gate creates all rhythmic movement.
    # step_in_bar is pre-advance_engine; check it is bar-start AND chord-start.
    # The chord boundary is checked via step_in_bar == 0 combined with the
    # caller having already confirmed we are at a chord boundary (is_chord_boundary).
    # We reuse the same is_chord_boundary the pad uses, passed via step context.
    # Simplest: check step_in_bar == 0 and (state.step - 1) is chord-aligned
    # (state.step was incremented by advance_engine before this call).
    chord_steps = CHORD_DURATION_BARS * STEPS_PER_BAR
    pre_advance_step = state.step - 1   # step value when note-select was triggered
    if not (step_in_bar == 0 and pre_advance_step % chord_steps == 0):
        return None

    pool = chord_to_register(chord, LEAD_LOW, LEAD_HIGH)
    if not pool:
        return None

    # Pick nearest chord tone to previous note for smooth voice-leading.
    if state.prev_lead_note is not None:
        idx = min(range(len(pool)), key=lambda i: abs(pool[i] - state.prev_lead_note))
    else:
        idx = len(pool) // 2

    note = pool[idx]
    _update_lead_state(state, note, state.prev_lead_note)
    return note


def _update_lead_state(
    state: EngineState,
    note: int,
    prev: Optional[int],
) -> None:
    """Update lead-related counters after a note is selected.

    :param state: Engine state to mutate.
    :param note: Selected MIDI note.
    :param prev: Previous MIDI note, or ``None``.
    """
    state.prev_lead_note = note
    state.bar_note_count += 1
    if prev is not None:
        state.bar_net_direction += note - prev
    if note > state.phrase_high_note:
        state.phrase_high_note = note


def select_arp_note(
    state: EngineState,
    chord: list[int],
    step_in_bar: int,
) -> Optional[int]:
    """Select the arp note for the current step.

    Steps through chord tones in the high register (ARP_LOW–ARP_HIGH) in
    strict ascending order, wrapping at the top.  The CA ARP_GATE bit gates
    individual steps (creating rhythmic gaps), and ARP_DIR_BIT flips
    direction at phrase boundaries to add variation.

    :param state: Current engine state (mutated: updates arp index/direction).
    :param chord: Current chord tones in bass register.
    :param step_in_bar: 0-based step index within bar.
    :returns: MIDI note in ``[ARP_LOW, ARP_HIGH]``, or ``None`` for a rest.
    """
    if state.ca_row[ARP_GATE] == 0:
        return None

    # Build arp pool: all chord-tone octave transpositions within register
    pool: list[int] = []
    for base in chord:
        tone = base
        while tone < ARP_LOW:
            tone += 12
        while tone <= ARP_HIGH:
            pool.append(tone)
            tone += 12
    if not pool:
        return None
    pool = sorted(set(pool))

    # Flip direction at phrase boundary
    if state.ca_row[ARP_DIR_BIT] == 1 and state.phrase_step <= 1:
        state.arp_direction *= -1

    # Advance index strictly, wrap at boundaries
    idx = state.prev_arp_index + state.arp_direction
    if idx >= len(pool):
        idx = 0
        state.arp_direction = 1
    elif idx < 0:
        idx = len(pool) - 1
        state.arp_direction = -1
    state.prev_arp_index = idx
    return pool[idx]


def select_bass_notes(
    state: EngineState,
    chord: list[int],
    step_in_bar: int,
    pattern: str,
) -> list[int]:
    """Select bass notes for the current step.

    Beat 1 (``step_in_bar == 0``) always returns the chord root (FR-14).
    Other steps follow the mood-specific ``pattern``.

    :param state: Current engine state.
    :param chord: Current chord tones in bass register (root is ``chord[0]``).
    :param step_in_bar: 0-based step index within bar (0-15).
    :param pattern: Bass pattern name.
    :returns: List of MIDI notes; may be empty on rest steps.
    """
    root = chord[0]
    fifth = chord[2] if len(chord) >= 3 else root
    # Octave of root — clamped to register
    octave = root + 12 if root + 12 <= BASS_HIGH else root - 12

    if step_in_bar == 0:
        return [root]

    if pattern == "rolling":
        return [root]

    if pattern == "offbeat":
        return [root] if step_in_bar == 10 else []

    if pattern == "tb303":
        # Root + chromatic approach on steps 6 and 12
        if step_in_bar in (6, 12):
            approach = root + 1 if root + 1 <= BASS_HIGH else root - 1
            return [approach]
        if step_in_bar in (3, 9):
            return [root]
        return []

    if pattern == "broken_octave":
        if step_in_bar == 7:
            return [octave]
        if step_in_bar == 9:
            return [root]
        if step_in_bar == 13:
            return [fifth]
        return []

    # sustain: root fires on beat 1 only (handled above); rest is silence
    return []


# --- SYNTHESIS: SUPERSAW ---

def init_supersaw(
    midi_note: int,
    velocity: float,
    saw_count: int,
    detune_cents: float,
) -> tuple[np.ndarray, float, float, float]:
    """Initialise a supersaw note's oscillator state.

    Returns the initial state for step-by-step rendering via
    :func:`render_supersaw_step`.  Does not pre-compute the waveform.

    :param midi_note: MIDI note number (21-108).
    :param velocity: Normalised amplitude (0.0-1.0).
    :param saw_count: Number of detuned sawtooth oscillators.
    :param detune_cents: Total detuning spread in cents across all oscillators.
    :returns: ``(osc_phases, iir_L, iir_R, gain)`` where ``osc_phases`` is a
        ``(saw_count,)`` float32 array initialised to 0.0.
    """
    osc_phases = np.zeros(saw_count, dtype=np.float32)
    return osc_phases, 0.0, 0.0, float(velocity)


def render_supersaw_step(
    osc_phases: np.ndarray,
    iir_L: float,
    iir_R: float,
    gain: float,
    midi_note: int,
    saw_count: int,
    detune_cents: float,
    cutoff_hz: float,
    samples_per_step: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
    """Render one step of a supersaw note.

    Advances oscillator phases, applies constant-power stereo panning, and
    runs a first-order IIR low-pass filter at ``cutoff_hz``.  Returns updated
    oscillator and filter state for the next call.

    :param osc_phases: ``(saw_count,)`` float32 phase accumulators.
    :param iir_L: IIR filter state, left channel.
    :param iir_R: IIR filter state, right channel.
    :param gain: Amplitude scalar (0.0-1.0).
    :param midi_note: MIDI note number.
    :param saw_count: Number of oscillators.
    :param detune_cents: Total detuning spread in cents.
    :param cutoff_hz: LPF cutoff for this step (LFO-modulated by caller).
    :param samples_per_step: Number of samples to render.
    :returns: ``(buf_L, buf_R, osc_phases, iir_L, iir_R)`` where the buffers
        are ``(samples_per_step,)`` float32 arrays.
    """
    # Detuning: spread oscillators symmetrically across detune_cents
    spread = detune_cents / 1200.0  # cents → octave fraction
    offsets = np.linspace(-spread / 2.0, spread / 2.0, saw_count)
    base_freq = midi_to_freq(midi_note)
    freqs = base_freq * (2.0 ** offsets)          # (saw_count,)
    delta = (freqs / SAMPLE_RATE).astype(np.float32)  # phase inc/sample

    # Build phase matrix: shape (saw_count, samples_per_step)
    t = np.arange(samples_per_step, dtype=np.float32)
    phases = osc_phases[:, None] + delta[:, None] * t[None, :]
    phases_mod = phases % 1.0
    saw = (2.0 * phases_mod - 1.0)               # bipolar sawtooth

    # Update phase accumulators to end of step
    osc_phases = (
        (osc_phases + delta * samples_per_step) % 1.0
    ).astype(np.float32)

    # Constant-power stereo panning
    pan = np.linspace(-1.0, 1.0, saw_count, dtype=np.float32)
    angle = (pan + 1.0) * (math.pi / 4.0)
    pan_l = np.cos(angle)   # (saw_count,)
    pan_r = np.sin(angle)   # (saw_count,)

    # Sum to stereo, normalise by oscillator count
    raw_l = (pan_l[:, None] * saw).sum(axis=0) / saw_count  # (N,)
    raw_r = (pan_r[:, None] * saw).sum(axis=0) / saw_count  # (N,)

    # Two-pole IIR LPF (cascade two one-poles → 12 dB/oct).
    a = (2.0 * math.pi * cutoff_hz) / (
        2.0 * math.pi * cutoff_hz + SAMPLE_RATE
    )
    one_minus_a = 1.0 - a
    buf_l = np.empty(samples_per_step, dtype=np.float32)
    buf_r = np.empty(samples_per_step, dtype=np.float32)
    iir_L2: float = 0.0
    iir_R2: float = 0.0
    for i in range(samples_per_step):
        iir_L = one_minus_a * iir_L + a * float(raw_l[i])
        iir_R = one_minus_a * iir_R + a * float(raw_r[i])
        iir_L2 = one_minus_a * iir_L2 + a * iir_L
        iir_R2 = one_minus_a * iir_R2 + a * iir_R
        buf_l[i] = iir_L2 * gain
        buf_r[i] = iir_R2 * gain

    return buf_l, buf_r, osc_phases, iir_L, iir_R


# --- SYNTHESIS: ARP ---

def synthesise_arp(
    midi_note: int,
    velocity: float,
    duration_steps: int,
    samples_per_step: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Synthesise one arp note: single sawtooth with exponential decay.

    Pre-computes the full waveform at note-on time.  No IIR filter — the arp
    is intentionally brighter than the lead.  Centre-panned (L == R).

    :param midi_note: MIDI note number.
    :param velocity: Normalised amplitude (0.0-1.0).
    :param duration_steps: Note length in steps.
    :param samples_per_step: Samples per 16th-note step.
    :returns: ``(left_wave, right_wave)`` float32 arrays.
    """
    n_samples = duration_steps * samples_per_step
    freq = midi_to_freq(midi_note)
    t = np.arange(n_samples, dtype=np.float32) / SAMPLE_RATE
    phase = (freq * t) % 1.0
    envelope = velocity * np.exp((-t / ARP_DECAY_TAU).astype(np.float32))
    raw = ((2.0 * phase - 1.0) * envelope).astype(np.float32)

    # First-order IIR LPF to remove harsh high-frequency sawtooth content
    a = (2.0 * math.pi * ARP_CUTOFF_HZ) / (
        2.0 * math.pi * ARP_CUTOFF_HZ + SAMPLE_RATE
    )
    filtered = np.empty(n_samples, dtype=np.float32)
    y = 0.0
    for i in range(n_samples):
        y = (1.0 - a) * y + a * raw[i]
        filtered[i] = y

    return filtered, filtered


# --- SYNTHESIS: KICK ---

def synthesise_kick(
    rng: random.Random,  # noqa: ARG001  reserved for future variation
) -> tuple[np.ndarray, np.ndarray]:
    """Synthesise one kick drum hit: sine sweep with exponential envelope.

    Uses an exponential (geometric) frequency sweep from ``KICK_F0`` to
    ``KICK_F1`` over ``KICK_DECAY_S`` seconds.  Centre-panned (L == R).

    :param rng: Seeded RNG from :class:`EngineState` (reserved for variation).
    :returns: ``(left_wave, right_wave)`` float32 arrays.
    """
    n = int(SAMPLE_RATE * KICK_DECAY_S * 3)
    buf = np.empty(n, dtype=np.float32)
    phase = 0.0
    freq_ratio = KICK_F1 / KICK_F0
    for i in range(n):
        t = i / SAMPLE_RATE
        freq = KICK_F0 * (freq_ratio ** (t / KICK_DECAY_S))
        phase += freq / SAMPLE_RATE
        amp = math.exp(-t / KICK_ENV_TAU)
        buf[i] = math.sin(2.0 * math.pi * phase) * amp
    return buf, buf   # centre-panned


# --- SYNTHESIS: SNARE / CLAP ---

def synthesise_snare(
    noise_rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Synthesise one snare/clap hit: band-passed noise burst.

    White noise burst decayed with a 25 ms tau, high-passed at 200 Hz and
    low-passed at 5 kHz via two IIR stages.  Used in the Buildup snare roll.

    :param noise_rng: Fast numpy RNG for noise generation.
    :returns: ``(left_wave, right_wave)`` float32 arrays.
    """
    duration_s = 0.060        # 60 ms total
    n = int(SAMPLE_RATE * duration_s)
    t = np.arange(n, dtype=np.float32) / SAMPLE_RATE

    # Noise burst with exponential decay
    raw = noise_rng.standard_normal(n).astype(np.float32)
    env = np.exp(-t / 0.025).astype(np.float32)
    buf = raw * env * 0.6

    # IIR low-pass at 5000 Hz (one-pole)
    a_lp = (2.0 * math.pi * 5000.0) / (2.0 * math.pi * 5000.0 + SAMPLE_RATE)
    y_lp: float = 0.0
    for i in range(n):
        y_lp = y_lp + a_lp * (float(buf[i]) - y_lp)
        buf[i] = np.float32(y_lp)

    # IIR high-pass at 200 Hz (one-pole): y_hp = x - x_lp where x_lp tracks dc
    a_hp = (2.0 * math.pi * 200.0) / (2.0 * math.pi * 200.0 + SAMPLE_RATE)
    y_dc: float = 0.0
    for i in range(n):
        y_dc = y_dc + a_hp * (float(buf[i]) - y_dc)
        buf[i] = np.float32(float(buf[i]) - y_dc)

    return buf, buf   # centre-panned


# --- SYNTHESIS: TRANCE GATE ---

def tgate_pattern(seed: int, length: int = 16) -> list[int]:
    """Generate a trance gate pattern with ~75% density.

    Beat positions (0, 4, 8, 12) are always open so the rhythmic pulse lands on
    the four-on-floor beats.  Off-beat positions are open with ~75% probability,
    seeded deterministically for repeatability.  This matches Switch Angel's
    ``rand.mul(1.5).round()`` gate which produces ~75% density with syncopated
    variation rather than the 50% density of a plain LFSR.

    :param seed: Integer seed for deterministic variation.
    :param length: Pattern length in steps (default 16).
    :returns: List of 0/1 integers of length ``length``.
    """
    rng = random.Random(seed)
    pattern: list[int] = []
    for i in range(length):
        if i % 4 == 0:
            pattern.append(1)   # always open on beat positions
        else:
            pattern.append(1 if rng.random() < 0.75 else 0)
    return pattern


def apply_tgate(
    buffer_l: np.ndarray,
    buffer_r: np.ndarray,
    pattern: list[int],
    step_in_bar: int,
    samples_per_step: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply a trance gate pattern to a stereo step buffer.

    The gate state for the current step is taken from ``pattern[step_in_bar]``.
    A short linear ramp (``TGATE_RAMP_MS``) is applied at the start of the
    step when the gate state changes, to prevent clicks.  The ramp direction is
    inferred from the previous step's gate state.

    :param buffer_l: Left channel float32 array, length ``samples_per_step``.
    :param buffer_r: Right channel float32 array, length ``samples_per_step``.
    :param pattern: 16-step binary gate pattern from :func:`tgate_pattern`.
    :param step_in_bar: Current step index (0-15).
    :param samples_per_step: Samples per step.
    :returns: ``(gated_left, gated_right)`` float32 arrays.
    """
    # Switch Angel uses fill().clip(.7): notes sustain into silence, then cut at
    # 70% of the slot. We model this with a smooth cosine fade-out when the next
    # slot is closed, rather than a hard chop at the slot boundary.
    current_gate = pattern[step_in_bar]
    next_gate    = pattern[(step_in_bar + 1) % 16]

    if current_gate == 0:
        # Closed slot — silence
        envelope = np.zeros(samples_per_step, dtype=np.float32)
    elif next_gate == 0:
        # Open slot but next is closed: sustain through 70% then cosine fade out
        clip_point = int(samples_per_step * 0.70)
        ramp_len   = samples_per_step - clip_point
        envelope   = np.ones(samples_per_step, dtype=np.float32)
        fade       = 0.5 * (1.0 + np.cos(
            np.linspace(0.0, math.pi, ramp_len, dtype=np.float32)
        ))
        envelope[clip_point:] = fade
    else:
        # Open slot, next also open — hold at full level
        envelope = np.ones(samples_per_step, dtype=np.float32)

    return buffer_l * envelope, buffer_r * envelope


# --- SYNTHESIS: SIDECHAIN ---

def apply_sidechain(
    buffer_l: np.ndarray,
    buffer_r: np.ndarray,
    sidechain_env: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply sidechain gain reduction to a stereo step buffer.

    Multiplies both channels by the scalar ``sidechain_env``.  The envelope
    value is already recovering each step via :func:`advance_engine`, so this
    function simply applies the current level.

    :param buffer_l: Left channel float32 array.
    :param buffer_r: Right channel float32 array.
    :param sidechain_env: Current gain scalar (0.0-1.0).
    :returns: ``(ducked_left, ducked_right)`` float32 arrays.
    """
    return buffer_l * sidechain_env, buffer_r * sidechain_env


# --- REVERB ---

_REVERB_DELAYS: list[int] = [1847, 1699, 2053, 2251]  # prime-length FDN delay lines
_REVERB_FEEDBACK: float = 0.82


class SimpleFDN:
    """Minimal 4-channel Feedback Delay Network reverb (sample-by-sample)."""

    def __init__(self) -> None:
        self.bufs = [np.zeros(d, dtype=np.float32) for d in _REVERB_DELAYS]
        self.pos   = [0] * 4

    def process(self, x: np.ndarray, wet: float = 0.25) -> np.ndarray:
        out = np.empty_like(x)
        for s in range(len(x)):
            outputs = [float(self.bufs[i][self.pos[i]]) for i in range(4)]
            mixed   = (outputs[0] + outputs[1] + outputs[2] + outputs[3]) * 0.25
            xf = float(x[s])
            for i in range(4):
                self.bufs[i][self.pos[i]] = np.float32(
                    xf * 0.015 + mixed * _REVERB_FEEDBACK
                )
                self.pos[i] = (self.pos[i] + 1) % _REVERB_DELAYS[i]
            out[s] = np.float32(xf * (1.0 - wet) + mixed * wet)
        return out


# --- NOTE ACCUMULATOR ---
# ActiveNote and ArpNote dataclasses are defined in the GENERATIVE ENGINE
# section above.  Accumulator lists are created and managed in the main loop.


# --- MIXER ---

def mix_and_limit(
    voice_buffers: list[tuple[np.ndarray, np.ndarray]],
    master_vol: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Sum stereo voice buffers, apply soft-clip limiter, scale by master volume.

    :param voice_buffers: List of ``(left, right)`` float32 array pairs, each
        exactly ``samples_per_step`` long.
    :param master_vol: Current master volume scalar (0.0-1.0).
    :returns: ``(mixed_left, mixed_right)`` float32 arrays.
    """
    if not voice_buffers:
        raise ValueError("mix_and_limit requires at least one voice buffer")

    n = len(voice_buffers[0][0])
    mix_l = np.zeros(n, dtype=np.float32)
    mix_r = np.zeros(n, dtype=np.float32)
    for buf_l, buf_r in voice_buffers:
        mix_l += buf_l
        mix_r += buf_r

    # Scale then soft-clip. tanh(x*DRIVE) keeps peak ≤ 1.0 regardless of DRIVE.
    mix_l = np.tanh(mix_l * master_vol * DRIVE)
    mix_r = np.tanh(mix_r * master_vol * DRIVE)

    return mix_l.astype(np.float32), mix_r.astype(np.float32)


# --- VELOCITY MODEL ---

def compute_velocity(
    step_in_bar: int,
    step_in_phrase: int,
    phrase_length: int,
    midi_note: int,
    phrase_high_note: int,
    rng: random.Random,
) -> int:
    """Compute MIDI velocity using a three-layer structural model.

    Layer 1: structural accent by beat position.
    Layer 2: phrase-shape climax boost when note equals the phrase peak.
    Layer 3: small random variation for organic feel.

    :param step_in_bar: 0-based step index within bar (0-15).
    :param step_in_phrase: 0-based step index within current phrase.
    :param phrase_length: Total phrase length in steps.
    :param midi_note: MIDI note being played.
    :param phrase_high_note: Highest note seen in this phrase.
    :param rng: Seeded RNG from :class:`EngineState`.
    :returns: Integer MIDI velocity in ``[VELOCITY_MIN, VELOCITY_MAX]``.
    """
    struct_map = {0: 95, 4: 80, 8: 80, 12: 80}
    v_struct = struct_map.get(step_in_bar, 65)
    denom = max(phrase_length - 1, 1)
    v_phrase = (
        int(15 * (step_in_phrase / denom))
        if midi_note >= phrase_high_note else 0
    )
    v_noise = rng.randint(-8, 8)
    raw = v_struct + v_phrase + v_noise
    return max(VELOCITY_MIN, min(VELOCITY_MAX, raw))


# --- MIDI RECORDER ---

def write_midi(midi: MIDIFile, path: Optional[str]) -> None:
    """Write the MIDI file to disk if a path was provided.

    Logs a warning to stderr if the write fails; never raises.

    :param midi: Populated :class:`MIDIFile` instance.
    :param path: Output file path, or ``None`` to skip.
    """
    if path is None:
        return
    try:
        with open(path, "wb") as fh:
            midi.writeFile(fh)
        logger.info("MIDI written to %s", path)
    except OSError as exc:
        logger.error(
            "Failed to write MIDI to %s: %s", path, exc, exc_info=True
        )


# --- TERMINAL VISUALISER ---

def print_bar_line(
    state: EngineState,
    bar: int,
    chord_nm: str,
    mood_name: str,
    master_vol: float,
) -> None:
    """Print the per-bar status line to stdout.

    Format: ``[mood] [Bar NNNN] [phase] [chord] K:n B:n L:n A:n P:n vol=V``

    :param state: Current engine state.
    :param bar: Current bar number (0-indexed; displayed as 1-indexed).
    :param chord_nm: 4-char chord name from :func:`chord_display_name`.
    :param mood_name: Active mood string.
    :param master_vol: Current master volume scalar.
    """
    phase_code = _PHASE_CODES.get(state.phase, state.phase[:4])
    k = 1 if state.kick_gain > 0.0 else 0
    b = 1 if state.bass_gain > 0.0 else 0
    lv = 1 if state.lead_gain > 0.0 else 0
    a = 1 if state.arp_gain > 0.0 else 0
    p = 1 if state.pad_gain > 0.0 else 0
    print(
        f"[{mood_name}] [Bar {bar + 1:4d}] [{phase_code}] [{chord_nm}]"
        f" K:{k} B:{b} L:{lv} A:{a} P:{p} vol={master_vol:.2f}"
    )


# --- MAIN LOOP ---

def _clamp(value: float, lo: float, hi: float) -> float:
    """Clamp ``value`` to ``[lo, hi]``.

    :param value: Input value.
    :param lo: Lower bound.
    :param hi: Upper bound.
    :returns: Clamped value.
    """
    return max(lo, min(hi, value))


def _render_accumulator(
    active: list[ActiveNote],
    cutoff_hz: float,
    samples_per_step: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Render all active supersaw notes for one step.

    Advances each note's oscillator state, sums the output, decrements
    ``steps_remaining``, and removes exhausted notes in-place.

    :param active: List of :class:`ActiveNote` instances (mutated).
    :param cutoff_hz: LPF cutoff for this step.
    :param samples_per_step: Samples per step.
    :returns: Summed ``(buf_l, buf_r)`` float32 arrays.
    """
    mix_l = np.zeros(samples_per_step, dtype=np.float32)
    mix_r = np.zeros(samples_per_step, dtype=np.float32)
    to_remove = []
    for note in active:
        bl, br, note.osc_phases, note.iir_L, note.iir_R = render_supersaw_step(
            note.osc_phases, note.iir_L, note.iir_R, note.gain,
            note.midi_note, note.saw_count, note.detune_cents,
            cutoff_hz, samples_per_step,
        )
        mix_l += bl
        mix_r += br
        note.steps_remaining -= 1
        if note.steps_remaining <= 0:
            to_remove.append(note)
    for note in to_remove:
        active.remove(note)
    return mix_l, mix_r


def _render_arp_accumulator(
    notes: list[ArpNote],
    samples_per_step: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Render all pre-computed arp/kick buffers for one step.

    Slices each buffer by the current read position, sums the slices, and
    removes exhausted entries in-place.

    :param notes: List of :class:`ArpNote` instances (mutated).
    :param samples_per_step: Samples per step.
    :returns: Summed ``(buf_l, buf_r)`` float32 arrays.
    """
    mix_l = np.zeros(samples_per_step, dtype=np.float32)
    mix_r = np.zeros(samples_per_step, dtype=np.float32)
    to_remove = []
    for note in notes:
        end = note.sample_pos + samples_per_step
        avail = len(note.buffer_l) - note.sample_pos
        if avail <= 0:
            to_remove.append(note)
            continue
        chunk = min(samples_per_step, avail)
        mix_l[:chunk] += note.buffer_l[note.sample_pos:note.sample_pos + chunk]
        mix_r[:chunk] += note.buffer_r[note.sample_pos:note.sample_pos + chunk]
        note.sample_pos = end
        if note.sample_pos >= len(note.buffer_l):
            to_remove.append(note)
    for note in to_remove:
        notes.remove(note)
    return mix_l, mix_r


def _write_wav(path: str, chunks: list[np.ndarray]) -> None:
    """Write accumulated stereo float32 chunks to a 16-bit PCM WAV file.

    :param path: Output file path.
    :param chunks: List of ``(N, 2)`` float32 arrays from the render loop.
    """
    import wave as _wave
    import struct as _struct

    if not chunks:
        logger.warning("No audio rendered; WAV not written")
        return

    data = np.concatenate(chunks, axis=0)  # (total_samples, 2)
    # Clip to [-1, 1] then scale to int16
    data = np.clip(data, -1.0, 1.0)
    pcm = (data * 32767.0).astype(np.int16)

    try:
        with _wave.open(path, "wb") as wf:
            wf.setnchannels(2)
            wf.setsampwidth(2)   # 16-bit
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(pcm.tobytes())
        logger.info("WAV written to %s (%d samples)", path, len(pcm))
    except OSError as exc:
        logger.error("Failed to write WAV to %s: %s", path, exc)


def main() -> None:
    """Entry point: validate CLI args, open audio stream, run the main loop.

    Exits with code 0 on clean stop (flag file, ``--bars``, or Ctrl+C).
    Exits with code 1 if the audio device cannot be opened.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        stream=sys.stderr,
    )

    # Validate CLI arguments before touching audio hardware
    if not 120 <= args.bpm <= 150:
        raise ValueError(
            f"--bpm must be in [120, 150]; got {args.bpm}"
        )
    if not 0.0 <= args.volume <= 1.0:
        raise ValueError(
            f"--volume must be in [0.0, 1.0]; got {args.volume}"
        )
    if args.bars < 0:
        raise ValueError(
            f"--bars must be >= 0; got {args.bars}"
        )

    # Time constants derived from BPM
    step_duration: float = (60.0 / args.bpm) * STEP_BEATS
    samples_per_step: int = int(SAMPLE_RATE * step_duration)
    steps_per_second: float = SAMPLE_RATE / samples_per_step

    # Build harmonic framework
    mood = MOODS[args.mood]
    root = derive_root(args.seed)
    progression = build_progression(root, mood)
    prog_display = [
        chord_display_name(root, deg, qual)
        for deg, qual in mood.progression
    ]

    # Initialise generative engine
    state = initialise_engine(args.seed)
    # Set initial arp direction from mood
    state.arp_direction = -1 if mood.arp_direction == "down" else 1

    # Open audio stream (or prepare WAV buffer for offline render)
    wav_mode = args.wav is not None
    wav_chunks: list[np.ndarray] = []
    mono_fallback = False
    stream = None
    if not wav_mode:
        try:
            device_info = sd.query_devices(kind="output")
            if device_info["max_output_channels"] < 2:
                logger.warning(
                    "Output device has < 2 channels; falling back to mono"
                )
                mono_fallback = True
            channels = 1 if mono_fallback else 2
            stream = sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=channels,
                dtype="float32",
            )
            stream.start()
        except sd.PortAudioError as exc:
            logger.error(
                "Failed to open audio output stream: %s", exc, exc_info=True
            )
            sys.exit(1)

    # MIDI setup
    midi = MIDIFile(1)
    midi.addTempo(0, 0, args.bpm)
    midi.addProgramChange(0, 0, 0, _GM_LEAD)
    midi.addProgramChange(0, 1, 0, _GM_ARP)
    midi.addProgramChange(0, 2, 0, _GM_BASS)
    midi.addProgramChange(0, 3, 0, _GM_PAD)
    midi.addProgramChange(0, 4, 0, _GM_KICK)

    # Note accumulators
    lead_active: list[ActiveNote] = []
    bass_active: list[ActiveNote] = []
    pad_active: list[ActiveNote] = []
    arp_notes: list[ArpNote] = []
    kick_notes: list[ArpNote] = []
    snare_notes: list[ArpNote] = []

    # Noise RNG — fast numpy generator seeded from state.rng for determinism
    noise_rng = np.random.default_rng(
        state.rng.randint(0, 2 ** 31)
    )

    # Reverb instances — separate L/R so each channel has independent diffusion.
    lead_reverb_l = SimpleFDN()
    lead_reverb_r = SimpleFDN()
    pad_reverb_l  = SimpleFDN()
    pad_reverb_r  = SimpleFDN()

    # Lead feedback delay — matches Switch Angel's .delay(0.4) on the lead orbit.
    # Delay time: 0.4 × beat duration (i.e. a dotted-8th echo).
    # Feedback: 0.35 (decays quickly, adds spatial depth without muddying).
    _beat_samples = samples_per_step * 4   # samples per quarter note
    _delay_samples = int(_beat_samples * 0.4)
    _delay_buf_l = np.zeros(_delay_samples, dtype=np.float32)
    _delay_buf_r = np.zeros(_delay_samples, dtype=np.float32)
    _delay_write_pos = 0
    _DELAY_FEEDBACK = 0.35
    _DELAY_MIX = 0.40

    # Fade scalars
    if args.fade_in > 0:
        fade_in_step_size = args.volume / (args.fade_in * STEPS_PER_BAR)
        state.master_volume_current = 0.0
    else:
        fade_in_step_size = 0.0
        state.master_volume_current = args.volume

    fade_out_step_size = args.volume / (FADE_OUT_BARS * STEPS_PER_BAR)
    fade_out_triggered = False

    # Bass pattern note steps by pattern name.
    # rolling: 1 step (retriggers every 16th; a 4-step note would overlap 4×
    # and stack the bass 4x louder than intended)
    bass_note_steps: dict[str, int] = {
        "rolling": 1,
        "offbeat": 4,
        "tb303": 4,
        "broken_octave": 4,
        "sustain": CHORD_DURATION_BARS * STEPS_PER_BAR,
    }
    nan_warned = False

    try:
        while True:
            step_in_bar = state.step % STEPS_PER_BAR
            bar = state.step // STEPS_PER_BAR
            chord_steps = CHORD_DURATION_BARS * STEPS_PER_BAR
            chord_idx = (state.step // chord_steps) % len(progression)
            chord = progression[chord_idx]
            chord_nm = prog_display[chord_idx]
            beat_time = float(state.step) * STEP_BEATS

            # a. DJ flag-file IPC
            flag_path = f"fade_{os.getpid()}.flag"
            if os.path.exists(flag_path):
                fade_out_triggered = True
                os.remove(flag_path)

            # b. --bars auto-stop
            if args.bars > 0 and state.step >= args.bars * STEPS_PER_BAR:
                fade_out_triggered = True

            # c. Advance engine
            state = advance_engine(state, steps_per_second)

            # d. LFO cutoffs
            _tau = 2.0 * math.pi
            lead_cutoff = LEAD_CUTOFF_BASE + LEAD_CUTOFF_SWEEP * math.sin(
                _tau * state.lead_lfo_phase
            )
            bass_cutoff = BASS_CUTOFF_BASE + BASS_CUTOFF_SWEEP * math.sin(
                _tau * state.bass_lfo_phase
            )
            pad_cutoff = PAD_CUTOFF_BASE + PAD_CUTOFF_SWEEP * math.sin(
                _tau * state.pad_lfo_phase
            )
            # Clamp to safe range
            lead_cutoff = _clamp(lead_cutoff, 80.0, 18000.0)
            bass_cutoff = _clamp(bass_cutoff, 80.0, 18000.0)
            pad_cutoff = _clamp(pad_cutoff, 80.0, 18000.0)

            # e. Kick
            kick_fires_groove = (
                step_in_bar % 4 == 0
                and state.phase in ("Groove", "Drop", "Intro")
            )
            kick_fires_buildup = (
                step_in_bar % 8 == 0
                and state.phase == "Buildup"
            )
            if (kick_fires_groove or kick_fires_buildup) \
                    and state.kick_gain > 0.0:
                kl, kr = synthesise_kick(state.rng)
                kick_notes.append(
                    ArpNote(buffer_l=kl, buffer_r=kr, sample_pos=0)
                )
                # Sidechain: only dip if not already below depth
                if state.sidechain_env > SIDECHAIN_DEPTH:
                    state.sidechain_env = SIDECHAIN_DEPTH
                midi.addNote(0, 4, 36, beat_time, STEP_BEATS, KICK_VELOCITY)

            # e2. Snare roll (Buildup only — escalating density per phase_bar)
            if state.phase == "Buildup" and state.snare_gain > 0.0:
                pb = state.phase_bar
                fire_snare = (
                    (pb < 4 and step_in_bar in (4, 12))           # half-note backbeat
                    or (4 <= pb < 12 and step_in_bar in (2, 6, 10, 14))  # quarter backbeat
                    or (pb >= 12 and step_in_bar % 2 == 0)        # 8th-note roll
                )
                if fire_snare:
                    sl, sr = synthesise_snare(noise_rng)
                    snare_notes.append(
                        ArpNote(buffer_l=sl, buffer_r=sr, sample_pos=0)
                    )

            # f. Bass
            if state.bass_gain > 0.0:
                bass_hits = select_bass_notes(
                    state, chord, step_in_bar, mood.bass_pattern
                )
                n_steps = bass_note_steps.get(mood.bass_pattern, 4)
                for midi_note in bass_hits:
                    vel = compute_velocity(
                        step_in_bar, state.phrase_step,
                        state.phrase_length, midi_note,
                        state.phrase_high_note, state.rng,
                    )
                    osc_ph, il, ir, gn = init_supersaw(
                        midi_note, vel / 127.0 * BASS_LEVEL,
                        SAW_COUNT_BASS, DETUNE_CENTS_BASS,
                    )
                    bass_active.append(ActiveNote(
                        osc_phases=osc_ph, iir_L=il, iir_R=ir,
                        gain=gn, midi_note=midi_note,
                        saw_count=SAW_COUNT_BASS,
                        detune_cents=DETUNE_CENTS_BASS,
                        steps_remaining=n_steps,
                    ))
                    dur_beats = n_steps * STEP_BEATS
                    midi.addNote(0, 2, midi_note, beat_time, dur_beats, vel)

            # g. Lead — fires as a 3-voice chord stack: base, +7, -7 semitones.
            # This matches Switch Angel's .add("7,-7") voicing on the lead orbit.
            if state.lead_gain > 0.0:
                lead_note = select_lead_note(state, chord, step_in_bar)
                if lead_note is not None:
                    vel = compute_velocity(
                        step_in_bar, state.phrase_step,
                        state.phrase_length, lead_note,
                        state.phrase_high_note, state.rng,
                    )
                    gain_per_voice = vel / 127.0 * LEAD_LEVEL / 3.0
                    for interval in (0, 7, -7):
                        stacked = lead_note + interval
                        osc_ph, il, ir, gn = init_supersaw(
                            stacked, gain_per_voice,
                            SAW_COUNT_LEAD, DETUNE_CENTS_LEAD,
                        )
                        lead_active.append(ActiveNote(
                            osc_phases=osc_ph, iir_L=il, iir_R=ir,
                            gain=gn, midi_note=stacked,
                            saw_count=SAW_COUNT_LEAD,
                            detune_cents=DETUNE_CENTS_LEAD,
                            steps_remaining=chord_steps,
                        ))
                        midi.addNote(
                            0, 0, stacked, beat_time,
                            chord_steps * STEP_BEATS, vel
                        )

            # h. Arp
            if state.arp_gain > 0.0:
                arp_note = select_arp_note(state, chord, step_in_bar)
                if arp_note is not None:
                    vel = _clamp(
                        70 + state.rng.randint(-8, 8),
                        VELOCITY_MIN, VELOCITY_MAX,
                    )
                    al, ar = synthesise_arp(
                        arp_note, vel / 127.0 * ARP_LEVEL, 1, samples_per_step
                    )
                    arp_notes.append(
                        ArpNote(buffer_l=al, buffer_r=ar, sample_pos=0)
                    )
                    midi.addNote(
                        0, 1, int(arp_note), beat_time, STEP_BEATS, int(vel)
                    )

            # i. Pad — triggered once per chord change (chord boundary)
            is_chord_boundary = (
                step_in_bar == 0
                and state.step % chord_steps == 0
            )
            if is_chord_boundary:
                # Clear old pad notes to avoid unbounded accumulation
                pad_active.clear()
                # Wide-spread voicing: mid chord tone + bass intervals below,
                # matching Switch Angel's .add("-14,-21") pad voicing.
                pad_mid = chord_to_register(chord, PAD_LOW, PAD_HIGH)
                pad_mid_note = pad_mid[len(pad_mid) // 2] if pad_mid else PAD_LOW
                pad_chord = chord_wide_voicing(chord, pad_mid_note)
                pad_dur = CHORD_DURATION_BARS * STEPS_PER_BAR
                for midi_note in pad_chord:
                    osc_ph, il, ir, gn = init_supersaw(
                        midi_note, PAD_LEVEL,
                        SAW_COUNT_PAD, DETUNE_CENTS_PAD,
                    )
                    pad_active.append(ActiveNote(
                        osc_phases=osc_ph, iir_L=il, iir_R=ir,
                        gain=gn, midi_note=midi_note,
                        saw_count=SAW_COUNT_PAD,
                        detune_cents=DETUNE_CENTS_PAD,
                        steps_remaining=pad_dur,
                    ))
                    midi.addNote(
                        0, 3, midi_note, beat_time,
                        pad_dur * STEP_BEATS, 80,
                    )

            # j. Render all voices into per-voice step buffers
            kick_l, kick_r = _render_arp_accumulator(
                kick_notes, samples_per_step
            )
            kick_l = kick_l * state.kick_gain * KICK_LEVEL
            kick_r = kick_r * state.kick_gain * KICK_LEVEL

            raw_bass_l, raw_bass_r = _render_accumulator(
                bass_active, bass_cutoff, samples_per_step
            )
            bass_l, bass_r = apply_sidechain(
                raw_bass_l * state.bass_gain,
                raw_bass_r * state.bass_gain,
                state.sidechain_env,
            )

            raw_lead_l, raw_lead_r = _render_accumulator(
                lead_active, lead_cutoff, samples_per_step
            )
            # Apply feedback delay before trance gate for spatial depth
            _dw = _delay_write_pos
            for _si in range(samples_per_step):
                _dr = (_dw - _delay_samples + _si) % _delay_samples
                _echo_l = _delay_buf_l[_dr]
                _echo_r = _delay_buf_r[_dr]
                _wi = (_dw + _si) % _delay_samples
                _delay_buf_l[_wi] = float(raw_lead_l[_si]) + _echo_l * _DELAY_FEEDBACK
                _delay_buf_r[_wi] = float(raw_lead_r[_si]) + _echo_r * _DELAY_FEEDBACK
                raw_lead_l[_si] = raw_lead_l[_si] * (1.0 - _DELAY_MIX) + _echo_l * _DELAY_MIX
                raw_lead_r[_si] = raw_lead_r[_si] * (1.0 - _DELAY_MIX) + _echo_r * _DELAY_MIX
            _delay_write_pos = (_delay_write_pos + samples_per_step) % _delay_samples
            lead_l, lead_r = apply_tgate(
                raw_lead_l * state.lead_gain,
                raw_lead_r * state.lead_gain,
                state.lead_tgate_pattern,
                step_in_bar,
                samples_per_step,
            )
            _lead_wet = 0.35 if state.phase == "Breakdown" else 0.15
            lead_l = lead_reverb_l.process(lead_l, wet=_lead_wet)
            lead_r = lead_reverb_r.process(lead_r, wet=_lead_wet)

            arp_l, arp_r = _render_arp_accumulator(
                arp_notes, samples_per_step
            )
            arp_l = arp_l * state.arp_gain
            arp_r = arp_r * state.arp_gain

            raw_pad_l, raw_pad_r = _render_accumulator(
                pad_active, pad_cutoff, samples_per_step
            )
            gated_pad_l, gated_pad_r = apply_tgate(
                raw_pad_l * state.pad_gain,
                raw_pad_r * state.pad_gain,
                state.pad_tgate_pattern,
                step_in_bar,
                samples_per_step,
            )
            pad_l, pad_r = apply_sidechain(
                gated_pad_l, gated_pad_r, state.sidechain_env
            )
            _pad_wet = 0.40 if state.phase == "Breakdown" else 0.25
            pad_l = pad_reverb_l.process(pad_l, wet=_pad_wet)
            pad_r = pad_reverb_r.process(pad_r, wet=_pad_wet)

            # k. Snare roll + noise riser (Build-up only)
            snare_l, snare_r = _render_arp_accumulator(
                snare_notes, samples_per_step
            )
            snare_l = snare_l * state.snare_gain
            snare_r = snare_r * state.snare_gain

            voice_buffers: list[tuple[np.ndarray, np.ndarray]] = [
                (kick_l, kick_r),
                (bass_l, bass_r),
                (lead_l, lead_r),
                (arp_l, arp_r),
                (pad_l, pad_r),
                (snare_l, snare_r),
            ]
            # l. Mix and soft-clip
            mix_l, mix_r = mix_and_limit(
                voice_buffers, state.master_volume_current
            )

            # m. Fade-in / fade-out
            if fade_out_triggered:
                state.master_volume_current -= fade_out_step_size
                if state.master_volume_current <= 0.0:
                    state.master_volume_current = 0.0
                    if not wav_mode:
                        stream.write(
                            np.zeros(
                                (samples_per_step, channels), dtype=np.float32
                            )
                        )
                    break
            elif state.master_volume_current < args.volume:
                state.master_volume_current = min(
                    args.volume,
                    state.master_volume_current + fade_in_step_size,
                )

            # n. NaN/Inf guard
            if not (np.isfinite(mix_l).all() and np.isfinite(mix_r).all()):
                if not nan_warned:
                    logger.warning(
                        "NaN/Inf in audio buffer; replacing with silence"
                    )
                    nan_warned = True
                mix_l = np.zeros(samples_per_step, dtype=np.float32)
                mix_r = np.zeros(samples_per_step, dtype=np.float32)

            # o. Write to stream or accumulate WAV buffer
            if wav_mode:
                wav_chunks.append(
                    np.column_stack([mix_l, mix_r]).astype(np.float32)
                )
            else:
                if mono_fallback:
                    audio_out = (
                        ((mix_l + mix_r) * 0.5)
                        .reshape(-1, 1)
                        .astype(np.float32)
                    )
                else:
                    audio_out = np.column_stack([mix_l, mix_r])
                stream.write(audio_out)

            # p. Terminal visualiser (once per bar, at bar start)
            if step_in_bar == 0:
                print_bar_line(
                    state, bar, chord_nm, args.mood,
                    state.master_volume_current,
                )

        # Natural exit
        if wav_mode:
            _write_wav(args.wav, wav_chunks)
        else:
            stream.stop()
            stream.close()
        write_midi(midi, args.out_midi)

    except KeyboardInterrupt:
        if wav_mode:
            _write_wav(args.wav, wav_chunks)
        else:
            stream.stop()
            stream.close()
        write_midi(midi, args.out_midi)
        sys.exit(0)

    except sd.PortAudioError as exc:
        logger.error(
            "Audio stream error during playback: %s", exc, exc_info=True
        )
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:  # noqa: BLE001
                pass
        sys.exit(1)


if __name__ == "__main__":
    main()
