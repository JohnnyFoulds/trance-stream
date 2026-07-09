# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Text-mode visualiser for trance_stream_v3 --stream mode.

Renders a full-screen ANSI box-drawing display in the terminal, updating
once per bar. Adapts layout to terminal width. No external dependencies —
pure Python stdlib + numpy (already required by the synthesiser).

Usage (from trance_stream_v3.py)::

    from tools.visualiser import Visualiser, make_bar_info
    viz = Visualiser(song, n_bars)
    viz.start()
    # in the stream loop after stream.write():
    viz.update(make_bar_info(bar_idx, song, render_ms, bar_dur_ms))
    # on exit:
    viz.stop()
"""
from __future__ import annotations

import math
import shutil
import sys
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# ANSI colour/style codes
# ---------------------------------------------------------------------------
_RESET  = '\033[0m'
_BOLD   = '\033[1m'
_DIM    = '\033[2m'
_GREEN  = '\033[92m'   # active track dot
_CYAN   = '\033[96m'   # filter bar filled / CA row at low energy
_YELLOW = '\033[93m'   # CA row at high energy
_WHITE  = '\033[97m'
_HIDE_CURSOR = '\033[?25l'
_SHOW_CURSOR = '\033[?25h'
_HOME        = '\033[H'
_CLEAR       = '\033[2J'

# Box-drawing
_TL = '╔'
_TR = '╗'
_BL = '╚'
_BR = '╝'
_ML = '╠'
_MR = '╣'
_H  = '═'
_V  = '║'


# ---------------------------------------------------------------------------
# BarInfo dataclass
# ---------------------------------------------------------------------------
@dataclass
class BarInfo:
    bar_idx:       int
    n_bars:        Optional[int]          # None = infinite
    bpm:           float
    seed:          str
    mood:          str
    chord_name:    str                    # e.g. 'Am', 'Dm', 'F'
    chord_idx:     int                    # 0-3
    filter_hz:     float                  # cutoff in Hz
    filter_slider: float                  # 0.0-1.0 normalised slider
    fm_depth:      float                  # 0.0-0.55
    gate_phase:    float                  # 0.0-1.0, position in trancegate cycle
    tracks_active: dict[str, bool] = field(default_factory=dict)
    render_ms:     float = 0.0
    bar_dur_ms:    float = 1714.0
    headroom_ms:   float = 0.0


# ---------------------------------------------------------------------------
# Pure helper: build BarInfo from a bar index + Song
# ---------------------------------------------------------------------------
def make_bar_info(bar_idx: int, song, render_ms: float, bar_dur_ms: float) -> BarInfo:
    """Compute all display parameters from bar index and Song dataclass.

    Pure function — no side effects, no instrument state accessed.
    """
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from song.arcs import filter_cutoff_arc, fm_depth_arc
    from song.theory import rlpf_to_hz, chord_to_midi, TRANCEGATE_SPEED, PAD_CHORD_WEIGHTS

    # Chord index — replicate SongRenderer._chord_index logic
    weights = song.chord_weights if song.chord_weights else PAD_CHORD_WEIGHTS
    cycle_len = sum(weights)
    pos = bar_idx % cycle_len
    cumulative = 0
    chord_idx = 0
    for i, w in enumerate(weights):
        cumulative += w
        if pos < cumulative:
            chord_idx = i % len(song.chord_prog)
            break

    chord_degrees = song.chord_prog[chord_idx]
    chord_name = _chord_name(song.root_midi, chord_degrees, song.scale)

    slider = filter_cutoff_arc(bar_idx, song.filter_pb_bar)
    filter_hz = rlpf_to_hz(slider)
    fm_depth = fm_depth_arc(bar_idx)

    # Trancegate: where in the cycle are we at bar start?
    # Phase = (bar_idx * spb) / gate_period_samples, mod 1.0
    spb = int(song.sr * 4 * 60 / song.bpm)
    gate_period = spb / TRANCEGATE_SPEED
    gate_phase = (bar_idx * spb % gate_period) / gate_period

    # Which tracks are active this bar?
    sb = song.stage_bars
    tracks_active = {
        'kick':  bar_idx >= sb.get('kick_on',   0),
        'pad':   bar_idx >= sb.get('pad_root_on', 9999),
        'bass':  bar_idx >= sb.get('bass_on',   9999),
        'lead':  bar_idx >= sb.get('lead_root_on', 9999),
        'hihat': bar_idx >= sb.get('hihat_on',  9999),
        'clap':  bar_idx >= sb.get('clap_on',   9999),
        'pulse': bar_idx >= sb.get('pulse_on',  9999),
    }

    return BarInfo(
        bar_idx       = bar_idx,
        n_bars        = None,
        bpm           = song.bpm,
        seed          = song.seed,
        mood          = song.mood,
        chord_name    = chord_name,
        chord_idx     = chord_idx,
        filter_hz     = filter_hz,
        filter_slider = slider,
        fm_depth      = fm_depth,
        gate_phase    = gate_phase,
        tracks_active = tracks_active,
        render_ms     = render_ms,
        bar_dur_ms    = bar_dur_ms,
        headroom_ms   = bar_dur_ms - render_ms,
    )


def _chord_name(root_midi: int, degrees: list, scale: list) -> str:
    """Return a chord name like 'Am', 'Dm', 'F' from scale degrees."""
    NOTE_NAMES = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
    root_semitone = root_midi % 12
    deg0 = degrees[0] % len(scale)
    chord_root = (root_semitone + scale[deg0]) % 12

    # Determine quality from the interval between degrees[0] and degrees[0]+2
    # (the third in a diatonic chord). 4 semitones = major, 3 = minor.
    deg_third = (degrees[0] + 2) % len(scale)
    interval = (scale[deg_third] - scale[deg0]) % 12
    quality = '' if interval == 4 else 'm'

    return NOTE_NAMES[chord_root] + quality


# ---------------------------------------------------------------------------
# Wolfram Rule 30 CA (verbatim from trance_stream.py)
# ---------------------------------------------------------------------------
def _ca_next(state: np.ndarray, rule: int = 30) -> np.ndarray:
    next_state = np.zeros_like(state)
    n = len(state)
    for i in range(n):
        left   = state[i - 1] if i > 0 else state[n - 1]
        centre = state[i]
        right  = state[i + 1] if i < n - 1 else state[0]
        idx    = (left << 2) | (centre << 1) | right
        next_state[i] = (rule >> idx) & 1
    return next_state


# ---------------------------------------------------------------------------
# Visualiser class
# ---------------------------------------------------------------------------
class Visualiser:
    """Full-screen ANSI terminal visualiser.

    Call start() once before streaming, update(bar_info) each bar,
    stop() on exit to restore the terminal.
    """

    CA_WIDTH = 32

    def __init__(self, song, n_bars: Optional[int] = None):
        self.song   = song
        self.n_bars = n_bars
        # Seed CA from root_midi for determinism
        rng = np.random.default_rng(song.root_midi)
        self._ca = rng.integers(0, 2, size=self.CA_WIDTH, dtype=np.int32)
        self._prev_chord_idx = -1
        self._fm_ever_active = False

    def start(self) -> None:
        sys.stdout.write(_HIDE_CURSOR + _CLEAR + _HOME)
        sys.stdout.flush()

    def stop(self) -> None:
        # Move cursor below the display box and restore
        cols, rows = shutil.get_terminal_size((80, 24))
        n_lines = 12  # max height of our display
        sys.stdout.write(f'\033[{n_lines + 2};0H' + _SHOW_CURSOR + _RESET + '\n')
        sys.stdout.flush()

    def update(self, info: BarInfo) -> None:
        """Re-render the display in place for this bar."""
        # Inject musical events into CA before advancing
        if info.chord_idx != self._prev_chord_idx and self._prev_chord_idx >= 0:
            self._ca[0] = 1  # chord change marker
        self._prev_chord_idx = info.chord_idx

        if info.fm_depth > 0 and not self._fm_ever_active:
            self._ca[5] = 1  # FM onset marker
            self._fm_ever_active = True

        # 4-bar phrase marker
        self._ca[11] = 1 if info.bar_idx % 4 == 0 else 0

        # Advance CA one step
        self._ca = _ca_next(self._ca)

        cols, _ = shutil.get_terminal_size((80, 24))
        wide = cols >= 100

        lines = self._render_wide(info, cols) if wide else self._render_narrow(info, cols)

        sys.stdout.write(_HOME)
        sys.stdout.write('\n'.join(lines) + '\n')
        sys.stdout.flush()

    # ------------------------------------------------------------------
    # Wide layout (≥ 100 cols)
    # ------------------------------------------------------------------
    def _render_wide(self, info: BarInfo, cols: int) -> list[str]:
        inner = cols - 4   # space inside ║  …  ║

        def row(content: str) -> str:
            # Pad or truncate to inner width, then wrap in box chars + spaces
            # Strip ANSI before measuring length
            visible = _strip_ansi(content)
            pad = max(0, inner - len(visible))
            return f'{_V}  {content}{" " * pad}{_V}'

        def divider() -> str:
            return f'{_ML}{_H * (cols - 2)}{_MR}'

        bars_label = f'{self.n_bars}' if self.n_bars is not None else '∞'
        bar_num    = info.bar_idx + 1

        # ── Header ────────────────────────────────────────────────────
        top   = f'{_TL}{_H * (cols - 2)}{_TR}'
        hdr   = f'{_BOLD}TRANCE-STREAM{_RESET}  seed={info.seed}  mood={info.mood}  {info.bpm:.0f} BPM'

        # ── Bar / chord / filter / FM row ──────────────────────────────
        fm_pct = int(info.fm_depth / 0.55 * 100) if info.fm_depth > 0 else 0
        fm_bar = _mini_bar(info.fm_depth / 0.55, 10, _YELLOW)
        info_row = (
            f'Bar {_BOLD}{bar_num:4d}{_RESET}/{bars_label}'
            f'  Chord: {_BOLD}{info.chord_name:<4}{_RESET}'
            f'  Filter: {_CYAN}{info.filter_hz:6.0f}{_RESET} Hz'
            f'  FM: {fm_bar} {fm_pct:3d}%'
        )

        # ── Track indicators ──────────────────────────────────────────
        def dot(name: str, short: str = None) -> str:
            label = (short or name).upper()
            active = info.tracks_active.get(name, False)
            if active:
                return f'{label} {_GREEN}●{_RESET}'
            else:
                return f'{_DIM}{label} ○{_RESET}'

        tracks_row = '   '.join([
            dot('kick'), dot('pad'), dot('bass'), dot('lead'),
            dot('hihat'), dot('clap'), dot('pulse'),
        ])

        # ── Filter bar ────────────────────────────────────────────────
        # prefix "Filter  " = 8, suffix "  XXXXXX Hz" = 11 → bar_width = inner - 19
        bar_width = max(8, inner - 19)
        filt_filled = _bar(info.filter_slider / 0.877, bar_width, _CYAN)
        filter_row = f'Filter  {filt_filled}  {_CYAN}{info.filter_hz:6.0f} Hz{_RESET}'

        # ── Gate bar (position indicator) ─────────────────────────────
        gate_width = bar_width
        gate_val = (1.0 + math.cos(info.gate_phase * 2 * math.pi + math.pi)) / 2.0
        floor = 1.0 - 0.7
        gate_level = floor + gate_val * 0.7
        gate_pos = int(info.gate_phase * gate_width)
        gate_cells = ['░'] * gate_width
        gate_cells[min(gate_pos, gate_width - 1)] = '●'
        gate_str = ''.join(gate_cells)
        gate_row = f'Gate    {_DIM}{gate_str}{_RESET}  {gate_level:.2f}'

        # ── CA row ────────────────────────────────────────────────────
        ca_color = _YELLOW if info.filter_slider > 0.6 else _CYAN
        # Scale 32 cells to inner width
        ca_inner = inner - 10
        repeat = max(1, ca_inner // self.CA_WIDTH)
        ca_str = ''.join(('█' if c else '░') * repeat for c in self._ca)[:ca_inner]
        ca_row_str = f'{ca_color}{ca_str}{_RESET}  Rule 30'

        # ── Timing row ────────────────────────────────────────────────
        timing_row = (
            f'{_DIM}render={info.render_ms:.0f}ms  '
            f'budget={info.bar_dur_ms:.0f}ms  '
            f'headroom={info.headroom_ms:.0f}ms{_RESET}'
        )

        bottom = f'{_BL}{_H * (cols - 2)}{_BR}'

        return [
            top,
            row(hdr),
            divider(),
            row(info_row),
            divider(),
            row(tracks_row),
            divider(),
            row(filter_row),
            row(gate_row),
            divider(),
            row(ca_row_str),
            divider(),
            row(timing_row),
            bottom,
        ]

    # ------------------------------------------------------------------
    # Narrow layout (< 100 cols)
    # ------------------------------------------------------------------
    def _render_narrow(self, info: BarInfo, cols: int) -> list[str]:
        inner = cols - 4

        def row(content: str) -> str:
            visible = _strip_ansi(content)
            pad = max(0, inner - len(visible))
            return f'{_V}  {content}{" " * pad}{_V}'

        def divider() -> str:
            return f'{_ML}{_H * (cols - 2)}{_MR}'

        bars_label = f'{self.n_bars}' if self.n_bars is not None else '∞'
        bar_num    = info.bar_idx + 1
        fm_pct     = int(info.fm_depth / 0.55 * 100) if info.fm_depth > 0 else 0

        top    = f'{_TL}{_H * (cols - 2)}{_TR}'
        bottom = f'{_BL}{_H * (cols - 2)}{_BR}'

        hdr = f'{_BOLD}TRANCE-STREAM{_RESET}  {info.seed}/{info.mood}  {info.bpm:.0f} BPM'

        info_row = (
            f'Bar {_BOLD}{bar_num}{_RESET}/{bars_label}'
            f'  {_BOLD}{info.chord_name}{_RESET}'
            f'  {_CYAN}{info.filter_hz:.0f}Hz{_RESET}'
            f'  FM:{fm_pct}%'
        )

        def dot(name: str, short: str) -> str:
            active = info.tracks_active.get(name, False)
            if active:
                return f'{short}{_GREEN}●{_RESET}'
            else:
                return f'{_DIM}{short}○{_RESET}'

        tracks_row = '  '.join([
            dot('kick', 'K'), dot('pad', 'P'), dot('bass', 'B'), dot('lead', 'L'),
            dot('hihat', 'H'), dot('clap', 'C'), dot('pulse', 'U'),
        ])

        bar_width = max(8, inner - 9)
        filt_filled = _bar(info.filter_slider / 0.877, bar_width, _CYAN)
        filter_row = f'Filter {filt_filled}'

        gate_width = bar_width
        gate_pos = int(info.gate_phase * gate_width)
        gate_cells = ['░'] * gate_width
        gate_cells[min(gate_pos, gate_width - 1)] = '●'
        gate_row = f'Gate   {_DIM}{"".join(gate_cells)}{_RESET}'

        ca_color = _YELLOW if info.filter_slider > 0.6 else _CYAN
        ca_inner = inner - 10
        repeat = max(1, ca_inner // self.CA_WIDTH)
        ca_str = ''.join(('█' if c else '░') * repeat for c in self._ca)[:ca_inner]
        ca_row_str = f'{ca_color}{ca_str}{_RESET}  R30'

        return [
            top,
            row(hdr),
            divider(),
            row(info_row),
            divider(),
            row(tracks_row),
            divider(),
            row(filter_row),
            row(gate_row),
            divider(),
            row(ca_row_str),
            bottom,
        ]


# ---------------------------------------------------------------------------
# Bar helpers
# ---------------------------------------------------------------------------
def _bar(frac: float, width: int, color: str) -> str:
    """Render a filled progress bar with ANSI color."""
    frac = max(0.0, min(1.0, frac))
    filled = int(frac * width)
    empty  = width - filled
    return f'{color}{"█" * filled}{_RESET}{_DIM}{"░" * empty}{_RESET}'


def _mini_bar(frac: float, width: int, color: str) -> str:
    frac = max(0.0, min(1.0, frac))
    filled = int(frac * width)
    empty  = width - filled
    return f'{color}{"█" * filled}{_DIM}{"░" * empty}{_RESET}'


def _strip_ansi(s: str) -> str:
    """Remove ANSI escape codes to get the visible character count."""
    import re
    return re.sub(r'\033\[[0-9;?]*[a-zA-Z]', '', s)
