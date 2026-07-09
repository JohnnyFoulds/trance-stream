from __future__ import annotations

# song/theory.py
# All values sourced from docs/music_theory/ — do not change without updating the docs.

# ---------------------------------------------------------------------------
# SCALES
# ---------------------------------------------------------------------------

# Source: docs/music_theory/01_trance_harmony.md §1
SCALES = {
    'natural_minor': [0, 2, 3, 5, 7, 8, 10],   # Aeolian
    'dorian':        [0, 2, 3, 5, 7, 9, 10],
    'major':         [0, 2, 4, 5, 7, 9, 11],
}

# ---------------------------------------------------------------------------
# FILTER CONSTANTS
# ---------------------------------------------------------------------------

def rlpf_to_hz(slider: float) -> float:
    """SA's exact rlpf formula: (slider * 12) ** 4 Hz.
    Source: docs/music_theory/02_sa_vocabulary_codified.md §5
    Confirmed: slider=0.877 → ~12267 Hz (SA's full_open value).
    """
    return (slider * 12.0) ** 4


# Source: docs/music_theory/02_sa_vocabulary_codified.md §5
FILTER_ARC = {
    'start':      0.45,   # session opens, moderate brightness
    'mid':        0.60,   # warming up
    'pullback':   0.35,   # deliberate dark moment
    'full_open':  0.877,  # SA's confirmed OCR value; rlpf_to_hz(0.877) ≈ 12267 Hz
    'lead_base':  0.593,  # SA's confirmed OCR value; rlpf_to_hz(0.593) ≈ 2563 Hz
}

FILTER_ARC_TIMING = {
    'start_to_mid_bars':  40,
    'pullback_duration':   8,
    'final_open_bar':     96,
}

FM_ARC_ONSET_BAR = 96
FM_ARC_TARGET    = 0.55

# ---------------------------------------------------------------------------
# CHORD PROGRESSIONS
# ---------------------------------------------------------------------------

# Scale degrees, 0-indexed from root.
# In G natural minor: 0=G, 1=A, 2=Bb, 3=C, 4=D, 5=Eb, 6=F.

# Source: docs/music_theory/01_trance_harmony.md §2, docs/music_theory/02_sa_vocabulary_codified.md §1
PROGRESSIONS = {
    'uplifting':    [[0], [5], [2], [4]],
    'dark':         [[0], [3], [0], [6]],
    'acid':         [[0], [2], [3], [2]],
    'progressive':  [[0], [3], [4], [1]],
    'sa_canonical': [[3], [4], [5], [6]],
    # degrees 3→4→5→6 in G minor = C→D→Eb→F
    # asymmetric timing in SA's pattern: C@3 D@1 Eb@3 F@1 (degrees 3 and 5 held 3×)
}

PAD_CHORD_WEIGHTS = [3, 1, 3, 1]  # relative durations of sa_canonical degrees

# ---------------------------------------------------------------------------
# PAD VOICING
# ---------------------------------------------------------------------------

# SA's .add("-14,-21") — sub-bass doublings fill low register
# Source: docs/music_theory/02_sa_vocabulary_codified.md §1
PAD_VOICING_OFFSETS = [0, -14, -21]

# ---------------------------------------------------------------------------
# NOTEARP PATTERN
# ---------------------------------------------------------------------------

# SA's confirmed pattern from 3fpx7Scysw4, across 128 snapshots, never changed.
# The outer pattern `< <- - - -> 0 1@2 0 1 0 1>*16` creates:
# - 4 rests (positions 0-3): "back-loaded" rhythm
# - Then: 0, 1, 1, 0, 1, 0, 1 at positions 4-10+ (approximate mapping)
# Map to a 16-step grid. -1 = rest, 0 = first chord tone, 1 = second chord tone.

# Source: docs/music_theory/04_generative_melody.md §2
SA_NOTEARP_PATTERN = [-1, -1, -1, -1, 0, -1, -1, -1, 0, 1, 1, 0, 1, 0, 1, 0]

# ---------------------------------------------------------------------------
# DRUM PATTERNS
# ---------------------------------------------------------------------------

# Source: docs/music_theory/03_trance_rhythm.md §1
KICK_STEPS_BASIC      = [0, 4, 8, 12]          # four-on-floor
KICK_STEPS_SYNCOPATED = [0, 4, 8, 11, 14]      # SA's trance pump pattern
CLAP_STEPS_BACKBEAT   = [4, 12]                # beats 2 and 4
CLAP_STEPS_SYNCOPATED = [0, 4, 8, 11, 14]     # matches kick (some SA sessions)
HIHAT_STEPS           = list(range(16))        # all 16th notes (full pattern)
HIHAT_STEPS_OFFBEAT   = [2, 6, 10, 14]        # offbeat 8th notes — sparse/hypnotic
HIHAT_STEPS_SPARSE    = [0, 4, 8, 12]         # straight 8th notes — basic groove
HIHAT_DECAY_S_BASE    = 0.08
HIHAT_DECAY_S_MIN     = 0.05
HIHAT_DECAY_S_MAX     = 0.12

