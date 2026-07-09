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
    """SA-inspired lead melody with 4-bar phrase cycle and 8-bar rhythm variation.

    chord_midi_notes is a 5-tone vocabulary built from the chord root + 4 scale
    steps above it, giving real melodic movement beyond root/fifth monotony.

    Rhythm: the step positions shift on an 8-bar cycle to avoid feeling static.
      bars 0,4:  [4, 10]   — SA's canonical back-loaded spacing (weight 2+3+3)
      bars 1,5:  [2, 10]   — pushed early, creates anticipation
      bars 2,6:  [4, 12]   — shifted late, "call and answer" across the beat
      bars 3,7:  [6, 11]   — syncopated, cross-rhythm tension

    Note choices follow a 4-bar descending phrase through 4 scale tones:
      position A (first hit): bar%4=0→tone[0], 1→tone[4], 2→tone[2], 3→tone[3]
      position B (second hit): bar%4=0→tone[2], 1→tone[0], 2→tone[3], 3→tone[1]

    The combined effect: a minor-key melodic line that resolves every 4 bars
    and shifts rhythmic feel every 2 bars — exactly SA's live energy.
    """
    n = max(len(chord_midi_notes), 1)

    # 8-bar rhythm cycle
    _RHYTHM = [(4, 10), (2, 10), (4, 12), (6, 11),
               (4, 10), (2, 10), (4, 12), (6, 11)]
    step_a, step_b = _RHYTHM[bar % 8]

    # 4-bar note phrase for each hit position
    _PHRASE_A = [0, 4, 2, 3]   # first hit: root → top → 3rd → 4th
    _PHRASE_B = [2, 0, 3, 1]   # second hit: 3rd → root → 4th → 2nd

    idx_a = _PHRASE_A[bar % 4] % n
    idx_b = _PHRASE_B[bar % 4] % n

    note_a = chord_midi_notes[idx_a]
    note_b = chord_midi_notes[idx_b]

    return StepPattern(steps=[step_a, step_b], notes=[note_a, note_b])
