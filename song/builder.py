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


def build_song(seed: str, mood: str = 'uplifting', bpm: float = BPM,
               total_bars: int = 128) -> 'Song':
    """Build a Song from a seed and mood.

    All musical choices come from theory.py. The seed provides:
    - Root note (md5 hash mod 12, added to 48)
    - Stage timing jitter (±4 bars from STAGE_BARS_DEFAULT)
    - Pullback bar position
    """
    from song.song import Song
    from song.track import Track
    from song.arcs import filter_cutoff_arc, fm_depth_arc, delay_wet_arc, hihat_decay_arc, gain_arc

    # Deterministic RNG from seed
    digest_int = int(hashlib.md5(seed.encode()).hexdigest(), 16)

    # Root note: 48 + (hash mod 12) → C3..B3
    root_midi = 48 + (digest_int % 12)

    # Scale and chord progression from mood
    scale      = SCALES[MOOD_TO_SCALE[mood]]
    chord_prog = PROGRESSIONS[MOOD_TO_PROGRESSION[mood]]

    # Stage timing: jitter STAGE_BARS_DEFAULT by ±4 bars using seed
    def jitter(base: int, idx: int, max_j: int = 4) -> int:
        # Deterministic per-stage jitter using (digest_int >> idx) mod (2*max_j+1)
        offset = int((digest_int >> (idx * 4)) % (2 * max_j + 1)) - max_j
        return max(0, base + offset)

    stage_items = list(STAGE_BARS_DEFAULT.items())
    stage_bars = {k: jitter(v, i) for i, (k, v) in enumerate(stage_items)}
    # Ensure kick_on is always 0 and order is preserved (each stage >= previous)
    stage_bars['kick_on'] = 0
    prev = 0
    for key in ['kick_on', 'pad_root_on', 'lead_root_on', 'lead_melody_on',
                'pad_chord_on', 'lead_voicing_on', 'clap_on', 'fm_on',
                'pulse_on', 'hihat_on', 'kick_syncopated']:
        if key in stage_bars:
            stage_bars[key] = max(stage_bars[key], prev + 1) if prev > 0 else stage_bars[key]
            prev = stage_bars[key]

    # Pullback bar: somewhere between bar 48 and bar 80, seed-determined
    filter_pb_bar = 48 + int((digest_int >> 32) % 32)

    # Build tracks lazily (instruments instantiated here)
    tracks = _build_tracks(stage_bars, root_midi, scale, chord_prog,
                           filter_pb_bar, sr=SR)

    return Song(
        bpm=bpm,
        root_midi=root_midi,
        scale=scale,
        chord_prog=chord_prog,
        chord_weights=PAD_CHORD_WEIGHTS,
        notearp_pattern=SA_NOTEARP_PATTERN,
        tracks=tracks,
        stage_bars=stage_bars,
        filter_pb_bar=filter_pb_bar,
        seed=seed,
        mood=mood,
        total_bars=total_bars,
        sr=SR,
    )


def _build_tracks(stage_bars: dict, root_midi: int, scale: list,
                  chord_prog: list, filter_pb_bar: int, sr: int) -> list:
    """Instantiate all instrument tracks with their arc functions."""
    from song.track import Track
    from song.arcs import filter_cutoff_arc, fm_depth_arc, delay_wet_arc, hihat_decay_arc
    from instruments.drums import DrumKit

    tracks = []

    # Kick
    kit = DrumKit(seed=42, sr=sr)
    tracks.append(Track(
        instrument=kit,
        instrument_type='kick',
        active_from_bar=stage_bars['kick_on'],
        gain_target=GAIN_KICK,
    ))

    # Pad — import here to avoid circular at module level
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
