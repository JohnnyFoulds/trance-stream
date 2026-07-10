# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""TDD tests for tools/convert_to_ascii.py.

All tests use synthetic in-memory images/GIFs — no network access required.
Tests are skipped when Pillow is not installed (only available via
requirements-research.txt, not the default requirements-dev.txt).
"""

from __future__ import annotations

import io
import pathlib
import sys

import pytest

PIL = pytest.importorskip('PIL', reason='Pillow required (pip install -r tools/requirements-research.txt)')

from PIL import Image, ImageSequence  # noqa: E402 — after importorskip guard

REPO_ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / 'tools'))

from convert_to_ascii import GRADIENT, convert_gif  # noqa: E402
from ascii_video import load_frames, content_fill_ratio  # noqa: E402


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_gif(frames_pixels: list, size: tuple[int, int], duration: int, path: pathlib.Path) -> None:
    """Write a multi-frame GIF from a list of grayscale pixel arrays."""
    imgs = []
    for pixels in frames_pixels:
        img = Image.new('L', size)
        img.putdata(pixels)
        imgs.append(img.convert('P'))
    imgs[0].save(
        str(path),
        save_all=True,
        append_images=imgs[1:],
        loop=0,
        duration=duration,
    )


def _solid_gif(size: tuple[int, int], lum: int, duration: int, path: pathlib.Path) -> None:
    """Single-frame GIF filled with a uniform luminance value."""
    pixels = [lum] * (size[0] * size[1])
    _make_gif([pixels], size, duration, path)


# ---------------------------------------------------------------------------
# test_single_frame_black_white
# ---------------------------------------------------------------------------

def test_single_frame_black_white(tmp_path):
    """Black corners → BG-tier space; white center region → BRIGHT-tier char."""
    w, h = 120, 60
    pixels = []
    cx, cy = w // 2, h // 2
    hw, hh = 30, 15  # half-size of white rectangle
    for y in range(h):
        for x in range(w):
            if cx - hw <= x < cx + hw and cy - hh <= y < cy + hh:
                pixels.append(255)
            else:
                pixels.append(0)
    gif_path = tmp_path / 'bw.gif'
    _make_gif([pixels], (w, h), 100, gif_path)

    out_path, fps, out_w, out_h = convert_gif(str(gif_path), str(tmp_path), target_width=60)

    frames, _, fw, fh = load_frames(out_path)
    assert len(frames) == 1

    frame = frames[0]
    # top-left corner is pure black → should be space (BG tier)
    assert frame[0][0] == ' ', f"Top-left should be space, got {frame[0][0]!r}"

    # center should be from BRIGHT tier
    BRIGHT = set('#@%MW&$X08B')
    center_char = frame[fh // 2][fw // 2]
    assert center_char in BRIGHT, (
        f"Center char should be BRIGHT tier, got {center_char!r}"
    )


# ---------------------------------------------------------------------------
# test_multi_frame_count
# ---------------------------------------------------------------------------

def test_multi_frame_count(tmp_path):
    """A 2-frame GIF produces exactly 2 frames in the output."""
    size = (80, 40)
    frame1 = [0] * (size[0] * size[1])
    frame2 = [255] * (size[0] * size[1])
    gif_path = tmp_path / 'two_frames.gif'
    _make_gif([frame1, frame2], size, 100, gif_path)

    out_path, fps, out_w, out_h = convert_gif(str(gif_path), str(tmp_path), target_width=60)

    frames, _, _, _ = load_frames(out_path)
    assert len(frames) == 2, f"Expected 2 frames, got {len(frames)}"


# ---------------------------------------------------------------------------
# test_fill_ratio_full_white
# ---------------------------------------------------------------------------

def test_fill_ratio_full_white(tmp_path):
    """An all-white frame should produce content_fill_ratio >= 0.9."""
    gif_path = tmp_path / 'white.gif'
    _solid_gif((120, 60), 255, 100, gif_path)

    out_path, _, out_w, _ = convert_gif(str(gif_path), str(tmp_path), target_width=60)

    frames, _, fw, _ = load_frames(out_path)
    ratio = content_fill_ratio(frames, fw)
    assert ratio >= 0.9, f"Full-white frame fill ratio should be >= 0.9, got {ratio:.3f}"


# ---------------------------------------------------------------------------
# test_output_format_oneline
# ---------------------------------------------------------------------------

def test_output_format_oneline(tmp_path):
    """Output file uses one-frame-per-line format with literal \\n row separators.

    Verifies:
    - load_frames round-trip returns 3 frames with w=60
    - raw bytes have literal \\n count > real \\n count * 10
    """
    size = (80, 40)
    n = size[0] * size[1]
    gif_path = tmp_path / 'three_frames.gif'
    # Use distinct luminance values so PIL GIF encoder doesn't merge identical frames
    _make_gif([[0] * n, [128] * n, [255] * n], size, 100, gif_path)

    out_path, _, out_w, out_h = convert_gif(str(gif_path), str(tmp_path), target_width=60)

    frames, _, fw, fh = load_frames(out_path)
    assert len(frames) == 3, f"Expected 3 frames, got {len(frames)}"
    assert fw == 60, f"Expected width 60, got {fw}"
    assert fh > 0

    # Verify one-line-per-frame format: literal \\n must vastly outnumber real \n
    raw = pathlib.Path(out_path).read_bytes()
    real_nl = raw.count(b'\n')
    literal_nl = raw.count(b'\\n')
    assert literal_nl > real_nl * 10, (
        f"Expected literal \\n ({literal_nl}) > real \\n ({real_nl}) * 10 — "
        "file does not appear to be in one-frame-per-line format"
    )


# ---------------------------------------------------------------------------
# test_fps_in_filename
# ---------------------------------------------------------------------------

def test_fps_in_filename(tmp_path):
    """GIF with 70ms/frame duration should produce a filename containing '14fps'."""
    gif_path = tmp_path / 'fps_test.gif'
    _solid_gif((80, 40), 128, 70, gif_path)  # 70ms → fps = round(1000/70) = 14

    out_path, fps, _, _ = convert_gif(str(gif_path), str(tmp_path), target_width=60)

    filename = pathlib.Path(out_path).name
    assert '14fps' in filename, (
        f"Expected '14fps' in filename for 70ms/frame GIF, got: {filename!r}"
    )
    assert fps == 14, f"Expected fps=14, got {fps}"


# ---------------------------------------------------------------------------
# test_all_four_tiers_present
# ---------------------------------------------------------------------------

def test_all_four_tiers_present(tmp_path):
    """A 4-band grayscale image (black → white) produces chars in all four tiers."""
    AV_BG     = {' '}
    AV_FADE   = set('.,:;`\'"_-')
    AV_MID    = set('!|/\\()[]{}+~?<>^*')
    AV_BRIGHT = set('#@%MW&$X08B')

    # 240 wide × 60 tall, four 60-wide vertical bands at lum 0 / 85 / 170 / 255
    w, h = 240, 60
    pixels = []
    for y in range(h):
        for x in range(w):
            band = x // 60
            pixels.append([0, 85, 170, 255][band])

    gif_path = tmp_path / 'gradient.gif'
    _make_gif([pixels], (w, h), 100, gif_path)

    out_path, _, _, _ = convert_gif(str(gif_path), str(tmp_path), target_width=60)

    frames, _, fw, fh = load_frames(out_path)
    all_chars = {c for row in frames[0] for c in row}

    assert all_chars & AV_BG,     f"No BG-tier chars found. chars={sorted(all_chars)}"
    assert all_chars & AV_FADE,   f"No FADE-tier chars found. chars={sorted(all_chars)}"
    assert all_chars & AV_MID,    f"No MID-tier chars found. chars={sorted(all_chars)}"
    assert all_chars & AV_BRIGHT, f"No BRIGHT-tier chars found. chars={sorted(all_chars)}"
