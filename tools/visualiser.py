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

import hashlib
import math
import os
import re
import select
import shutil
import sys
import termios
import time
import tty
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

# ---------------------------------------------------------------------------
# ANSI colour/style codes
# ---------------------------------------------------------------------------
_RESET   = '\033[0m'
_BOLD    = '\033[1m'
_DIM     = '\033[2m'
_GREEN   = '\033[92m'   # active track dot
_CYAN    = '\033[96m'   # filter bar / UI accents
_YELLOW  = '\033[93m'
_MAGENTA = '\033[95m'
_WHITE   = '\033[97m'
_HIDE_CURSOR = '\033[?25l'
_SHOW_CURSOR = '\033[?25h'
_HOME        = '\033[H'
_CLEAR       = '\033[2J'

# CA chord palette — one colour per chord index (0-3).
# Chosen to be distinct but not garish; all readable on dark backgrounds.
# Chord 0 (tonic) = cyan (home, stable), 1 = green (lift), 2 = yellow (tension), 3 = magenta (release).
_CA_PALETTE = ['\033[96m', '\033[92m', '\033[93m', '\033[95m']

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

    from song.arcs import filter_cutoff_arc, fm_depth_arc, chord_state_at
    from song.theory import rlpf_to_hz, chord_to_midi, TRANCEGATE_SPEED

    # Chord index — phase-aware, matches SongRenderer exactly
    prog, weights, effective_root = chord_state_at(bar_idx, song)
    cycle_len = sum(weights)
    pos = bar_idx % cycle_len
    cumulative = 0
    chord_idx = 0
    for i, w in enumerate(weights):
        cumulative += w
        if pos < cumulative:
            chord_idx = i % len(prog)
            break

    chord_degrees = prog[chord_idx]
    chord_name = _chord_name(effective_root, chord_degrees, song.scale)

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

# Row number (1-indexed) of the tracks indicator line within the full display.
# top(1) hdr(2) div(3) info(4) div(5) tracks(6)
_TRACKS_ROW = 6

