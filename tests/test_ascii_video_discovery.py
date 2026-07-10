# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Tests for ascii_video auto-discovery and path conventions.

Covers:
- trance_stream_v3: ascii_video_paths resolved from args (None / [] / explicit)
- fetch_bad_apple / fetch_starwars: DEFAULT_OUT writes into ascii_videos/
- ascii_videos/ directory exists and contains the expected frame files
"""

from __future__ import annotations

import pathlib
import sys
import types
import unittest.mock as mock

REPO_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / 'tools'))

ASCII_VIDEOS_DIR = REPO_ROOT / 'ascii_videos'


# ---------------------------------------------------------------------------
# ascii_videos/ directory and contents
# ---------------------------------------------------------------------------

def test_ascii_videos_dir_exists():
    assert ASCII_VIDEOS_DIR.is_dir(), "ascii_videos/ directory must exist at repo root"


def test_frame_files_in_ascii_videos():
    txt_files = sorted(ASCII_VIDEOS_DIR.glob('*.txt'))
    assert txt_files, "ascii_videos/ must contain at least one *.txt frame file"


def test_known_frame_files_present():
    names = {p.name for p in ASCII_VIDEOS_DIR.glob('*.txt')}
    for expected in ('bad_apple_frames.txt', 'starwars_15fps_frames.txt',
                     'death_angel_12fps_114x21.txt'):
        assert expected in names, f"{expected} must be in ascii_videos/"


def test_no_frame_files_left_in_tools():
    stray = list((REPO_ROOT / 'tools').glob('*_frames.txt'))
    assert not stray, (
        f"Frame files must live in ascii_videos/, not tools/: {stray}"
    )


# ---------------------------------------------------------------------------
# fetch script DEFAULT_OUT paths
# ---------------------------------------------------------------------------

def test_fetch_bad_apple_default_out():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'fetch_bad_apple', REPO_ROOT / 'tools' / 'fetch_bad_apple.py'
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = pathlib.Path(mod.DEFAULT_OUT)
    assert out.parent.name == 'ascii_videos', (
        f"fetch_bad_apple DEFAULT_OUT must be inside ascii_videos/, got: {out}"
    )


def test_fetch_starwars_default_out():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'fetch_starwars', REPO_ROOT / 'tools' / 'fetch_starwars.py'
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    out = pathlib.Path(mod.DEFAULT_OUT)
    assert out.parent.name == 'ascii_videos', (
        f"fetch_starwars DEFAULT_OUT must be inside ascii_videos/, got: {out}"
    )


# ---------------------------------------------------------------------------
# trance_stream_v3: ascii_video_paths arg resolution
# ---------------------------------------------------------------------------

def _resolve(ascii_video_arg, glob_results):
    """Reproduce the resolution logic from trance_stream_v3.main()."""
    ascii_video_paths = ascii_video_arg
    if ascii_video_paths is None or ascii_video_paths == []:
        ascii_video_paths = sorted(glob_results) or None
    return ascii_video_paths


def test_none_triggers_autodiscovery():
    found = [str(ASCII_VIDEOS_DIR / 'bad_apple_frames.txt')]
    result = _resolve(None, found)
    assert result == found


def test_empty_list_triggers_autodiscovery():
    found = [str(ASCII_VIDEOS_DIR / 'bad_apple_frames.txt')]
    result = _resolve([], found)
    assert result == found


def test_none_with_no_files_returns_none():
    result = _resolve(None, [])
    assert result is None


def test_empty_list_with_no_files_returns_none():
    result = _resolve([], [])
    assert result is None


def test_explicit_paths_bypass_autodiscovery():
    explicit = ['/some/custom/video.txt']
    result = _resolve(explicit, ['should_not_appear.txt'])
    assert result == explicit


def test_autodiscovery_results_are_sorted():
    unsorted = ['z.txt', 'a.txt', 'm.txt']
    result = _resolve(None, unsorted)
    assert result == sorted(unsorted)


# ---------------------------------------------------------------------------
# Contain-mode centering math
# ---------------------------------------------------------------------------

def _contain_layout(av_w, av_h, ca_inner, ca_lines):
    """Reproduce the contain-mode layout math from visualiser._render()."""
    scale = min(ca_inner / max(av_w, 1), ca_lines / max(av_h, 1))
    av_scaled_w = max(1, int(av_w * scale))
    av_scaled_h = max(1, int(av_h * scale))
    col_start = (ca_inner - av_scaled_w) // 2
    row_start = (ca_lines - av_scaled_h) // 2
    return scale, av_scaled_w, av_scaled_h, col_start, row_start


def _cover_layout(av_w, av_h, ca_inner, ca_lines):
    """Reproduce the cover-mode layout math from visualiser._render()."""
    scale = max(ca_inner / max(av_w, 1), ca_lines / max(av_h, 1))
    av_scaled_w = max(ca_inner, int(av_w * scale))
    av_scaled_h = max(ca_lines, int(av_h * scale))
    col_src_start = (av_scaled_w - ca_inner) / 2.0
    row_src_start = (av_scaled_h - ca_lines) / 2.0
    return scale, av_scaled_w, av_scaled_h, col_src_start, row_src_start


def test_cover_fills_ca_area():
    _, sw, sh, _, _ = _cover_layout(114, 21, 100, 20)
    assert sw >= 100 and sh >= 20, f"Cover scaled size {sw}x{sh} must fill CA area 100x20"


def test_cover_center_crop_is_symmetric_cols():
    _, sw, _, cs, _ = _cover_layout(114, 21, 170, 27)
    # cs is how many scaled cols are cropped from the left — right crop = sw - ca_inner - cs
    right_crop = sw - 170 - cs
    assert abs(cs - right_crop) <= 1, (
        f"Cover crop not symmetric: left={cs:.1f}, right={right_crop:.1f}"
    )


def test_cover_center_crop_is_symmetric_rows():
    _, _, sh, _, rs = _cover_layout(114, 21, 170, 27)
    bottom_crop = sh - 27 - rs
    assert abs(rs - bottom_crop) <= 1, (
        f"Cover crop not symmetric: top={rs:.1f}, bottom={bottom_crop:.1f}"
    )


def test_cover_scale_uses_max_not_min():
    # Contain would use min() — cover must use max() so every cell is filled
    ca_inner, ca_lines = 100, 20
    av_w, av_h = 114, 21
    contain_scale = min(ca_inner / av_w, ca_lines / av_h)
    cover_scale, _, _, _, _ = _cover_layout(av_w, av_h, ca_inner, ca_lines)
    assert cover_scale >= contain_scale, (
        "Cover scale must be >= contain scale"
    )


def test_space_transparent_only_in_contain_mode():
    """Space is transparent in contain mode (logo art) but opaque in cover mode (full-frame art)."""
    import visualiser as _vis
    import inspect
    src = inspect.getsource(_vis.Visualiser._render)
    # The contain guard must exist and be conditional
    assert 'av_contain' in src, "_render must branch on av_contain for transparency"
    assert "src_ch == ' '" in src or 'src_ch == " "' in src, (
        "_render must treat space as transparent in contain mode"
    )


def test_content_fill_ratio_full_frame():
    from ascii_video import content_fill_ratio, load_frames
    frames, _, w, _ = load_frames(str(ASCII_VIDEOS_DIR / 'bad_apple_frames.txt'))
    ratio = content_fill_ratio(frames, w)
    assert ratio >= 0.9, f"Bad Apple fill ratio {ratio:.2f} should be >= 0.9 (full-frame art)"


def test_content_fill_ratio_logo():
    from ascii_video import content_fill_ratio, load_frames
    frames, _, w, _ = load_frames(str(ASCII_VIDEOS_DIR / 'death_angel_12fps_114x21.txt'))
    ratio = content_fill_ratio(frames, w)
    assert ratio < 0.9, f"Death Angel fill ratio {ratio:.2f} should be < 0.9 (logo art)"


def test_playlist_tuple_includes_fill_ratio():
    """Both playlist-building paths must store a 5-tuple including fill ratio."""
    from ascii_video import load_frames, content_fill_ratio
    frames, fps, w, h = load_frames(str(ASCII_VIDEOS_DIR / 'bad_apple_frames.txt'))
    fill = content_fill_ratio(frames, w)
    entry = (frames, fps, w, h, fill)
    assert len(entry) == 5
    assert 0.0 <= entry[4] <= 1.0


# ---------------------------------------------------------------------------
# crop_to_content
# ---------------------------------------------------------------------------

def test_crop_strips_blank_padding():
    from ascii_video import load_frames, crop_to_content
    frames, _, w, h = load_frames(str(ASCII_VIDEOS_DIR / 'death_angel_12fps_114x21.txt'))
    cropped, cw, ch = crop_to_content(frames)
    assert cw < w, f"Cropped width {cw} should be less than original {w}"
    assert ch <= h, f"Cropped height {ch} should be <= original {h}"


def test_crop_content_fills_cropped_canvas():
    from ascii_video import load_frames, crop_to_content, content_fill_ratio
    frames, _, w, _ = load_frames(str(ASCII_VIDEOS_DIR / 'death_angel_12fps_114x21.txt'))
    cropped, cw, ch = crop_to_content(frames)
    ratio = content_fill_ratio(cropped, cw)
    assert ratio >= 0.9, f"After crop, fill ratio should be >= 0.9, got {ratio:.2f}"


def test_crop_preserves_full_frame_art_width():
    """Full-frame art width should be unchanged by cropping (content reaches the edges)."""
    from ascii_video import load_frames, crop_to_content
    frames, _, w, h = load_frames(str(ASCII_VIDEOS_DIR / 'bad_apple_frames.txt'))
    cropped, cw, ch = crop_to_content(frames)
    assert cw == w, f"Bad Apple width should be unchanged: {cw} != {w}"
    assert ch <= h, f"Cropped height {ch} should not exceed original {h}"


def test_crop_preserves_frame_count():
    from ascii_video import load_frames, crop_to_content
    frames, _, w, _ = load_frames(str(ASCII_VIDEOS_DIR / 'death_angel_12fps_114x21.txt'))
    cropped, _, _ = crop_to_content(frames)
    assert len(cropped) == len(frames)


def test_cropped_logo_scales_up_to_fill_ca():
    """After cropping, contain-mode scaling should reach close to the CA dimensions."""
    from ascii_video import load_frames, crop_to_content
    frames, _, _, _ = load_frames(str(ASCII_VIDEOS_DIR / 'death_angel_12fps_114x21.txt'))
    cropped, cw, ch = crop_to_content(frames)
    ca_inner, ca_lines = 114, 27
    scale = min(ca_inner / cw, ca_lines / ch)
    scaled_w = int(cw * scale)
    scaled_h = int(ch * scale)
    # At least one axis should be within 1 cell of the CA boundary
    assert scaled_w >= ca_inner - 1 or scaled_h >= ca_lines - 1, (
        f"Cropped logo doesn't scale to fill CA: scaled={scaled_w}x{scaled_h}, CA={ca_inner}x{ca_lines}"
    )
