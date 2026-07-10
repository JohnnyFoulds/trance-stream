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

    # Instrument character — seed-driven; what makes two songs audibly different
    pad_detune_cents: float = 60.0    # supersaw detune: tight (30) to wide (80)
    pad_room_size:    float = 0.7     # FDN reverb: dry/tight (0.3) to spacious (0.9)
    pad_saw_count:    int   = 5       # supersaw voices: 3 (thin) to 7 (thick)
    lead_character:   str   = 'acid'  # 'acid', 'smooth', or 'stab'
    kick_decay_s:     float = 0.25    # kick length: punchy (0.12) to boomy (0.35)
    kick_pitch_floor: float = 50.0    # kick bottom pitch: tight (70 Hz) to sub (30 Hz)
    hihat_pattern:    str   = 'full'  # 'full' (all-16), 'offbeat' (8ths), 'sparse' (odd 8ths)
    arc_shape:        str   = 'steady'  # 'fast', 'steady', or 'slow'

    # Harmonic modulation — creates a second-half shift at the pullback
    chord_prog_b:   list = None   # second progression used after filter_pb_bar; None = loop A forever
    root_shift:     int  = 0      # semitones added to root after pullback (0 or +2)

    # Style variant: 'trance' (default SA procedural) or 'hey_angel' (Hey Angel synthesis)
    style:          str  = 'trance'