class Visualiser:
    """Full-screen ANSI terminal visualiser.

    The CA history section expands to fill all available terminal rows.
    The spacetime diagram scrolls upward — each bar adds a new row at the
    bottom. The number of visible rows adapts live to terminal height.

    Call start() once before streaming, update(bar_info) each bar,
    stop() on exit to restore the terminal.
    """

    def __init__(self, song, n_bars: Optional[int] = None,
                 ascii_video_playlist=None):
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
        self._last_info: Optional[BarInfo] = None

        # ASCII video playlist state
        # _av_playlist: list of (frames, fps, w, h) tuples
        # _av_playlist_idx: -1 = normal CA mode; 0..N-1 = active video index
        self._av_playlist: list = list(ascii_video_playlist or [])
        self._av_playlist_idx: int = -1
        self._ascii_video_frame_idx: int = 0
        self._ascii_video_start_time: Optional[float] = None

        # stdin state for keybind (set up in start())
        self._stdin_fd: Optional[int] = None
        self._old_termios = None

    @property
    def _ascii_video_mode(self) -> bool:
        return self._av_playlist_idx >= 0

    @property
    def _current_av(self):
        """Return (frames, fps, w, h, fill) for the active video, or None."""
        if self._av_playlist_idx < 0 or not self._av_playlist:
            return None
        return self._av_playlist[self._av_playlist_idx]

    def start(self) -> None:
        # Enter cbreak mode so keypresses are available without Enter.
        # Only affects stdin input flags — stdout ANSI output is unaffected.
        try:
            fd = sys.stdin.fileno()
            self._old_termios = termios.tcgetattr(fd)
            attr = termios.tcgetattr(fd)
            attr[tty.LFLAG] = attr[tty.LFLAG] & ~(termios.ECHO | termios.ICANON)
            attr[tty.CC][termios.VMIN]  = 1
            attr[tty.CC][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, attr)
            self._stdin_fd = fd
        except Exception:
            self._stdin_fd = None

        # Auto-discover all *.txt in ascii_videos/ when no explicit playlist
        # was provided via the constructor.
        if not self._av_playlist:
            import glob
            tools_dir = os.path.dirname(os.path.abspath(__file__))
            repo_dir = os.path.dirname(tools_dir)
            sys.path.insert(0, tools_dir)
            from ascii_video import load_frames
            from ascii_video import load_frames, content_fill_ratio
            for path in sorted(glob.glob(os.path.join(repo_dir, 'ascii_videos', '*.txt'))):
                try:
                    frames, fps, w, h = load_frames(path)
                    if frames:
                        fill = content_fill_ratio(frames, w)
                        self._av_playlist.append((frames, fps, w, h, fill))
                except Exception:
                    pass

        sys.stdout.write(_HIDE_CURSOR + _CLEAR + _HOME)
        sys.stdout.flush()

    def stop(self) -> None:
        cols, rows = shutil.get_terminal_size((80, 24))
        # Place cursor well below the last line we wrote and restore terminal.
        sys.stdout.write(f'\033[{rows};0H' + _SHOW_CURSOR + _RESET + '\n')
        sys.stdout.flush()
        # Restore terminal input settings
        if self._old_termios is not None and self._stdin_fd is not None:
            try:
                termios.tcsetattr(self._stdin_fd, termios.TCSAFLUSH, self._old_termios)
            except Exception:
                pass

    def tick(self, hit_map: dict) -> None:
        """Sub-bar update called 16 times per bar.

        In overlay mode: full-frame redraw with the video frame advanced by
        wall-clock time, giving smooth video playback at ~16 fps within each bar.

        In default mode: overwrite only the track indicator line in-place
        (no full-frame refresh, no flicker).
        """
        if not self._last_info:
            return
        info = self._last_info

        self._poll_keys()

        av = self._current_av
        if av is not None:
            av_frames, av_fps, _av_w, _av_h, _av_fill = av
            # Advance frame index by wall clock then do a full redraw
            now = time.monotonic()
            if self._ascii_video_start_time is None:
                self._ascii_video_start_time = now
            elapsed = now - self._ascii_video_start_time
            self._ascii_video_frame_idx = (
                round(elapsed * av_fps) % len(av_frames)
            )
            cols, rows = shutil.get_terminal_size((80, 24))
            wide = cols >= 100
            fixed = _FIXED_LINES_WIDE if wide else _FIXED_LINES_NARROW
            ca_lines = max(1, rows - fixed)
            lines = self._render(info, cols, rows, wide, ca_lines, hit_map=hit_map)
            sys.stdout.write(_HOME)
            sys.stdout.write('\n'.join(lines))
            sys.stdout.flush()
            return

        cols, _ = shutil.get_terminal_size((80, 24))
        wide = cols >= 100
        inner = cols - 6

        # Percussive voices go ○ between hits — shows the rhythm pattern.
        # Sustained voices stay dim ● — they're always ringing, just not retriggering.
        _PERCUSSIVE = {'kick', 'hihat', 'clap', 'bass'}

        def dot(name: str, short: str = None) -> str:
            label = (short or name).upper()
            active = info.tracks_active.get(name, False)
            hitting = hit_map.get(name, False)
            if not active:
                return f'{_DIM}{label} ○{_RESET}' if wide else f'{_DIM}{short}○{_RESET}'
            if hitting:
                return (f'{label} {_BOLD}{_GREEN}●{_RESET}' if wide
                        else f'{_BOLD}{_GREEN}{short}●{_RESET}')
            elif name in _PERCUSSIVE:
                # Empty between hits — rhythm visible
                return f'{label} ○' if wide else f'{short}○'
            else:
                # Sustained — dim dot shows it's active and droning
                return (f'{_DIM}{label} {_GREEN}●{_RESET}' if wide
                        else f'{_DIM}{_GREEN}{short}●{_RESET}')

        if wide:
            tracks_row = '   '.join([
                dot('kick'), dot('pad'), dot('bass'), dot('lead'),
                dot('hihat'), dot('clap'), dot('pulse'),
            ])
        else:
            tracks_row = '  '.join([
                dot('kick', 'K'), dot('pad', 'P'), dot('bass', 'B'), dot('lead', 'L'),
                dot('hihat', 'H'), dot('clap', 'C'), dot('pulse', 'U'),
            ])

        visible = _strip_ansi(tracks_row)
        pad = max(0, inner - len(visible))
        line = f'{_V}  {tracks_row}{" " * pad}  {_V}'

        # Move cursor to tracks row, overwrite, return cursor to bottom
        sys.stdout.write(f'\033[{_TRACKS_ROW};1H{line}')
        sys.stdout.flush()

    def _poll_keys(self) -> None:
        if self._stdin_fd is None:
            return
        if select.select([sys.stdin], [], [], 0)[0]:
            chunk = os.read(self._stdin_fd, 256)
            if b'v' in chunk and self._av_playlist:
                # Cycle: 0 → 1 → ... → N-1 → -1 (normal CA) → 0 → ...
                if self._av_playlist_idx < len(self._av_playlist) - 1:
                    self._av_playlist_idx += 1
                else:
                    self._av_playlist_idx = -1
                if self._av_playlist_idx >= 0:
                    self._ascii_video_start_time = time.monotonic()
                    self._ascii_video_frame_idx = 0

    def update(self, info: BarInfo) -> None:
        """Advance CA, record history, re-render the full display in place."""
        self._poll_keys()
        cols, rows = shutil.get_terminal_size((80, 24))
        wide   = cols >= 100
        # CA width = full usable inner width (label is overlaid, not appended)
        ca_w = max(8, cols - 6)

        # Resize CA array when terminal width changes, carrying live state across.
        if ca_w != self._ca_width:
            seed_int = int(hashlib.md5(self.song.seed.encode()).hexdigest(), 16) & 0xFFFFFFFF
            rng = np.random.default_rng(seed_int ^ ca_w)
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

        # Record this row in history: (ca_row, filter_slider, chord_idx)
        self._ca_history.append((self._ca.copy(), info.filter_slider, info.chord_idx))

        # Compute how many CA history lines fit given the fixed UI chrome.
        fixed = _FIXED_LINES_WIDE if wide else _FIXED_LINES_NARROW
        ca_lines = max(1, rows - fixed)

        # Keep history buffer at most as deep as we'll ever display + a small pad
        self._ca_history = deque(self._ca_history, maxlen=max(ca_lines + 4, 200))

        self._last_info = info
        lines = self._render(info, cols, rows, wide, ca_lines)

        sys.stdout.write(_HOME)
        sys.stdout.write('\n'.join(lines))
        # Don't add trailing newline — keep cursor inside the box.
        sys.stdout.flush()

    def ca_density(self) -> float:
        """Fraction of live (1) cells in the current CA row. 0.0–1.0.

        Used by the renderer to drive delay wet: dense CA = more wash.
        Returns 0.5 before any bars have been processed.
        """
        if len(self._ca) == 0:
            return 0.5
        return float(np.mean(self._ca))

    def ca_voicing_offset(self) -> int:
        """Semitone offset for the lead derived from two centre CA bits.

        Reads bits at positions ca_width//2 and ca_width//2+1 to form a
        2-bit index into (0, 2, 5, 7) — SA's confirmed voicing offsets.
        Returns 0 before any bars have been processed.
        """
        _OFFSETS = (0, 2, 5, 7)
        if len(self._ca) < 2:
            return 0
        mid = len(self._ca) // 2
        idx = (int(self._ca[mid]) << 1) | int(self._ca[mid + 1])
        return _OFFSETS[idx]

    # ------------------------------------------------------------------
    # Unified renderer — wide and narrow share the same structure,
    # differing only in label verbosity and whether timing row appears.
    # ------------------------------------------------------------------
    def _render(self, info: BarInfo, cols: int, rows: int,
                wide: bool, ca_lines: int,
                hit_map: Optional[dict] = None) -> list[str]:
        inner = cols - 6   # usable width: ║(1) + sp(2) + content + sp(2) + ║(1)

        def row(content: str) -> str:
            visible = _strip_ansi(content)
            pad = max(0, inner - len(visible))
            return f'{_V}  {content}{" " * pad}  {_V}'

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
        _PERCUSSIVE = {'kick', 'hihat', 'clap', 'bass'}
        _hm = hit_map or {}

        def dot(name: str, short: str = None) -> str:
            label = (short or name).upper()
            active  = info.tracks_active.get(name, False)
            hitting = _hm.get(name, False)
            if not active:
                return (f'{_DIM}{label} ○{_RESET}' if wide else f'{_DIM}{short}○{_RESET}')
            if hitting:
                return (f'{label} {_BOLD}{_GREEN}●{_RESET}' if wide
                        else f'{_BOLD}{_GREEN}{short}●{_RESET}')
            elif name in _PERCUSSIVE:
                return f'{label} ○' if wide else f'{short}○'
            else:
                return (f'{_DIM}{label} {_GREEN}●{_RESET}' if wide
                        else f'{_DIM}{_GREEN}{short}●{_RESET}')

        if wide:
            tracks_row = '   '.join([
                dot('kick'), dot('pad'), dot('bass'), dot('lead'),
                dot('hihat'), dot('clap'), dot('pulse'),
            ])
        else:
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
        ca_inner = inner   # cells fill the full inner width
        label_txt = 'Rule 30'

        history_slice = list(self._ca_history)[-ca_lines:]
        pad_count     = ca_lines - len(history_slice)
        blank_row_str = f'{_DIM}{"░" * ca_inner}{_RESET}'

        # ASCII video overlay: grab current frame once for the whole render
        av_frame = None
        av_row_src_start = av_col_src_start = 0.0
        av_scaled_w = av_scaled_h = 1
        av_w = av_h = 1   # overridden below when a video is active
        _cur_av = self._current_av
        # Whether this video uses contain+transparent or cover+opaque rendering.
        av_contain = False

        if _cur_av is not None:
            _av_frames, _av_fps, av_w, av_h, av_fill = _cur_av
            frame_idx = self._ascii_video_frame_idx % len(_av_frames)
            av_frame = _av_frames[frame_idx]

            # Full-frame art (fill ≥ 0.9, e.g. Bad Apple, Star Wars): cover mode.
            #   Scale to fill the CA area, center-crop excess, space = opaque dim-blue.
            # Logo art (fill < 0.9, e.g. Death Angel): contain mode.
            #   Scale to fit entirely, center on both axes, space = transparent CA.
            # Cell aspect ratio 0.5 cancels in both axes; work in char-count space.
            if av_fill >= 0.9:
                scale = max(ca_inner / max(av_w, 1), ca_lines / max(av_h, 1))
                av_scaled_w = max(ca_inner, int(av_w * scale))
                av_scaled_h = max(ca_lines, int(av_h * scale))
                av_col_src_start = (av_scaled_w - ca_inner) / 2.0
                av_row_src_start  = (av_scaled_h - ca_lines) / 2.0
            else:
                av_contain = True
                scale = min(ca_inner / max(av_w, 1), ca_lines / max(av_h, 1))
                av_scaled_w = max(1, int(av_w * scale))
                av_scaled_h = max(1, int(av_h * scale))
                av_col_src_start = -(ca_inner - av_scaled_w) / 2.0
                av_row_src_start  = -(ca_lines - av_scaled_h) / 2.0

        def _av_colored_row(raw: str, display_row: int) -> str:
            """Color every cell in a CA row using the current video frame."""
            src_r = display_row + av_row_src_start
            if av_contain and (src_r < 0 or src_r >= av_scaled_h):
                return f'{_DIM}{raw}{_RESET}'
            src_row_idx = min(int(src_r / av_scaled_h * av_h), av_h - 1)
            src_line = av_frame[src_row_idx] if src_row_idx < len(av_frame) else ''
            chars = []
            for col_idx, ch in enumerate(raw):
                src_c = col_idx + av_col_src_start
                if av_contain and (src_c < 0 or src_c >= av_scaled_w):
                    chars.append(f'{_DIM}{ch}{_RESET}')
                    continue
                src_col_idx = min(int(src_c / av_scaled_w * av_w), av_w - 1)
                src_ch = src_line[src_col_idx] if src_col_idx < len(src_line) else ' '
                if av_contain and src_ch == ' ':
                    chars.append(f'{_DIM}{ch}{_RESET}')
                else:
                    chars.append(f'{_av_color(src_ch)}{ch}{_RESET}')
            return ''.join(chars)

        ca_rendered = []

        # Padding rows at top (before history fills up) — still get overlay coloring
        blank_raw = '░' * ca_inner
        for pad_i in range(pad_count):
            display_row = pad_i   # top of the full ca_lines area
            if av_frame is not None:
                content = _av_colored_row(blank_raw, display_row)
            else:
                content = f'{_DIM}{blank_raw}{_RESET}'
            ca_rendered.append(row(content))

        for i, entry in enumerate(history_slice):
            ca_row, fslider, chord_idx = entry
            display_row = pad_count + i   # position in the full ca_lines area
            age = len(history_slice) - i   # 1 = newest

            # Build cell string — 1 char per cell, fit to ca_inner
            raw = ''.join('█' if c else '░' for c in ca_row)
            if len(raw) < ca_inner:
                raw = raw + '░' * (ca_inner - len(raw))
            else:
                raw = raw[:ca_inner]

            if av_frame is not None:
                content = _av_colored_row(raw, display_row)
            else:
                # Default mode: hue = chord palette, brightness = filter arc
                ca_color = _CA_PALETTE[chord_idx % len(_CA_PALETTE)]
                if fslider < 0.5:
                    bright = _DIM
                elif fslider > 0.7:
                    bright = _BOLD
                else:
                    bright = ''
                content = f'{bright}{ca_color}{raw}{_RESET}'

            if age == 1 and av_frame is None:
                # Newest row label only in default mode
                cells_w = ca_inner - len(label_txt)
                ca_color = _CA_PALETTE[chord_idx % len(_CA_PALETTE)]
                bright = _DIM if fslider < 0.5 else (_BOLD if fslider > 0.7 else '')
                ca_rendered.append(
                    f'{_V}  {bright}{ca_color}{raw[:cells_w]}{_RESET}'
                    f'{_DIM}{label_txt}{_RESET}  {_V}'
                )
            else:
                ca_rendered.append(row(content))

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


# Characters ordered roughly by visual density (darkest → brightest).
# Used to map ASCII video source pixels to ANSI brightness in overlay mode.
_AV_DARK   = set(' .,`\'":;-_')
_AV_MID    = set('!|/\\()[]{}+~?<>^*')
_AV_BRIGHT = set('#@%MW&$X08B')

def _av_color(src_ch: str) -> str:
    """Map an ASCII video source character to an ANSI color code for overlay."""
    if src_ch in _AV_BRIGHT:
        return _BOLD + _WHITE
    if src_ch in _AV_DARK:
        return _DIM + '\033[34m'   # dim blue — dark regions recede
    return _CYAN                   # mid chars get cyan
