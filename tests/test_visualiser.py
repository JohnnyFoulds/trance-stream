# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for the track indicator logic in tools/visualiser.py.

Key invariants:
1. _render() uses full hit/percussive/sustained logic — not just active/inactive.
2. Percussive voices show ○ when active but not hitting.
3. Sustained voices show dim ● when active but not hitting.
4. Any voice shows bold bright ● when hitting.
5. Inactive voices always show dim ○ regardless of hit_map.
6. tick() in overlay mode passes hit_map through to _render().
7. tick() in default mode still produces the correct indicator line.
8. hit_map=None (bar-boundary render) falls back to all-not-hitting gracefully.
"""

from __future__ import annotations

import re
import sys
import pathlib

import pytest

REPO_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / 'tools'))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_ansi(s: str) -> str:
    return re.sub(r'\033\[[0-9;?]*[a-zA-Z]', '', s)


def _make_viz(n_bars: int = 64, seed: str = 'sunrise'):
    from song.builder import build_song
    from visualiser import Visualiser
    song = build_song(seed, mood='uplifting', bpm=140.0, total_bars=n_bars)
    return Visualiser(song, n_bars), song


def _make_info(bar_idx: int, song):
    from visualiser import make_bar_info
    return make_bar_info(bar_idx, song, 100.0, 1714.0)


def _tracks_line(viz, info, hit_map, cols=120, rows=40, ca_lines=27):
    """Render and return the stripped tracks row text."""
    lines = viz._render(info, cols, rows, cols >= 100, ca_lines, hit_map=hit_map)
    # Row 5 (0-indexed): top/hdr/div/info/div/tracks
    return _strip_ansi(lines[5])


PERCUSSIVE = ['kick', 'hihat', 'clap', 'bass']
SUSTAINED  = ['pad', 'lead', 'pulse']
ALL_TRACKS = PERCUSSIVE + SUSTAINED


def _all_active_info(song):
    """Return a BarInfo where all tracks are active (late bar)."""
    return _make_info(120, song)


# ---------------------------------------------------------------------------
# Indicator state machine
# ---------------------------------------------------------------------------

class TestIndicatorStates:
    """The three-state dot logic: hitting / active-not-hitting / inactive."""

    def setup_method(self):
        self.viz, self.song = _make_viz()
        self.info = _all_active_info(self.song)

    def test_hitting_shows_filled_dot(self):
        for track in ALL_TRACKS:
            hit_map = {t: (t == track) for t in ALL_TRACKS}
            line = _tracks_line(self.viz, self.info, hit_map)
            label = track.upper()
            assert f'{label} ●' in line, \
                f'{track}: expected bold ● when hitting, got: {line}'

    def test_percussive_shows_empty_circle_when_not_hitting(self):
        hit_map = {t: False for t in ALL_TRACKS}
        line = _tracks_line(self.viz, self.info, hit_map)
        for track in PERCUSSIVE:
            label = track.upper()
            assert f'{label} ○' in line, \
                f'{track}: expected ○ when active but not hitting, got: {line}'

    def test_sustained_shows_filled_dot_when_not_hitting(self):
        hit_map = {t: False for t in ALL_TRACKS}
        line = _tracks_line(self.viz, self.info, hit_map)
        for track in SUSTAINED:
            label = track.upper()
            assert f'{label} ●' in line, \
                f'{track}: expected dim ● when active droning, got: {line}'

    def test_inactive_shows_empty_circle_regardless_of_hit(self):
        # hihat, clap, pulse are not active until late bars (sunrise seed stage_bars)
        # Use bar 0 where only kick + pad are active
        info = _make_info(0, self.song)
        hit_map = {t: True for t in ALL_TRACKS}  # even if hit_map says hitting
        line = _tracks_line(self.viz, info, hit_map)
        for track in ['hihat', 'clap', 'pulse', 'lead']:
            label = track.upper()
            assert f'{label} ○' in line, \
                f'{track}: expected ○ when not yet active, got: {line}'

    def test_hitting_overrides_percussive_empty_rule(self):
        # When a percussive voice IS hitting it shows ● not ○
        for track in PERCUSSIVE:
            hit_map = {t: (t == track) for t in ALL_TRACKS}
            line = _tracks_line(self.viz, self.info, hit_map)
            label = track.upper()
            assert f'{label} ●' in line, \
                f'{track}: percussive should show ● when hitting, got: {line}'

    def test_no_hit_map_does_not_crash(self):
        # hit_map=None is the bar-boundary case — should render cleanly
        line = _tracks_line(self.viz, self.info, hit_map=None)
        # With no hit_map, percussive should show ○, sustained should show ●
        for track in PERCUSSIVE:
            assert f'{track.upper()} ○' in line, \
                f'{track}: expected ○ with no hit_map, got: {line}'
        for track in SUSTAINED:
            assert f'{track.upper()} ●' in line, \
                f'{track}: expected ● with no hit_map, got: {line}'


# ---------------------------------------------------------------------------
# Consistency: tick() must pass hit_map to _render() in overlay mode
# ---------------------------------------------------------------------------

class TestTickOverlayPassesHitMap:
    """Regression test for the bug where overlay mode ignored hit_map."""

    def setup_method(self):
        self.viz, self.song = _make_viz()
        # Seed some CA history so _render() has something to work with
        info = _all_active_info(self.song)
        for _ in range(3):
            self.viz._ca_history.append(
                (self.viz._ca if len(self.viz._ca) > 0
                 else __import__('numpy').zeros(80, dtype='int32'),
                 0.6, 0)
            )
        self.info = info
        self.viz._last_info = info

    def _capture_tick_output(self, hit_map, overlay: bool) -> str:
        """Run tick() capturing stdout, return stripped full output."""
        import io
        import unittest.mock as mock
        dummy_playlist = [([[' ' * 60] * 32], 30, 60, 32)]
        self.viz._av_playlist = dummy_playlist
        self.viz._av_playlist_idx = 0 if overlay else -1
        self.viz._ascii_video_start_time = None
        self.viz._stdin_fd = None

        buf = io.StringIO()
        import sys as _sys
        # Force wide terminal so full labels (KICK, BASS, PAD…) are used
        with mock.patch('shutil.get_terminal_size', return_value=(120, 40)):
            old_stdout = _sys.stdout
            _sys.stdout = buf
            try:
                self.viz.tick(hit_map)
            finally:
                _sys.stdout = old_stdout

        return _strip_ansi(buf.getvalue())

    def test_overlay_mode_shows_hitting_dot(self):
        hit_map = {t: (t == 'kick') for t in ALL_TRACKS}
        output = self._capture_tick_output(hit_map, overlay=True)
        assert 'KICK ●' in output, \
            f'overlay mode: KICK should show ● when hitting, got:\n{output}'

    def test_overlay_mode_shows_percussive_empty(self):
        hit_map = {t: False for t in ALL_TRACKS}
        output = self._capture_tick_output(hit_map, overlay=True)
        assert 'BASS ○' in output, \
            f'overlay mode: BASS should show ○ when not hitting, got:\n{output}'

    def test_overlay_mode_shows_sustained_droning(self):
        hit_map = {t: False for t in ALL_TRACKS}
        output = self._capture_tick_output(hit_map, overlay=True)
        assert 'PAD ●' in output, \
            f'overlay mode: PAD should show ● when droning, got:\n{output}'

    def test_default_mode_shows_hitting_dot(self):
        hit_map = {t: (t == 'kick') for t in ALL_TRACKS}
        output = self._capture_tick_output(hit_map, overlay=False)
        assert 'KICK ●' in output, \
            f'default mode: KICK should show ● when hitting, got:\n{output}'

    def test_default_mode_shows_percussive_empty(self):
        hit_map = {t: False for t in ALL_TRACKS}
        output = self._capture_tick_output(hit_map, overlay=False)
        assert 'BASS ○' in output, \
            f'default mode: BASS should show ○ when not hitting, got:\n{output}'


# ---------------------------------------------------------------------------
# Narrow layout (compact mode)
# ---------------------------------------------------------------------------

class TestNarrowLayout:
    """Compact layout uses single-char abbreviations — same logic must apply."""

    def setup_method(self):
        self.viz, self.song = _make_viz()
        self.info = _all_active_info(self.song)

    def _narrow_tracks_line(self, hit_map):
        lines = self.viz._render(self.info, 80, 24, False, 11, hit_map=hit_map)
        return _strip_ansi(lines[5])

    def test_narrow_hitting_shows_dot(self):
        hit_map = {t: (t == 'kick') for t in ALL_TRACKS}
        line = self._narrow_tracks_line(hit_map)
        assert 'K●' in line, f'narrow: K should show ● when hitting, got: {line}'

    def test_narrow_percussive_empty(self):
        hit_map = {t: False for t in ALL_TRACKS}
        line = self._narrow_tracks_line(hit_map)
        assert 'B○' in line, f'narrow: B (bass) should show ○ when not hitting, got: {line}'

    def test_narrow_sustained_droning(self):
        hit_map = {t: False for t in ALL_TRACKS}
        line = self._narrow_tracks_line(hit_map)
        assert 'P●' in line, f'narrow: P (pad) should show ● when droning, got: {line}'


# ---------------------------------------------------------------------------
# Playlist cycling
# ---------------------------------------------------------------------------

def _dummy_video(n: int = 1) -> tuple:
    """Return a minimal (frames, fps, w, h) tuple for testing."""
    return ([[' ' * 10] * 5] * n, 15, 10, 5)


class TestPlaylistCycling:
    """v-key cycles through playlist entries then back to normal CA mode."""

    def setup_method(self):
        self.viz, _ = _make_viz()
        self.viz._stdin_fd = None

    def _press_v(self):
        """Simulate a single 'v' keypress."""
        self.viz._av_playlist  # ensure property exists
        if self.viz._av_playlist:
            if self.viz._av_playlist_idx < len(self.viz._av_playlist) - 1:
                self.viz._av_playlist_idx += 1
            else:
                self.viz._av_playlist_idx = -1
            if self.viz._av_playlist_idx >= 0:
                self.viz._ascii_video_start_time = 0.0
                self.viz._ascii_video_frame_idx = 0

    def test_empty_playlist_stays_normal(self):
        self.viz._av_playlist = []
        self.viz._av_playlist_idx = -1
        self._press_v()
        assert self.viz._av_playlist_idx == -1
        assert not self.viz._ascii_video_mode

    def test_single_video_cycle(self):
        self.viz._av_playlist = [_dummy_video()]
        self.viz._av_playlist_idx = -1
        # -1 → 0
        self._press_v()
        assert self.viz._av_playlist_idx == 0
        assert self.viz._ascii_video_mode
        # 0 → -1
        self._press_v()
        assert self.viz._av_playlist_idx == -1
        assert not self.viz._ascii_video_mode

    def test_two_video_full_cycle(self):
        self.viz._av_playlist = [_dummy_video(), _dummy_video()]
        self.viz._av_playlist_idx = -1
        self._press_v()
        assert self.viz._av_playlist_idx == 0   # first video
        self._press_v()
        assert self.viz._av_playlist_idx == 1   # second video
        self._press_v()
        assert self.viz._av_playlist_idx == -1  # normal CA
        self._press_v()
        assert self.viz._av_playlist_idx == 0   # wraps back to first

    def test_start_time_reset_on_activation(self):
        self.viz._av_playlist = [_dummy_video()]
        self.viz._av_playlist_idx = -1
        self.viz._ascii_video_start_time = None
        self._press_v()
        assert self.viz._av_playlist_idx == 0
        assert self.viz._ascii_video_start_time is not None

    def test_start_time_unchanged_on_deactivation(self):
        self.viz._av_playlist = [_dummy_video()]
        self.viz._av_playlist_idx = 0
        self.viz._ascii_video_start_time = 42.0
        self._press_v()
        assert self.viz._av_playlist_idx == -1
        # start_time should not be reset when going back to CA mode
        assert self.viz._ascii_video_start_time == 42.0

    def test_current_av_returns_none_in_normal_mode(self):
        self.viz._av_playlist = [_dummy_video()]
        self.viz._av_playlist_idx = -1
        assert self.viz._current_av is None

    def test_current_av_returns_tuple_when_active(self):
        vid = _dummy_video()
        self.viz._av_playlist = [vid]
        self.viz._av_playlist_idx = 0
        assert self.viz._current_av is vid
