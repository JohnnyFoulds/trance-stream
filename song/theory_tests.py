# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Self-consistency tests for song/theory.py.

Tests verify mathematical correctness of the theory constants.
No audio synthesis, no external files required.

Run with: pytest song/theory_tests.py
"""

import pytest

from song.theory import (
    FILTER_ARC,
    GAIN_BASS,
    GAIN_CLAP,
    GAIN_HIHAT,
    GAIN_KICK,
    GAIN_LEAD,
    GAIN_PAD,
    GAIN_PULSE,
    KICK_STEPS_BASIC,
    KICK_STEPS_SYNCOPATED,
    PAD_VOICING_OFFSETS,
    SA_NOTEARP_PATTERN,
    SCALES,
    STAGE_BARS_DEFAULT,
    chord_to_midi,
    degree_to_midi,
    rlpf_to_hz,
    samples_per_bar,
    samples_per_sixteenth,
)

# ---------------------------------------------------------------------------
# Scale intervals
# ---------------------------------------------------------------------------


def test_scale_intervals_in_range():
    for name, intervals in SCALES.items():
        for i in intervals:
            assert 0 <= i <= 11, f"SCALES[{name!r}] has out-of-range interval {i}"


# ---------------------------------------------------------------------------
# rlpf_to_hz spot checks
# ---------------------------------------------------------------------------


def test_rlpf_to_hz_full_open():
    hz = rlpf_to_hz(0.877)
    assert 12000 <= hz <= 12500, f"rlpf_to_hz(0.877) = {hz}, expected 12000–12500"


def test_rlpf_to_hz_lead_base():
    hz = rlpf_to_hz(0.593)
    assert 2400 <= hz <= 2700, f"rlpf_to_hz(0.593) = {hz}, expected 2400–2700"


def test_rlpf_to_hz_start():
    hz = rlpf_to_hz(0.45)
    assert 700 <= hz <= 1000, f"rlpf_to_hz(0.45) = {hz}, expected 700–1000"


# ---------------------------------------------------------------------------
# FILTER_ARC slider values produce audible Hz
# ---------------------------------------------------------------------------


def test_filter_arc_all_valid_hz():
    for label, slider in FILTER_ARC.items():
        hz = rlpf_to_hz(slider)
        assert 20 <= hz <= 20000, (
            f"FILTER_ARC[{label!r}] slider={slider} → {hz} Hz is outside 20–20000 Hz"
        )


# ---------------------------------------------------------------------------
# PAD_VOICING_OFFSETS
# ---------------------------------------------------------------------------


def test_pad_voicing_offsets_sub_doublings_negative():
    for offset in PAD_VOICING_OFFSETS[1:]:
        assert offset < 0, f"PAD_VOICING_OFFSETS sub-bass doubling {offset} is not negative"


# ---------------------------------------------------------------------------
# SA_NOTEARP_PATTERN
# ---------------------------------------------------------------------------


def test_notearp_pattern_length():
    assert len(SA_NOTEARP_PATTERN) == 16


def test_notearp_pattern_values():
    allowed = {-1, 0, 1}
    for i, v in enumerate(SA_NOTEARP_PATTERN):
        assert v in allowed, f"SA_NOTEARP_PATTERN[{i}] = {v!r}, expected one of {allowed}"


# ---------------------------------------------------------------------------
# Drum patterns
# ---------------------------------------------------------------------------


def test_kick_steps_syncopated_exact():
    assert KICK_STEPS_SYNCOPATED == [0, 4, 8, 11, 14]


def test_kick_steps_basic_exact():
    assert KICK_STEPS_BASIC == [0, 4, 8, 12]


def test_kick_steps_in_range():
    for step in KICK_STEPS_BASIC + KICK_STEPS_SYNCOPATED:
        assert 0 <= step <= 15, f"kick step {step} is outside [0, 15]"


# ---------------------------------------------------------------------------
# degree_to_midi
# ---------------------------------------------------------------------------


def test_degree_to_midi_root():
    assert degree_to_midi(0, 55, SCALES['natural_minor']) == 55


def test_degree_to_midi_octave_up():
    # degree 7 = one full octave above root in a 7-note scale
    assert degree_to_midi(7, 55, SCALES['natural_minor']) == 67


# ---------------------------------------------------------------------------
# chord_to_midi
# ---------------------------------------------------------------------------


def test_chord_to_midi_sa_canonical():
    # G3=55, natural_minor=[0,2,3,5,7,8,10]
    # degree 3 → scale[3]=5  → 55+5=60
    # degree 4 → scale[4]=7  → 55+7=62
    # degree 5 → scale[5]=8  → 55+8=63
    # degree 6 → scale[6]=10 → 55+10=65
    result = chord_to_midi([3, 4, 5, 6], 55, SCALES['natural_minor'])
    assert result == [60, 62, 63, 65]


# ---------------------------------------------------------------------------
# Timing helpers
# ---------------------------------------------------------------------------


def test_samples_per_bar():
    assert samples_per_bar(140, 44100) == 75600


def test_samples_per_sixteenth():
    assert samples_per_sixteenth(140, 44100) == 4725


# ---------------------------------------------------------------------------
# GAIN constants
# ---------------------------------------------------------------------------

_ALL_GAINS = {
    'GAIN_KICK':  GAIN_KICK,
    'GAIN_PAD':   GAIN_PAD,
    'GAIN_LEAD':  GAIN_LEAD,
    'GAIN_BASS':  GAIN_BASS,
    'GAIN_HIHAT': GAIN_HIHAT,
    'GAIN_CLAP':  GAIN_CLAP,
    'GAIN_PULSE': GAIN_PULSE,
}


def test_all_gains_in_range():
    for name, value in _ALL_GAINS.items():
        assert 0.0 <= value <= 1.0, f"{name} = {value} is outside [0.0, 1.0]"


def test_gain_kick_is_unity():
    assert GAIN_KICK == 1.0


# ---------------------------------------------------------------------------
# STAGE_BARS_DEFAULT
# ---------------------------------------------------------------------------


def test_stage_bars_non_negative_integers():
    for stage, bar in STAGE_BARS_DEFAULT.items():
        assert isinstance(bar, int), f"STAGE_BARS_DEFAULT[{stage!r}] is not an int"
        assert bar >= 0, f"STAGE_BARS_DEFAULT[{stage!r}] = {bar} is negative"


def test_stage_bars_kick_on_is_zero():
    assert STAGE_BARS_DEFAULT['kick_on'] == 0


def test_stage_bars_strictly_increasing():
    values = list(STAGE_BARS_DEFAULT.values())
    for i in range(1, len(values)):
        assert values[i] > values[i - 1], (
            f"STAGE_BARS_DEFAULT is not strictly increasing at index {i}: "
            f"{values[i - 1]} then {values[i]}"
        )
