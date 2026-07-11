"""Generate a demoscene-style plasma ASCII animation.

Classic plasma effect: three overlapping sine waves (two spatial, one
temporal) produce smooth interference patterns that ripple and pulse.
Every cell is covered on every frame so fill ratio = 1.000 (cover mode).

The brightness of each cell is derived from the sum of three sine functions:
    v = sin(x/4 + t)
      + sin(y/3 + t*1.3)
      + sin((x + y)/6 + t*0.7)

v ∈ (-3, 3) is normalised to [0, N-1] for the GRADIENT lookup.  Because the
sum sweeps the full range, all four _av_color tiers appear in every frame.

Output: ascii_videos/plasma_20fps_60x28.txt
Expected: 80 frames, 60×28 chars, fill ratio 1.000

Usage:
    python tools/gen_plasma.py [--output ascii_videos/plasma_20fps_60x28.txt]
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

DEFAULT_OUT = Path(__file__).parent.parent / 'ascii_videos' / 'plasma_20fps_60x28.txt'

_FRAMES = 80
_FPS    = 20
_W      = 60
_H      = 28

# Full 10-char gradient — all four _av_color tiers represented
_GRADIENT = ' .,:-+*%@#'
_N        = len(_GRADIENT)


def _render_frame(frame_idx: int, w: int, h: int) -> list[str]:
    """Render one plasma frame."""
    t = frame_idx * 0.18   # time step — controls animation speed

    rows = []
    for y in range(h):
        row = []
        yf = y * 2.0       # stretch vertically to compensate 2:1 cell aspect ratio
        for x in range(w):
            v = (math.sin(x / 4.0 + t)
                 + math.sin(yf / 6.0 + t * 1.3)
                 + math.sin((x + yf) / 8.0 + t * 0.7))
            # v ∈ (-3, 3) → normalise to [0, 1] → gradient index
            normalised = (v + 3.0) / 6.0          # 0..1
            idx = min(_N - 1, int(normalised * _N))
            row.append(_GRADIENT[idx])
        rows.append(''.join(row))
    return rows


def generate(out_path: Path) -> None:
    """Generate _FRAMES plasma frames and write to out_path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f'Generating {_FRAMES} plasma frames at {_W}×{_H} @ {_FPS}fps ...')
    frames = [_render_frame(i, _W, _H) for i in range(_FRAMES)]

    lines = ['\\n'.join(row for row in frame) for frame in frames]
    out_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    sys.path.insert(0, str(Path(__file__).parent.parent))
    from ascii_video import load_frames, content_fill_ratio
    loaded, _, fw, fh = load_frames(str(out_path))
    ratio = content_fill_ratio(loaded, fw)

    print(f'Written: {out_path}')
    print(f'  {fw}x{fh} @ {_FPS}fps — {len(loaded)} frames — fill ratio {ratio:.3f}')
    if ratio < 0.9:
        print(f'  WARNING: fill ratio {ratio:.3f} < 0.9')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', default=str(DEFAULT_OUT))
    args = parser.parse_args()
    generate(Path(args.output))


if __name__ == '__main__':
    main()
