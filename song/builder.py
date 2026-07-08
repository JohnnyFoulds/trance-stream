# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# song/builder.py
# Assembles a Song from a seed string and mood, using theory.py constants.

from __future__ import annotations
import hashlib
from song.theory import (
    SCALES, PROGRESSIONS, PAD_CHORD_WEIGHTS, SA_NOTEARP_PATTERN,
    STAGE_BARS_DEFAULT, FILTER_ARC, MOOD_TO_SCALE, MOOD_TO_PROGRESSION,
    GAIN_KICK, GAIN_PAD, GAIN_LEAD, GAIN_BASS, GAIN_HIHAT, GAIN_CLAP, GAIN_PULSE,
    BPM, SR,
)

# Notearp pattern pool — different rhythmic feels.
# Each pattern is 16 steps: -1=rest, 0=first chord tone, 1=second chord tone.
# Source: docs/music_theory/04_generative_melody.md
_NOTEARP_PATTERNS = [
    [-1, -1, -1, -1,  0, -1, -1, -1,  0,  1,  1,  0,  1,  0,  1,  0],  # SA canonical: back-loaded
    [ 0, -1,  0, -1,  0, -1,  1, -1,  0, -1,  0,  1,  0, -1,  1, -1],  # even 8ths with accents
    [-1,  0, -1, -1,  1, -1,  0, -1, -1,  0,  1, -1,  0,  1,  0,  1],  # syncopated push
    [ 0, -1, -1,  1,  0, -1,  0, -1,  1, -1,  0, -1,  1,  0, -1,  1],  # offbeat heavy
    [-1, -1,  0, -1, -1,  1,  0, -1,  0, -1,  1,  0, -1,  0,  1,  0],  # mid-bar entry
]

# Chord progression pool per mood — multiple options so seed varies the harmony.
# Source: docs/music_theory/01_trance_harmony.md §2
_PROGRESSIONS_BY_MOOD = {
    'uplifting':   [
        [[0], [5], [2], [4]],   # i – VI – III – v  (euphoric)
        [[0], [3], [5], [4]],   # i – iv – VI – v
        [[0], [6], [3], [5]],   # i – VII – iv – VI
    ],
    'dark':        [
        [[0], [3], [0], [6]],   # i – iv – i – VII  (tension loop)
        [[0], [6], [5], [3]],   # i – VII – VI – iv
        [[0], [5], [3], [6]],   # i – VI – iv – VII
    ],
    'acid':        [
        [[0], [2], [3], [2]],   # i – III – iv – III (hypnotic)
        [[0], [3], [2], [0]],   # i – iv – III – i
        [[0], [2], [5], [3]],   # i – III – VI – iv
    ],
    'dreamy':      [
        [[3], [4], [5], [6]],   # SA canonical in dorian
        [[0], [4], [5], [2]],   # I – V – VI – III
        [[0], [5], [3], [4]],   # I – VI – IV – V
    ],
    'progressive': [
        [[0], [3], [4], [1]],   # I – IV – V – ii
        [[0], [4], [5], [3]],   # I – V – VI – IV
        [[0], [1], [5], [4]],   # I – ii – VI – V
    ],
}

# BPM range per mood — seed picks within the range.
# Source: docs/music_theory/01_trance_harmony.md — trance BPM conventions
_BPM_RANGE = {
    'uplifting':   (138, 142),
    'dark':        (136, 140),
    'acid':        (138, 145),
    'dreamy':      (128, 136),
    'progressive': (128, 138),
}


