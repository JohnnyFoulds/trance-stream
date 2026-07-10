"""Generate the classic spinning donut (torus) ASCII animation.

Generates frames programmatically — no network download required.
Based on the donut.c algorithm by Andy Sloane (a1k0n), which renders a rotating
torus using ASCII characters to represent surface luminance.

Output: ascii_videos/donut_25fps_60x28.txt
Expected: 90 frames, 60×28 chars, fill ratio < 0.9 (logo/contain mode — the
donut occupies the central portion of the frame with a dark surround)

Reference:
    Sloane, A. (2006). Donut math: how donut.c works.
    https://www.a1k0n.net/2011/07/20/donut-math.html

Usage:
    python tools/fetch_donut.py [--output ascii_videos/donut_25fps_60x28.txt]
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

DEFAULT_OUT = Path(__file__).parent.parent / 'ascii_videos' / 'donut_25fps_60x28.txt'

_FRAMES = 90        # one full rotation
_FPS = 25
_TARGET_WIDTH = 60
_TARGET_HEIGHT = 28

# Same gradient as convert_to_ascii.py: covers all four _av_color tiers
# BG=' ' FADE='.,:-' MID='+*' BRIGHT='%@#'
_GRADIENT = ' .,:-+*%@#'
_N = len(_GRADIENT)


def _render_frame(A: float, B: float, width: int, height: int) -> list[str]:
    """Render one frame of the spinning donut.

    A = rotation around the x-axis, B = rotation around the z-axis.
    The donut radius parameters (R1, R2) and projection distance (K2) are fixed;
    K1 is scaled to fill ~60% of the terminal width for good visual balance.
    """
    R1, R2 = 1.0, 2.0
    K2 = 5.0
    # K1 chosen so the torus fits neatly inside the frame
    K1 = width * K2 * 3.0 / (8.0 * (R1 + R2))

    output = [' '] * (width * height)
    zbuf = [-1e9] * (width * height)

    cosA, sinA = math.cos(A), math.sin(A)
    cosB, sinB = math.cos(B), math.sin(B)

    theta = 0.0
    while theta < 2 * math.pi:
        costheta, sintheta = math.cos(theta), math.sin(theta)
        phi = 0.0
        while phi < 2 * math.pi:
            cosphi, sinphi = math.cos(phi), math.sin(phi)

            # Torus circle point before rotation
            cx = R2 + R1 * costheta
            cy = R1 * sintheta

            # 3D coordinates after A (x-axis) then B (z-axis) rotation
            x = cx * (cosB * cosphi + sinA * sinB * sinphi) - cy * cosA * sinB
            y = cx * (sinB * cosphi - sinA * cosB * sinphi) + cy * cosA * cosB
            z = K2 + cosA * cx * sinphi + cy * sinA
            ooz = 1.0 / z

            xp = int(width / 2 + K1 * ooz * x)
            # Multiply y by 0.5 to compensate for 2:1 terminal cell aspect ratio
            yp = int(height / 2 - K1 * ooz * y * 0.5)

            # Surface luminance from dot-product with light at (0, 1, -1) normalised
            L = (cosphi * costheta * sinB
                 - cosA * costheta * sinphi
                 - sinA * sintheta
                 + cosB * (cosA * sintheta - costheta * sinA * sinphi))

            if 0 <= xp < width and 0 <= yp < height and ooz > zbuf[xp + yp * width]:
                zbuf[xp + yp * width] = ooz
                # Map luminance [-1..1] → gradient index [0..N-1]
                # L < 0 means the surface faces away from the light → dark
                idx = max(0, min(_N - 1, int(L * 5) + 4))
                output[xp + yp * width] = _GRADIENT[idx]

            phi += 0.02
        theta += 0.07

    rows = []
    for row_y in range(height):
        rows.append(''.join(output[row_y * width:(row_y + 1) * width]))
    return rows


def generate(out_path: Path) -> None:
    """Generate _FRAMES frames of the spinning donut and write to out_path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f'Generating {_FRAMES} donut frames at {_TARGET_WIDTH}×{_TARGET_HEIGHT} @ {_FPS}fps ...')

    frames = []
    for i in range(_FRAMES):
        # A (x-axis tilt) and B (z-axis spin) advance at different rates
        # for a visually interesting tumbling rotation
        A = i * 0.08
        B = i * 0.04
        frames.append(_render_frame(A, B, _TARGET_WIDTH, _TARGET_HEIGHT))
        if i % 10 == 0:
            print(f'  frame {i}/{_FRAMES}')

    # Write in one-frame-per-line format (same as binarize_ascii_video.py)
    lines = ['\\n'.join(row for row in frame) for frame in frames]
    out_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')

    # Sanity checks
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from ascii_video import load_frames, content_fill_ratio
    loaded_frames, _, fw, fh = load_frames(str(out_path))
    ratio = content_fill_ratio(loaded_frames, fw)

    print(f'Written: {out_path}')
    print(f'  {fw}x{fh} @ {_FPS}fps — {len(loaded_frames)} frames — fill ratio {ratio:.3f}')
    if len(loaded_frames) != _FRAMES:
        print(f'  WARNING: expected {_FRAMES} frames, got {len(loaded_frames)}')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '--output', default=str(DEFAULT_OUT),
        help=f'Output path (default: {DEFAULT_OUT})',
    )
    args = parser.parse_args()
    generate(Path(args.output))


if __name__ == '__main__':
    main()
