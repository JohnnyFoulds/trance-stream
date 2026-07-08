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