# ---------------------------------------------------------------------------
# TRANCEGATE
# ---------------------------------------------------------------------------

# Source: docs/music_theory/03_trance_rhythm.md §4
TRANCEGATE_SPEED  = 1.5    # cycles per bar — creates 3/2 polyrhythm vs 4/4
TRANCEGATE_ANGLE  = 45.0   # degrees — cosine shape, equal rise/fall time
TRANCEGATE_AMOUNT = 1.0    # full depth

# ---------------------------------------------------------------------------
# SIDECHAIN
# ---------------------------------------------------------------------------

# Source: docs/music_theory/03_trance_rhythm.md §5
# SA's confirmed .duck().duckattack(.16).duckdepth(.6)
SIDECHAIN_DEPTH    = 0.6    # pad reduces to 0.4 gain on kick hit
SIDECHAIN_ATTACK_S = 0.16   # recovery time constant (exponential)

# ---------------------------------------------------------------------------
# GAIN VALUES
# ---------------------------------------------------------------------------

# Source: docs/music_theory/02_sa_vocabulary_codified.md §7
# SA's OCR values are Strudel gain multipliers — our synthesizer outputs at a
# different amplitude than SA's SuperDirt sampler, so we scale up melodic
# instruments so they're audible against the kick. Kick stays at 1.0.
GAIN_KICK  = 1.00   # .gain(1) — SA's confirmed value, unchanged
GAIN_PAD   = 1.50   # scaled: our supersaw outputs ~3× quieter than SA's sampler
GAIN_LEAD  = 0.90   # balanced: lead audible but doesn't overload brightness
GAIN_BASS  = 1.20   # scaled: bass needs presence in the mix
GAIN_HIHAT = 0.50   # .gain(.5) — SA confirmed
GAIN_CLAP  = 0.70   # .pg(.7) — SA confirmed
GAIN_PULSE = 0.12

# ---------------------------------------------------------------------------
# BUILD ORDER
# ---------------------------------------------------------------------------

# Source: docs/music_theory/02_sa_vocabulary_codified.md §6
# Bars at 140 BPM. Derived from GWXCCBsOMSg session timing.
STAGE_BARS_DEFAULT = {
    'kick_on':         0,
    'pad_root_on':     2,
    'bass_on':         4,    # acid bass enters early — the harmonic spine
    'lead_root_on':    8,
    'lead_melody_on':  16,
    'pad_chord_on':    20,
    'lead_voicing_on': 32,
    'clap_on':         56,
    'fm_on':           88,
    'pulse_on':        100,
    'hihat_on':        112,
    'kick_syncopated': 116,
}

# ---------------------------------------------------------------------------
# MOOD MAPPINGS
# ---------------------------------------------------------------------------

MOOD_TO_SCALE = {
    'uplifting':   'natural_minor',
    'dark':        'natural_minor',
    'acid':        'natural_minor',
    'dreamy':      'dorian',
    'progressive': 'major',
}

MOOD_TO_PROGRESSION = {
    'uplifting':   'uplifting',
    'dark':        'dark',
    'acid':        'acid',
    'dreamy':      'sa_canonical',
    'progressive': 'progressive',
}

# ---------------------------------------------------------------------------
# TIMING CONSTANTS
# ---------------------------------------------------------------------------

# Source: docs/music_theory/03_trance_rhythm.md — computed from 140 BPM
BPM = 140.0
SR  = 44100


def samples_per_bar(bpm: float = BPM, sr: int = SR) -> int:
    """Number of samples in one 4/4 bar at given BPM."""
    return int(sr * 4 * 60 / bpm)


def samples_per_beat(bpm: float = BPM, sr: int = SR) -> int:
    return int(sr * 60 / bpm)


def samples_per_sixteenth(bpm: float = BPM, sr: int = SR) -> int:
    return int(sr * 60 / (bpm * 4))


# ---------------------------------------------------------------------------
# MUSIC THEORY HELPERS
# ---------------------------------------------------------------------------

def degree_to_midi(degree: int, root_midi: int, scale: list) -> int:
    """Convert a 0-indexed scale degree to an absolute MIDI note.

    Handles degrees > len(scale) by moving up octaves.
    Source: docs/music_theory/02_sa_vocabulary_codified.md §1
    """
    octave, step = divmod(degree, len(scale))
    return root_midi + octave * 12 + scale[step]


def chord_to_midi(degrees: list, root_midi: int, scale: list) -> list:
    """Convert a list of scale degrees to MIDI notes."""
    return [degree_to_midi(d, root_midi, scale) for d in degrees]