def build_song(seed: str, mood: str = 'uplifting', bpm: float = None,
               total_bars: int = 128) -> 'Song':
    """Build a Song from a seed and mood.

    Seed drives: root note, BPM (within mood range), chord progression
    variant, notearp pattern, stage timing jitter, pullback bar, drum seed.
    Mood drives: scale, BPM range, progression pool.
    """
    from song.song import Song
    from song.track import Track
    from song.arcs import filter_cutoff_arc, fm_depth_arc, delay_wet_arc, hihat_decay_arc

    # Deterministic RNG from seed
    digest_int = int(hashlib.md5(seed.encode()).hexdigest(), 16)

    def _hash_bits(shift: int, bits: int) -> int:
        """Extract `bits` bits from digest_int at position `shift`."""
        return (digest_int >> shift) & ((1 << bits) - 1)

    # Root note: 48 + (hash mod 12) → C3..B3
    root_midi = 48 + (_hash_bits(0, 4) % 12)

    # Scale from mood
    scale = SCALES[MOOD_TO_SCALE[mood]]

    # BPM: seed picks within mood's range (unless caller overrides)
    if bpm is None:
        bpm_lo, bpm_hi = _BPM_RANGE[mood]
        bpm = bpm_lo + (_hash_bits(8, 8) % (bpm_hi - bpm_lo + 1))

    # Chord progression: seed selects from mood's pool
    prog_pool = _PROGRESSIONS_BY_MOOD[mood]
    chord_prog = prog_pool[_hash_bits(16, 4) % len(prog_pool)]

    # Notearp pattern: seed selects from pool
    notearp = _NOTEARP_PATTERNS[_hash_bits(20, 4) % len(_NOTEARP_PATTERNS)]

    # Stage timing: jitter STAGE_BARS_DEFAULT ±4 bars
    def jitter(base: int, idx: int, max_j: int = 4) -> int:
        offset = int(_hash_bits(24 + idx * 4, 4) % (2 * max_j + 1)) - max_j
        return max(0, base + offset)

    stage_items = list(STAGE_BARS_DEFAULT.items())
    stage_bars = {k: jitter(v, i) for i, (k, v) in enumerate(stage_items)}
    stage_bars['kick_on'] = 0
    prev = 0
    for key in ['kick_on', 'pad_root_on', 'lead_root_on', 'lead_melody_on',
                'pad_chord_on', 'lead_voicing_on', 'clap_on', 'fm_on',
                'pulse_on', 'hihat_on', 'kick_syncopated']:
        if key in stage_bars:
            stage_bars[key] = max(stage_bars[key], prev + (1 if prev > 0 else 0))
            prev = stage_bars[key]

    # Pullback bar: somewhere between bar 48 and 80
    filter_pb_bar = 48 + int(_hash_bits(80, 5) % 32)

    # Drum seed: varies so each song has different noise texture on drums
    drum_seed = _hash_bits(88, 16)

    tracks = _build_tracks(stage_bars, root_midi, scale, chord_prog,
                           filter_pb_bar, drum_seed=drum_seed, sr=SR)

    return Song(
        bpm=float(bpm),
        root_midi=root_midi,
        scale=scale,
        chord_prog=chord_prog,
        chord_weights=PAD_CHORD_WEIGHTS,
        notearp_pattern=notearp,
        tracks=tracks,
        stage_bars=stage_bars,
        filter_pb_bar=filter_pb_bar,
        seed=seed,
        mood=mood,
        total_bars=total_bars,
        sr=SR,
    )


def _build_tracks(stage_bars: dict, root_midi: int, scale: list,
                  chord_prog: list, filter_pb_bar: int,
                  drum_seed: int = 42, sr: int = SR) -> list:
    """Instantiate all instrument tracks with their arc functions."""
    from song.track import Track
    from song.arcs import filter_cutoff_arc, fm_depth_arc, hihat_decay_arc, gain_arc
    from instruments.drums import DrumKit

    tracks = []

    # Kick + hihat + clap share one DrumKit instance, seeded per-song
    kit = DrumKit(seed=drum_seed, sr=sr)

    tracks.append(Track(
        instrument=kit,
        instrument_type='kick',
        active_from_bar=stage_bars['kick_on'],
        gain_target=GAIN_KICK,
    ))

    # Pad
    try:
        from instruments.pad import SupersawPad
        pad = SupersawPad(root_midi=root_midi, sr=sr)
        tracks.append(Track(
            instrument=pad,
            instrument_type='pad',
            active_from_bar=stage_bars['pad_root_on'],
            gain_target=GAIN_PAD,
            arc_fn=lambda bar: {'cutoff_slider': filter_cutoff_arc(bar, filter_pb_bar)},
        ))
    except ImportError:
        pass

    # Lead
    try:
        from instruments.lead import AcidLead
        lead = AcidLead(root_midi=root_midi, sr=sr)
        tracks.append(Track(
            instrument=lead,
            instrument_type='lead',
            active_from_bar=stage_bars['lead_root_on'],
            gain_target=GAIN_LEAD,
            arc_fn=lambda bar: {
                'cutoff_slider': filter_cutoff_arc(bar, filter_pb_bar),
                'fm_depth': fm_depth_arc(bar),
            },
        ))
    except ImportError:
        pass

    return tracks
