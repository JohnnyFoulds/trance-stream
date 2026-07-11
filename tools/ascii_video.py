"""Generic ASCII video frame file loader.

Supports two formats:
1. One-frame-per-line with literal \n row separators (backslashxx/bad-apple-ascii format):
   Each real newline ends a frame; rows within the frame are separated by the
   two-character sequence backslash + n.

2. {N}| delimiter format:
   A line matching /^[0-9]+[|]$/ starts a new frame, followed by HEIGHT lines.

FPS is parsed from the filename pattern *_{N}fps[_.] and defaults to 30.
WIDTH and HEIGHT are inferred from the first frame.
"""
from __future__ import annotations

import re
from pathlib import Path


def content_fill_ratio(frames: list[list[str]], width: int) -> float:
    """Return the fraction of canvas width actually used by non-space content.

    Samples up to 20 frames.  Used to distinguish full-frame art (ratio ≈ 1.0,
    e.g. Bad Apple) from logo-on-canvas art (ratio < 1.0, e.g. Death Angel).
    """
    if not frames or width == 0:
        return 1.0
    step = max(1, len(frames) // 20)
    max_col = 0
    for frame in frames[::step]:
        for row in frame:
            stripped = row.rstrip()
            if stripped.strip():
                max_col = max(max_col, len(stripped))
    return min(1.0, max_col / width)


def crop_to_content(frames: list[list[str]]) -> tuple[list[list[str]], int, int]:
    """Crop all frames to the tightest bounding box that contains non-space content.

    Returns (cropped_frames, new_width, new_height).  Used to strip blank padding
    from logo-style art so contain-mode scaling actually fills the display area.
    """
    if not frames:
        return frames, 0, 0

    min_col, max_col, min_row, max_row = 10**9, 0, 10**9, 0
    for frame in frames:
        for ri, row in enumerate(frame):
            stripped_r = row.rstrip()
            if stripped_r.strip():
                max_col = max(max_col, len(stripped_r))
                min_col = min(min_col, len(row) - len(row.lstrip()))
                max_row = max(max_row, ri)
                min_row = min(min_row, ri)

    if max_col == 0:
        return frames, len(frames[0][0]) if frames and frames[0] else 0, len(frames[0]) if frames else 0

    new_w = max_col - min_col
    new_h = max_row - min_row + 1
    cropped = []
    for frame in frames:
        rows = []
        for ri in range(min_row, max_row + 1):
            row = frame[ri] if ri < len(frame) else ''
            row = row[min_col:max_col]
            d = new_w - len(row)
            if d > 0:
                row = row + ' ' * d
            rows.append(row)
        cropped.append(rows)
    return cropped, new_w, new_h


def load_frames(path: str) -> tuple[list[list[str]], int, int, int]:
    """Load a frame file and return (frames, fps, width, height).

    frames: list of frames, each a list of HEIGHT strings of exactly WIDTH chars.
    """
    name = Path(path).name
    m = re.search(r'_(\d+)fps[_.]', name)
    fps = int(m.group(1)) if m else 30

    raw = Path(path).read_bytes()

    # Detect format: if the file has very few real newlines relative to its size,
    # it's the one-frame-per-line format with literal \n row separators.
    real_nl = raw.count(b'\n')
    literal_nl = raw.count(b'\\n')

    if literal_nl > real_nl * 10:
        frames = _load_oneline_format(raw)
    else:
        frames = _load_delimiter_format(raw)

    if not frames:
        return [], fps, 60, 32

    # Use the most common row count as the canonical height (handles frames
    # with all-blank rows that look shorter if stripped).
    from collections import Counter
    height_counts = Counter(len(f) for f in frames)
    height = height_counts.most_common(1)[0][0]

    # Width = widest row across any frame
    width = max((len(row) for frame in frames for row in frame), default=60)
    if width == 0:
        width = 60

    for frame in frames:
        # Pad short frames to canonical height with blank rows
        while len(frame) < height:
            frame.append('')
        # Trim frames taller than canonical height
        del frame[height:]
        for i in range(len(frame)):
            row = frame[i]
            d = width - len(row)
            if d > 0:
                frame[i] = row + ' ' * d
            elif d < 0:
                frame[i] = row[:width]

    return frames, fps, width, height


def _load_oneline_format(raw: bytes) -> list[list[str]]:
    """One real line per frame; rows separated by literal backslash-n."""
    frames = []
    for line in raw.split(b'\n'):
        line = line.decode('utf-8', errors='replace')
        if not line:
            continue
        rows = line.split('\\n')
        # Keep all rows (including interior blanks) — only skip if the entire
        # line was empty (already guarded above). Append even if all rows are
        # blank so every encoded frame is represented in the playlist.
        frames.append(rows)
    return frames


def _load_delimiter_format(raw: bytes) -> list[list[str]]:
    """Frames delimited by lines matching /^[0-9]+[|]$/."""
    frames = []
    current: list[str] = []
    for line in raw.decode('utf-8', errors='replace').splitlines():
        if re.match(r'^\d+\|$', line):
            if current:
                frames.append(current)
            current = []
        else:
            current.append(line)
    if current:
        frames.append(current)
    return frames
