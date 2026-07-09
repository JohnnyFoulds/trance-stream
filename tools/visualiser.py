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
import re
import shutil
import sys
from collections import deque
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

# Fixed UI lines (excluding the CA history section):
#   top border, header, divider, info, divider, tracks, divider,
#   filter, gate, divider, [timing (wide only),] divider, bottom border
_FIXED_LINES_WIDE   = 13   # top + hdr + div + info + div + tracks + div + filt + gate + div + timing + div + bottom
_FIXED_LINES_NARROW = 11   # same minus timing+div

class Visualiser:
    """Full-screen ANSI terminal visualiser.

    The CA history section expands to fill all available terminal rows.
    The spacetime diagram scrolls upward — each bar adds a new row at the
    bottom. The number of visible rows adapts live to terminal height.

    Call start() once before streaming, update(bar_info) each bar,
    stop() on exit to restore the terminal.
    """

    def __init__(self, song, n_bars: Optional[int] = None):
        self.song   = song
        self.n_bars = n_bars
        # CA width adapts to terminal width — initialised on first update().
        self._ca: np.ndarray = np.zeros(0, dtype=np.int32)
        self._ca_width: int  = 0
        self._prev_chord_idx = -1
        self._fm_ever_active = False
        # Rolling history: each entry is (ca_row_copy, filter_slider).
        # Rows may differ in width if the terminal was resized; the renderer
        # handles that by cropping/padding each row to the current ca_inner.
        self._ca_history: deque = deque(maxlen=200)

    def start(self) -> None:
        sys.stdout.write(_HIDE_CURSOR + _CLEAR + _HOME)
        sys.stdout.flush()

    def stop(self) -> None:
        cols, rows = shutil.get_terminal_size((80, 24))
        # Place cursor well below the last line we wrote and restore terminal.
        sys.stdout.write(f'\033[{rows};0H' + _SHOW_CURSOR + _RESET + '\n')
        sys.stdout.flush()

    def update(self, info: BarInfo) -> None:
        """Advance CA, record history, re-render the full display in place."""
        cols, rows = shutil.get_terminal_size((80, 24))
        wide   = cols >= 100
        # CA width = usable inner width minus label overhead ("  Rule 30" = 9, "  R30" = 5)
        label_len = 9 if wide else 5
        ca_inner  = (cols - 4) - label_len   # inner = cols-4; minus label
        ca_w      = max(8, ca_inner)

        # Resize CA array when terminal width changes, carrying live state across.
        if ca_w != self._ca_width:
            rng = np.random.default_rng(self.song.root_midi + ca_w)
            new_ca = rng.integers(0, 2, size=ca_w, dtype=np.int32)
            # Overlay existing state into centre of new array for continuity
            if self._ca_width > 0:
                copy_w = min(self._ca_width, ca_w)
                offset = (ca_w - copy_w) // 2
                new_ca[offset: offset + copy_w] = self._ca[:copy_w]
            self._ca = new_ca
            self._ca_width = ca_w

        # Inject musical events into CA before advancing.
        # Events are spread across the full width proportionally.
        mid = ca_w // 2
        if info.chord_idx != self._prev_chord_idx and self._prev_chord_idx >= 0:
            self._ca[0] = 1              # chord change: left edge
        self._prev_chord_idx = info.chord_idx

        if info.fm_depth > 0 and not self._fm_ever_active:
            self._ca[mid] = 1            # FM onset: centre
            self._fm_ever_active = True

        # 4-bar phrase marker: inject near-centre so it seeds both flanks
        phrase_pos = max(0, mid - ca_w // 8)
        self._ca[phrase_pos] = 1 if info.bar_idx % 4 == 0 else 0

        # Advance CA one step
        self._ca = _ca_next(self._ca)

        # Record this row in history (copy + current energy colour tag)
        self._ca_history.append((self._ca.copy(), info.filter_slider))

        # Compute how many CA history lines fit given the fixed UI chrome.
        fixed = _FIXED_LINES_WIDE if wide else _FIXED_LINES_NARROW
        ca_lines = max(1, rows - fixed)

        # Keep history buffer at most as deep as we'll ever display + a small pad
        self._ca_history = deque(self._ca_history, maxlen=max(ca_lines + 4, 200))

        lines = self._render(info, cols, rows, wide, ca_lines)

        sys.stdout.write(_HOME)
        sys.stdout.write('\n'.join(lines))
        # Don't add trailing newline — keep cursor inside the box.
        sys.stdout.flush()

    # ------------------------------------------------------------------
    # Unified renderer — wide and narrow share the same structure,
    # differing only in label verbosity and whether timing row appears.
    # ------------------------------------------------------------------
    def _render(self, info: BarInfo, cols: int, rows: int,
                wide: bool, ca_lines: int) -> list[str]:
        inner = cols - 4   # usable width inside ║  …  ║

        def row(content: str) -> str:
            visible = _strip_ansi(content)
            pad = max(0, inner - len(visible))
            return f'{_V}  {content}{" " * pad}{_V}'

        def divider() -> str:
            return f'{_ML}{_H * (cols - 2)}{_MR}'

        bars_label = f'{self.n_bars}' if self.n_bars is not None else '∞'
        bar_num    = info.bar_idx + 1
        fm_pct     = int(info.fm_depth / 0.55 * 100) if info.fm_depth > 0 else 0

        # ── Header ────────────────────────────────────────────────────
        top = f'{_TL}{_H * (cols - 2)}{_TR}'
        if wide:
            hdr = f'{_BOLD}TRANCE-STREAM{_RESET}  seed={info.seed}  mood={info.mood}  {info.bpm:.0f} BPM'
        else:
            hdr = f'{_BOLD}TRANCE-STREAM{_RESET}  {info.seed}/{info.mood}  {info.bpm:.0f} BPM'

        # ── Info row ──────────────────────────────────────────────────
        if wide:
            fm_bar   = _mini_bar(info.fm_depth / 0.55, 10, _YELLOW)
            info_row = (
                f'Bar {_BOLD}{bar_num:4d}{_RESET}/{bars_label}'
                f'  Chord: {_BOLD}{info.chord_name:<4}{_RESET}'
                f'  Filter: {_CYAN}{info.filter_hz:6.0f}{_RESET} Hz'
                f'  FM: {fm_bar} {fm_pct:3d}%'
            )
        else:
            info_row = (
                f'Bar {_BOLD}{bar_num}{_RESET}/{bars_label}'
                f'  {_BOLD}{info.chord_name}{_RESET}'
                f'  {_CYAN}{info.filter_hz:.0f}Hz{_RESET}'
                f'  FM:{fm_pct}%'
            )

        # ── Track indicators ──────────────────────────────────────────
        if wide:
            def dot(name: str, short: str = None) -> str:
                label = (short or name).upper()
                active = info.tracks_active.get(name, False)
                return (f'{label} {_GREEN}●{_RESET}' if active
                        else f'{_DIM}{label} ○{_RESET}')
            tracks_row = '   '.join([
                dot('kick'), dot('pad'), dot('bass'), dot('lead'),
                dot('hihat'), dot('clap'), dot('pulse'),
            ])
        else:
            def dot(name: str, short: str) -> str:
                active = info.tracks_active.get(name, False)
                return (f'{short}{_GREEN}●{_RESET}' if active
                        else f'{_DIM}{short}○{_RESET}')
            tracks_row = '  '.join([
                dot('kick', 'K'), dot('pad', 'P'), dot('bass', 'B'), dot('lead', 'L'),
                dot('hihat', 'H'), dot('clap', 'C'), dot('pulse', 'U'),
            ])

        # ── Filter bar ────────────────────────────────────────────────
        if wide:
            bar_width  = max(8, inner - 19)
            filt_row   = f'Filter  {_bar(info.filter_slider / 0.877, bar_width, _CYAN)}  {_CYAN}{info.filter_hz:6.0f} Hz{_RESET}'
        else:
            bar_width  = max(8, inner - 9)
            filt_row   = f'Filter {_bar(info.filter_slider / 0.877, bar_width, _CYAN)}'

        # ── Gate bar ──────────────────────────────────────────────────
        gate_val   = (1.0 + math.cos(info.gate_phase * 2 * math.pi + math.pi)) / 2.0
        gate_level = 0.3 + gate_val * 0.7
        gate_pos   = int(info.gate_phase * bar_width)
        gate_cells = ['░'] * bar_width
        gate_cells[min(gate_pos, bar_width - 1)] = '●'
        gate_str   = ''.join(gate_cells)
        if wide:
            gate_row = f'Gate    {_DIM}{gate_str}{_RESET}  {gate_level:.2f}'
        else:
            gate_row = f'Gate   {_DIM}{gate_str}{_RESET}'

        # ── CA spacetime diagram ──────────────────────────────────────
        # One terminal character per CA cell at the current terminal width.
        # History rows may be narrower/wider than ca_inner if the terminal
        # was resized mid-session — crop or pad each stored row to fit.
        ca_label   = '  Rule 30' if wide else '  R30'
        ca_inner   = inner - len(ca_label)   # characters available for CA cells

        history_slice = list(self._ca_history)[-ca_lines:]
        blank_row_str = f'{_DIM}{"░" * ca_inner}{_RESET}'
        pad_count = ca_lines - len(history_slice)

        ca_rendered = []
        for i, (ca_row, fslider) in enumerate(history_slice):
            age = len(history_slice) - i          # 1 = newest
            ca_color = _YELLOW if fslider > 0.6 else _CYAN
            prefix   = '' if age == 1 else _DIM

            # Build cell string — 1 char per cell, then fit to ca_inner
            raw = ''.join('█' if c else '░' for c in ca_row)
            if len(raw) < ca_inner:
                raw = raw + '░' * (ca_inner - len(raw))   # pad narrow rows
            else:
                raw = raw[:ca_inner]                       # crop wide rows

            label = ca_label if age == 1 else ' ' * len(ca_label)
            ca_rendered.append(row(f'{prefix}{ca_color}{raw}{_RESET}{label}'))

        # ── Assemble ──────────────────────────────────────────────────
        bottom = f'{_BL}{_H * (cols - 2)}{_BR}'

        out = [
            top,
            row(hdr),
            divider(),
            row(info_row),
            divider(),
            row(tracks_row),
            divider(),
            row(filt_row),
            row(gate_row),
            divider(),
        ]

        # Blank padding rows (before history fills up)
        for _ in range(pad_count):
            out.append(row(blank_row_str))

        out.extend(ca_rendered)

        if wide:
            timing = (
                f'{_DIM}render={info.render_ms:.0f}ms  '
                f'budget={info.bar_dur_ms:.0f}ms  '
                f'headroom={info.headroom_ms:.0f}ms{_RESET}'
            )
            out.append(divider())
            out.append(row(timing))

        out.append(bottom)
        return out


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
    return re.sub(r'\033\[[0-9;?]*[a-zA-Z]', '', s)
