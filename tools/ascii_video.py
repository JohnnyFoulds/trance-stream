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

    height = len(frames[0])
    width = max((len(row) for row in frames[0]), default=60)

    for frame in frames:
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
        rows = [r for r in rows if r]  # drop empty first/last
        if rows:
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
