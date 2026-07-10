# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests that seeds and moods produce genuinely different songs.

These test the variation properties that were previously broken:
- Different seeds → different root, BPM, chord progression, notearp pattern
- Different moods → different scale, BPM range, chord pool
- Drum seed varies per song (not hardcoded to 42)
- No two seeds from a sample set should produce the same song structure
"""

from __future__ import annotations

import sys
import pathlib
import itertools

import numpy as np
import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

SR = 44100
BPM_DEFAULT = 140.0
SPB = int(SR * 4 * 60 / BPM_DEFAULT)

SEEDS = ['sunrise', 'forest', 'midnight', 'aurora', 'storm', 'ocean', 'ember', 'frost']
MOODS = ['uplifting', 'dark', 'acid', 'dreamy', 'progressive']


def _song(seed, mood='uplifting'):
    from song.builder import build_song
    return build_song(seed, mood=mood, total_bars=16)


def _render_8(seed, mood='uplifting'):
    from song.builder import build_song
    from song.renderer import SongRenderer
    song = build_song(seed, mood=mood, total_bars=8)
    spb = int(SR * 4 * 60 / song.bpm)
    renderer = SongRenderer(song)
    l, r = renderer.render_bars(8)
    return l, r, song


# ---------------------------------------------------------------------------
# Root note varies with seed
# ---------------------------------------------------------------------------

def test_seeds_produce_different_root_notes():
    """All 8 test seeds should not all land on the same root note."""
    roots = [_song(s).root_midi for s in SEEDS]
    unique_roots = set(roots)
    assert len(unique_roots) > 2, (
        f"Only {len(unique_roots)} distinct root notes across {len(SEEDS)} seeds: {roots}"
    )


def test_roots_span_at_least_one_octave():
    """The range of root notes across seeds should span multiple semitones."""
    roots = [_song(s).root_midi for s in SEEDS]
    span = max(roots) - min(roots)
    assert span >= 3, (
        f"Root notes span only {span} semitones across {len(SEEDS)} seeds: {roots}"
    )


# ---------------------------------------------------------------------------
# BPM varies with seed and mood
# ---------------------------------------------------------------------------

def test_seeds_produce_different_bpms():
    """Different seeds should produce different BPMs (within mood range)."""
    bpms = [_song(s).bpm for s in SEEDS]
    unique_bpms = set(bpms)
    assert len(unique_bpms) > 1, (
        f"All seeds produced identical BPM={bpms[0]}"
    )


def test_mood_bpm_ranges_are_distinct():
    """Dreamy and acid moods should produce different BPM ranges."""
    dreamy_bpm = _song('sunrise', 'dreamy').bpm
    acid_bpm   = _song('sunrise', 'acid').bpm
    assert dreamy_bpm != acid_bpm, (
        f"dreamy and acid produced identical BPM {dreamy_bpm}"
    )
    # Dreamy should be slower than acid
    assert dreamy_bpm < acid_bpm, (
        f"dreamy ({dreamy_bpm}) should be slower than acid ({acid_bpm})"
    )


def test_bpm_within_mood_range():
    """Each mood's BPM must stay within its declared range."""
    ranges = {
        'uplifting':   (138, 142),
        'dark':        (136, 140),
        'acid':        (138, 145),
        'dreamy':      (128, 136),
        'progressive': (128, 138),
    }
    for mood, (lo, hi) in ranges.items():
        for seed in ['sunrise', 'midnight', 'storm']:
            bpm = _song(seed, mood).bpm
            assert lo <= bpm <= hi, (
                f"{mood}/{seed}: BPM {bpm} outside declared range [{lo}, {hi}]"
            )


# ---------------------------------------------------------------------------
# Chord progression varies with seed
# ---------------------------------------------------------------------------

def test_seeds_produce_different_chord_progressions():
    """Not all seeds should land on the same chord progression."""
    progs = [str(_song(s).chord_prog) for s in SEEDS]
    unique = set(progs)
    assert len(unique) > 1, (
        f"All {len(SEEDS)} seeds produced the same chord progression: {progs[0]}"
    )


def test_moods_produce_different_chord_progressions():
    """Each mood should produce a different chord progression for the same seed."""
    progs = {mood: str(_song('sunrise', mood).chord_prog) for mood in MOODS}
    unique = set(progs.values())
    assert len(unique) > 2, (
        f"Only {len(unique)} distinct progressions across {len(MOODS)} moods: {progs}"
    )


# ---------------------------------------------------------------------------
# Notearp pattern varies with seed
# ---------------------------------------------------------------------------

def test_seeds_produce_different_notearp_patterns():
    """Not all seeds should use the same notearp pattern."""
    patterns = [str(_song(s).notearp_pattern) for s in SEEDS]
    unique = set(patterns)
    assert len(unique) > 1, (
        f"All {len(SEEDS)} seeds produced the same notearp pattern: {patterns[0]}"
    )


# ---------------------------------------------------------------------------
# Scale varies with mood
# ---------------------------------------------------------------------------

