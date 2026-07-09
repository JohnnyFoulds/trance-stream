# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# song/pattern.py
# Rhythmic and melodic patterns built from theory.py constants.

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import numpy as np


@dataclass
class StepPattern:
    """A rhythmic pattern of 16th-note steps, each with an optional MIDI note.

    steps : list[int]   — which 16th-note positions fire (0–15)
    notes : list[int]   — MIDI note or chord index per active step (-1 = chord index 0)
    """
    steps: list[int]
    notes: list[int] = field(default_factory=list)

    def __post_init__(self):
        if not self.notes:
            self.notes = [0] * len(self.steps)

    def as_grid(self) -> list[int]:
        """Return 16-element list: note at active steps, -1 at rests."""
        grid = [-1] * 16
        for step, note in zip(self.steps, self.notes):
            grid[step % 16] = note
        return grid

    def fires_at(self, step: int) -> bool:
        return (step % 16) in self.steps


def kick_basic() -> StepPattern:
    """Four-on-floor kick. Source: theory.KICK_STEPS_BASIC"""
    from song.theory import KICK_STEPS_BASIC
    return StepPattern(steps=KICK_STEPS_BASIC)


def kick_syncopated() -> StepPattern:
    """SA's trance pump kick. Source: theory.KICK_STEPS_SYNCOPATED"""
    from song.theory import KICK_STEPS_SYNCOPATED
    return StepPattern(steps=KICK_STEPS_SYNCOPATED)


def clap_backbeat() -> StepPattern:
    """Beats 2+4 clap. Source: theory.CLAP_STEPS_BACKBEAT"""
    from song.theory import CLAP_STEPS_BACKBEAT
    return StepPattern(steps=CLAP_STEPS_BACKBEAT)


def clap_syncopated() -> StepPattern:
    from song.theory import CLAP_STEPS_SYNCOPATED
    return StepPattern(steps=CLAP_STEPS_SYNCOPATED)


def hihat_all16() -> StepPattern:
    """All 16 16th notes. Source: theory.HIHAT_STEPS"""
    return StepPattern(steps=list(range(16)))


def notearp_pattern(chord_midi_notes: list[int]) -> StepPattern:
    """SA's confirmed notearp pattern applied to a chord.

    Uses theory.SA_NOTEARP_PATTERN (-1=rest, 0=chord[0], 1=chord[1]).
    Returns a StepPattern where each active step maps to an absolute MIDI note.
    Source: theory.SA_NOTEARP_PATTERN, docs/music_theory/04_generative_melody.md
    """
    from song.theory import SA_NOTEARP_PATTERN
    steps = []
    notes = []
    for i, idx in enumerate(SA_NOTEARP_PATTERN):
        if idx >= 0:
            steps.append(i)
            note = chord_midi_notes[idx % len(chord_midi_notes)] if chord_midi_notes else 60
            notes.append(note)
    return StepPattern(steps=steps, notes=notes)


def lead_melody_pattern(chord_midi_notes: list[int], bar: int) -> StepPattern:
    """SA's lead melody pattern — sparse 2-note phrase with bar-cycling notes.

    Derived from SA's "@@2 <-7 [-5 -2]>@3 <0 -3 2 1>@3".add 7:
    - @@2 (weight 2): rest for first 4 sixteenth-notes (steps 0–3)
    - <...>@3 (weight 3): note at step 4, sustained 6 sixteenth-notes
    - <...>@3 (weight 3): note at step 10, sustained 6 sixteenth-notes

    Step 4 note alternates each bar (< > cycling):
      even bars: chord[0]
      odd bars:  chord[1 % n]  — the fifth, or same note if monophonic

    Step 10 note cycles every 4 bars (<0 -3 2 1> mapped to available chord tones):
      bar%4==0: chord[0]
      bar%4==1: chord[1 % n]
      bar%4==2: chord[0]  — back to root for a question-answer phrase shape
      bar%4==3: chord[1 % n]

    All notes should already be transposed +12 by the caller (SA's .add 7).
    Source: docs/music_theory/02_sa_vocabulary_codified.md §3 (lead melody analysis)
    """
    n = max(len(chord_midi_notes), 1)
    note_4  = chord_midi_notes[bar % 2 % n]
    note_10 = chord_midi_notes[(bar % 4 // 2) % n]   # 0→0, 1→0, 2→1, 3→1 in 2-tone chord
    return StepPattern(steps=[4, 10], notes=[note_4, note_10])
