# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# song/track.py
# Track dataclass: instrument + pattern + activation bar + arc function.

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class Track:
    """One instrument voice in the song.

    instrument      — an instruments.* instance with a render() method
    instrument_type — string tag ('kick', 'pad', 'lead', 'bass', 'hihat', 'clap', 'pulse')
    active_from_bar — bar at which this track begins playing
    gain_target     — base gain (from theory.GAIN_*)
    arc_fn          — optional per-bar parameter function: (bar) -> dict of render kwargs
    """
    instrument:      Any
    instrument_type: str
    active_from_bar: int
    gain_target:     float
    arc_fn:          Optional[Callable] = None

    def is_active(self, bar: int) -> bool:
        return bar >= self.active_from_bar

    def render_kwargs(self, bar: int) -> dict:
        """Return kwargs to pass to instrument.render() at this bar."""
        if self.arc_fn is not None:
            return self.arc_fn(bar)
        return {}
