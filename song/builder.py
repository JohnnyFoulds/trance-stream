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
# Each chord entry is [root_degree, fifth_degree] so notearp index 0=root, 1=fifth.
# Two distinct tones are required; with only one the notearp plays the same note
# every step — a buzzing flutter instead of melody.
# Source: docs/music_theory/01_trance_harmony.md §2
_PROGRESSIONS_BY_MOOD = {
    'uplifting':   [
        [[0, 4], [5, 2], [2, 6], [4, 1]],   # i – VI – III – v
        [[0, 4], [3, 0], [5, 2], [4, 1]],   # i – iv – VI – v
        [[0, 4], [6, 3], [3, 0], [5, 2]],   # i – VII – iv – VI
    ],
    'dark':        [
        [[0, 4], [3, 0], [0, 4], [6, 3]],   # i – iv – i – VII
        [[0, 4], [6, 3], [5, 2], [3, 0]],   # i – VII – VI – iv
        [[0, 4], [5, 2], [3, 0], [6, 3]],   # i – VI – iv – VII
    ],
    'acid':        [
        [[0, 4], [2, 6], [3, 0], [2, 6]],   # i – III – iv – III
        [[0, 4], [3, 0], [2, 6], [0, 4]],   # i – iv – III – i
        [[0, 4], [2, 6], [5, 2], [3, 0]],   # i – III – VI – iv
    ],
    'dreamy':      [
        [[3, 0], [4, 1], [5, 2], [6, 3]],   # SA canonical
        [[0, 4], [4, 1], [5, 2], [2, 6]],   # I – V – VI – III
        [[0, 4], [5, 2], [3, 0], [4, 1]],   # I – VI – IV – V
    ],
    'progressive': [
        [[0, 4], [3, 0], [4, 1], [1, 5]],   # I – IV – V – ii
        [[0, 4], [4, 1], [5, 2], [3, 0]],   # I – V – VI – IV
        [[0, 4], [1, 5], [5, 2], [4, 1]],   # I – ii – VI – V
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


def build_hey_angel_song(total_bars: int = 128) -> 'Song':
    """Build the "Hey Angel…" arrangement with exactly the analysed parameters.

    Fixed parameters from research/analysis/hey_angel_analysis.md:
    - BPM 138, root G1 (MIDI 43), G minor/dorian
    - Bass: G1 quarter-note drone + F2 eighth + portamento sweep back
    - Melody: C4→F#3 chromatic descend with slow portamento (15 sem/sec)
    - High pluck: E5 sustained, filter burst on attack
    - Sidechain: depth=0.721 (-11.1 dB trough)
    - Kick: half-time pattern (steps 0, 8 only)
    """
    from song.song import Song
    from song.track import Track
    from instruments.drums import DrumKit
    from instruments.bass import AcidBass
    from instruments.lead import AcidLead
    from instruments.pluck import HighPluck
    from song.theory import (
        SCALES, GAIN_KICK, GAIN_PAD, GAIN_LEAD, GAIN_BASS, GAIN_HIHAT,
        SIDECHAIN_DEPTH_HEY_ANGEL,
    )

    # G1 = MIDI 43 (G below middle C, two octaves below G3=55)
    # G natural minor scale
    root_midi = 43
    scale = SCALES['natural_minor']

    stage_bars = {
        'kick_on':         0,
        'pad_root_on':     9999,   # no pad in Hey Angel
        'bass_on':         0,
        'lead_root_on':    0,
        'lead_melody_on':  0,
        'pad_chord_on':    9999,
        'lead_voicing_on': 9999,
        'clap_on':         9999,
        'fm_on':           9999,
        'pulse_on':        9999,
        'hihat_on':        9999,
        'kick_syncopated': 9999,
    }

    tracks = []

    kit = DrumKit(seed=42, sr=SR,
                  kick_decay_s=0.25,
                  kick_pitch_floor=50.0)
    tracks.append(Track(
        instrument=kit,
        instrument_type='kick',
        active_from_bar=0,
        gain_target=GAIN_KICK,
    ))

    bass = AcidBass(sr=SR)
    tracks.append(Track(
        instrument=bass,
        instrument_type='bass',
        active_from_bar=0,
        gain_target=GAIN_BASS,
    ))

    # Melody lead: smooth character, slower acidenv, portamento handled in renderer
    lead = AcidLead(root_midi=root_midi, sr=SR, character='smooth')
    tracks.append(Track(
        instrument=lead,
        instrument_type='lead',
        active_from_bar=0,
        gain_target=GAIN_LEAD,
    ))

    # High pluck: enters at bar 2 (approximating t=3.1s at 138 BPM)
    pluck = HighPluck(sr=SR)
    tracks.append(Track(
        instrument=pluck,
        instrument_type='pluck',
        active_from_bar=2,
        gain_target=0.45,
    ))

    return Song(
        bpm=138.0,
        root_midi=root_midi,
        scale=scale,
        chord_prog=[[0, 4]],       # static G minor tonic (no progression in Hey Angel)
        chord_weights=[1],
        notearp_pattern=[-1] * 16,  # melody handled directly in hey_angel renderer path
        tracks=tracks,
        stage_bars=stage_bars,
        filter_pb_bar=9999,
        seed='hey_angel',
        mood='uplifting',
        total_bars=total_bars,
        sr=SR,
        pad_detune_cents=60.0,
        pad_room_size=0.7,
        pad_saw_count=5,
        lead_character='smooth',
        kick_decay_s=0.25,
        kick_pitch_floor=50.0,
        hihat_pattern='full',
        arc_shape='steady',
        chord_prog_b=None,
        root_shift=0,
        style='hey_angel',
    )


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

    # Chord progressions: seed selects A from pool; B is a different entry
    prog_pool  = _PROGRESSIONS_BY_MOOD[mood]
    prog_a_idx = _hash_bits(16, 4) % len(prog_pool)
    chord_prog = prog_pool[prog_a_idx]
    # B is the next entry in the pool (wraps), guaranteeing it differs from A
    chord_prog_b = prog_pool[(prog_a_idx + 1) % len(prog_pool)]

    # Root shift at pullback: 0 (no shift) or +2 semitones (classic trance lift)
    root_shift = 2 if (_hash_bits(128, 1) == 1) else 0

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
    for key in ['kick_on', 'pad_root_on', 'bass_on', 'lead_root_on',
                'lead_melody_on', 'pad_chord_on', 'lead_voicing_on', 'clap_on',
                'fm_on', 'pulse_on', 'hihat_on', 'kick_syncopated']:
        if key in stage_bars:
            stage_bars[key] = max(stage_bars[key], prev + (1 if prev > 0 else 0))
            prev = stage_bars[key]

    # Pullback bar: somewhere between bar 48 and 80
    filter_pb_bar = 48 + int(_hash_bits(80, 5) % 32)

    # Drum seed: varies so each song has different noise texture on drums
    drum_seed = _hash_bits(88, 16)

    # ── Instrument character ─────────────────────────────────────────────────
    # Pad detune: 30–80 cents. Wide detune (>60) = lush/washy; tight (<40) = focused/cutting.
    pad_detune_cents = 30.0 + (_hash_bits(104, 6) % 51)       # 30..80 cents

    # Pad reverb room size: 0.3–0.9. Large = spacious/diffuse; small = dry/tight.
    pad_room_size_idx = _hash_bits(110, 3) % 7                  # 0..6
    pad_room_size = 0.3 + pad_room_size_idx * 0.1               # 0.3..0.9

    # Pad saw count: 3, 5, or 7 voices. 3 = thin/focused; 7 = thick/massive.
    pad_saw_count = [3, 5, 5, 7][_hash_bits(113, 2) % 4]       # 3/5/5/7 (5 most common)

    # Lead character: 'acid' (SA's default — tight acidenv, low detune),
    # 'smooth' (wider detune, softer env), 'stab' (very dry, short gate).
    lead_character = ['acid', 'smooth', 'stab', 'acid'][_hash_bits(115, 2) % 4]

    # Kick decay: 0.15–0.28 s. Short = punchy; long = boomy.
    # Capped at 0.28s: at 140 BPM four-on-floor, kicks land every 0.43s.
    # Beyond ~0.30s decay the tail of one kick overlaps the next, creating
    # constant sub-bass rumble that drowns all other instruments.
    kick_decay_s = 0.15 + (_hash_bits(117, 5) % 14) * 0.01     # 0.15..0.28

    # Kick pitch floor: 30–70 Hz. Low = sub-weight; high = mid-punch.
    kick_pitch_floor = 30.0 + (_hash_bits(122, 6) % 41)        # 30..70 Hz

    # Hihat pattern: full 16ths, offbeat 8ths, or sparse straight 8ths.
    hihat_pattern = ['full', 'full', 'offbeat', 'sparse'][_hash_bits(68, 2) % 4]

    # Arc shape: how fast the song builds to full intensity.
    # 'fast' = all stages done by bar ~64; 'steady' = default ~96; 'slow' = ~128
    arc_shape = ['fast', 'steady', 'steady', 'slow'][_hash_bits(70, 2) % 4]

    # Scale stage_bars by arc_shape — multiply all non-zero entries by a factor,
    # then re-run the ordering pass so the sequence stays monotonic.
    _arc_scale = {'fast': 0.6, 'steady': 1.0, 'slow': 1.4}[arc_shape]
    if _arc_scale != 1.0:
        for key in stage_bars:
            if stage_bars[key] > 0:
                stage_bars[key] = max(1, int(round(stage_bars[key] * _arc_scale)))
        # Re-enforce monotonic ordering after scaling
        prev = 0
        for key in ['kick_on', 'pad_root_on', 'bass_on', 'lead_root_on',
                    'lead_melody_on', 'pad_chord_on', 'lead_voicing_on', 'clap_on',
                    'fm_on', 'pulse_on', 'hihat_on', 'kick_syncopated']:
            if key in stage_bars:
                stage_bars[key] = max(stage_bars[key], prev + (1 if prev > 0 else 0))
                prev = stage_bars[key]

    tracks = _build_tracks(stage_bars, root_midi, scale, chord_prog,
                           filter_pb_bar, drum_seed=drum_seed, sr=SR,
                           pad_detune_cents=pad_detune_cents,
                           pad_room_size=pad_room_size,
                           pad_saw_count=pad_saw_count,
                           lead_character=lead_character,
                           kick_decay_s=kick_decay_s,
                           kick_pitch_floor=kick_pitch_floor)

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
        pad_detune_cents=float(pad_detune_cents),
        pad_room_size=float(pad_room_size),
        pad_saw_count=int(pad_saw_count),
        lead_character=lead_character,
        kick_decay_s=float(kick_decay_s),
        kick_pitch_floor=float(kick_pitch_floor),
        hihat_pattern=hihat_pattern,
        arc_shape=arc_shape,
        chord_prog_b=chord_prog_b,
        root_shift=root_shift,
    )


def _build_tracks(stage_bars: dict, root_midi: int, scale: list,
                  chord_prog: list, filter_pb_bar: int,
                  drum_seed: int = 42, sr: int = SR,
                  pad_detune_cents: float = 60.0,
                  pad_room_size: float = 0.7,
                  pad_saw_count: int = 5,
                  lead_character: str = 'acid',
                  kick_decay_s: float = 0.25,
                  kick_pitch_floor: float = 50.0) -> list:
    """Instantiate all instrument tracks with their arc functions."""
    from song.track import Track
    from song.arcs import filter_cutoff_arc, fm_depth_arc, hihat_decay_arc, gain_arc
    from instruments.drums import DrumKit

    tracks = []

    # Kick + hihat + clap share one DrumKit instance, seeded per-song
    kit = DrumKit(seed=drum_seed, sr=sr,
                  kick_decay_s=kick_decay_s,
                  kick_pitch_floor=kick_pitch_floor)

    tracks.append(Track(
        instrument=kit,
        instrument_type='kick',
        active_from_bar=stage_bars['kick_on'],
        gain_target=GAIN_KICK,
    ))

    # Pad
    try:
        from instruments.pad import SupersawPad
        pad = SupersawPad(root_midi=root_midi, sr=sr,
                          detune_cents=pad_detune_cents,
                          room_size=pad_room_size,
                          saw_count=pad_saw_count)
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
        lead = AcidLead(root_midi=root_midi, sr=sr, character=lead_character)
        # SA's lead uses slider .593 (≈2563 Hz) as its base — a fixed bright value
        # independent of the pad's opening arc. The pad arc starts at 0.48 (~1100 Hz)
        # which makes the lead too dark in bars 8-32. Lock lead at its confirmed base
        # then allow it to track the full arc once the song opens past that point.
        def lead_arc(bar, _filter_pb_bar=filter_pb_bar):
            from song.theory import FILTER_ARC
            pad_slider = filter_cutoff_arc(bar, _filter_pb_bar)
            lead_base  = FILTER_ARC['lead_base']  # 0.593
            slider = max(pad_slider, lead_base)
            return {
                'cutoff_slider': slider,
                'fm_depth':      fm_depth_arc(bar),
            }
        tracks.append(Track(
            instrument=lead,
            instrument_type='lead',
            active_from_bar=stage_bars['lead_root_on'],
            gain_target=GAIN_LEAD,
            arc_fn=lead_arc,
        ))
    except ImportError:
        pass

    # Bass
    try:
        from instruments.bass import AcidBass
        bass = AcidBass(sr=sr)
        tracks.append(Track(
            instrument=bass,
            instrument_type='bass',
            active_from_bar=stage_bars.get('bass_on', 4),
            gain_target=GAIN_BASS,
        ))
    except ImportError:
        pass

    return tracks
