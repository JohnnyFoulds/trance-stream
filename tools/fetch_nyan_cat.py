"""Download the Nyan Cat animated GIF and convert it to an ASCII frame file.

Source: nyan.cat/cats/original.gif (Torres, C., 2011 — original creator: prguitarman.com)
Output: ascii_videos/nyan_cat_14fps_60x19.txt
Expected: 12 frames (7 unique), 60×19 chars, fill ratio >= 0.9 (full-canvas cover mode)

Usage:
    python tools/fetch_nyan_cat.py [--output ascii_videos/nyan_cat_14fps_60x19.txt]
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import urllib.request
from pathlib import Path

SOURCE_URL = 'https://www.nyan.cat/cats/original.gif'
DEFAULT_OUT = Path(__file__).parent.parent / 'ascii_videos' / 'nyan_cat_14fps_60x19.txt'

_EXPECTED_FRAMES = 12
_TARGET_WIDTH = 60


def fetch(out_path: Path) -> None:
    """Download the Nyan Cat GIF and convert to ASCII frames at out_path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f'Downloading Nyan Cat GIF from {SOURCE_URL} ...')
    req = urllib.request.Request(SOURCE_URL, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req) as resp:
        gif_bytes = resp.read()
    print(f'Downloaded {len(gif_bytes):,} bytes')

    # Write to a temp file so the PIL-based converter can open it by path
    with tempfile.NamedTemporaryFile(suffix='.gif', delete=False) as tmp:
        tmp.write(gif_bytes)
        tmp_path = Path(tmp.name)

    try:
        # Deferred import — PIL only needed here, not at module import time
        sys.path.insert(0, str(Path(__file__).parent))
        from convert_to_ascii import convert_gif

        auto_out, fps, w, h = convert_gif(str(tmp_path), str(out_path.parent), _TARGET_WIDTH)
        auto_out_path = Path(auto_out)

        # Rename to canonical output path if the auto-generated name differs
        if auto_out_path != out_path:
            auto_out_path.rename(out_path)
            print(f'Renamed {auto_out_path.name} → {out_path.name}')

    finally:
        tmp_path.unlink(missing_ok=True)

    # Sanity checks
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from ascii_video import load_frames, content_fill_ratio
    frames, _, fw, fh = load_frames(str(out_path))
    ratio = content_fill_ratio(frames, fw)

    print(f'Written: {out_path}')
    print(f'  {fw}x{fh} @ {fps}fps — {len(frames)} frames — fill ratio {ratio:.3f}')

    if len(frames) != _EXPECTED_FRAMES:
        print(f'  WARNING: expected {_EXPECTED_FRAMES} frames, got {len(frames)}')
    if ratio < 0.9:
        print(f'  WARNING: fill ratio {ratio:.3f} < 0.9 — may not render in cover mode')
    else:
        print('  OK: fill ratio >= 0.9 (cover mode)')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '--output', default=str(DEFAULT_OUT),
        help=f'Output path (default: {DEFAULT_OUT})',
    )
    args = parser.parse_args()
    fetch(Path(args.output))


if __name__ == '__main__':
    main()
