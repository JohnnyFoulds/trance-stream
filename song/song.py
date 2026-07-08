# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# song/song.py
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Song:
    """Complete specification of one trance song generation.

    All musical choices are derived from song/theory.py — no magic constants here.
    """
    bpm:             float
    root_midi:       int               # e.g. 55 = G3
    scale:           list[int]         # semitone offsets from theory.SCALES
    chord_prog:      list[list[int]]   # list of scale-degree lists from theory.PROGRESSIONS
    chord_weights:   list[int]         # relative durations per chord (from PAD_CHORD_WEIGHTS)
    notearp_pattern: list[int]         # from theory.SA_NOTEARP_PATTERN
    tracks:          list[Any]         # list of song.track.Track
    stage_bars:      dict[str, int]    # from theory.STAGE_BARS_DEFAULT + seed jitter
    filter_pb_bar:   int               # pullback bar (seed-determined)
    seed:            str               # generation seed
    mood:            str               # 'uplifting', 'dark', 'acid', etc.
    total_bars:      int = 128
    sr:              int = 44100