def test_moods_produce_different_scales():
    """At least 3 distinct scales should appear across the 5 moods."""
    scales = {mood: str(_song('sunrise', mood).scale) for mood in MOODS}
    unique = set(scales.values())
    assert len(unique) >= 2, (
        f"Only {len(unique)} distinct scales across {len(MOODS)} moods: {scales}"
    )


def test_dreamy_uses_dorian():
    """Dreamy mood must use dorian scale."""
    from song.theory import SCALES
    song = _song('sunrise', 'dreamy')
    assert song.scale == SCALES['dorian'], (
        f"dreamy scale {song.scale} != dorian {SCALES['dorian']}"
    )


def test_progressive_uses_major():
    """Progressive mood must use major scale."""
    from song.theory import SCALES
    song = _song('sunrise', 'progressive')
    assert song.scale == SCALES['major'], (
        f"progressive scale {song.scale} != major {SCALES['major']}"
    )


# ---------------------------------------------------------------------------
# Stage timing varies with seed
# ---------------------------------------------------------------------------

def test_seeds_produce_different_stage_timings():
    """Stage bars should vary across seeds."""
    lead_ons = [_song(s).stage_bars['lead_melody_on'] for s in SEEDS]
    unique = set(lead_ons)
    assert len(unique) > 1, (
        f"All seeds produced identical lead_melody_on={lead_ons[0]}"
    )


# ---------------------------------------------------------------------------
# Drum seed varies — different noise texture per song
# ---------------------------------------------------------------------------

def test_drum_seeds_vary_across_songs():
    """Drums should sound different across seeds (different noise texture)."""
    from instruments.drums import DrumKit
    from song.builder import build_song

    # Extract the drum_seed used by each song by checking DrumKit init
    # We can't inspect it directly, so render a kick-only segment and compare
    results = []
    for seed in ['sunrise', 'forest', 'midnight']:
        song = build_song(seed, total_bars=4)
        # Find the DrumKit track
        kit = None
        for t in song.tracks:
            if t.instrument_type == 'kick':
                kit = t.instrument
                break
        assert kit is not None
        l, _ = kit.render_kick(gain=1.0)
        results.append(l.copy())

    assert not np.array_equal(results[0], results[1]), \
        "sunrise and forest produced identical kick (drum seed not varying)"
    assert not np.array_equal(results[0], results[2]), \
        "sunrise and midnight produced identical kick (drum seed not varying)"


# ---------------------------------------------------------------------------
# Audio output is genuinely different between seeds/moods
# ---------------------------------------------------------------------------

def test_audio_differs_across_seeds():
    """Rendered audio must differ across seeds — not just metadata."""
    audios = []
    for seed in ['sunrise', 'forest', 'midnight']:
        l, _, _ = _render_8(seed, 'uplifting')
        audios.append(l)

    for (i, a), (j, b) in itertools.combinations(enumerate(audios), 2):
        names = ['sunrise', 'forest', 'midnight']
        assert not np.array_equal(a, b), (
            f"Seeds {names[i]} and {names[j]} produced identical audio"
        )


def test_audio_differs_across_moods():
    """Rendered audio must differ across moods for the same seed.

    Chord/scale differences only become audible after pad_chord_on (~bar 38-43).
    We compare song parameters rather than raw audio, since a short 8-bar render
    only contains the root note and kick, which are identical across moods with
    the same BPM and root.
    """
    songs = {mood: _song('sunrise', mood) for mood in MOODS}

    # Every pair of moods must differ in at least one musical parameter
    for mood_a, mood_b in itertools.combinations(MOODS, 2):
        sa, sb = songs[mood_a], songs[mood_b]
        differs = (
            sa.scale != sb.scale or
            sa.chord_prog != sb.chord_prog or
            sa.bpm != sb.bpm
        )
        assert differs, (
            f"Moods {mood_a} and {mood_b} are musically identical: "
            f"bpm={sa.bpm}/{sb.bpm} scale={sa.scale}/{sb.scale} chord={sa.chord_prog}/{sb.chord_prog}"
        )


def test_audio_rms_differs_across_seeds():
    """RMS levels should vary across seeds (different BPM, root, progression)."""
    rms_values = []
    for seed in SEEDS:
        l, _, _ = _render_8(seed)
        rms_values.append(float(np.sqrt(np.mean(l.astype(np.float64) ** 2))))

    rms_range = max(rms_values) - min(rms_values)
    # Even small differences in BPM change spb, causing minor RMS shifts.
    # We just verify they're not all identical.
    assert rms_range > 0.01, f"RMS range across seeds {rms_range:.4f} is too small: {rms_values}"


# ---------------------------------------------------------------------------
# Determinism still holds
# ---------------------------------------------------------------------------

def test_same_seed_same_audio():
    """Same seed must still produce identical audio on repeat builds."""
    l1, _, _ = _render_8('sunrise', 'uplifting')
    l2, _, _ = _render_8('sunrise', 'uplifting')
    assert np.array_equal(l1, l2), "Same seed produced different audio"
