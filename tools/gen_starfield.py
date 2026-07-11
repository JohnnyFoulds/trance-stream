"""Generate a warp-speed starfield ASCII animation.

Stars are placed pseudo-randomly, then accelerate outward from the centre each
frame.  As a star gets closer it brightens: dim-cyan far away, bold-white when
it flies past.  The void between stars is filled with the FADE-tier '.' character
so content_fill_ratio ≥ 0.99 (cover mode, same as Bad Apple).

Output: ascii_videos/starfield_25fps_60x28.txt
Expected: 120 frames, 60×28 chars, fill ratio ≥ 0.99

Usage:
    python tools/gen_starfield.py [--output ascii_videos/starfield_25fps_60x28.txt]
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

DEFAULT_OUT = Path(__file__).parent.parent / 'ascii_videos' / 'starfield_25fps_60x28.txt'

_FRAMES = 120
_FPS    = 25
_W      = 60
_H      = 28
_STARS  = 180   # number of stars in the field

# Gradient ordered dark→bright — covers all four _av_color tiers:
#   ' '  → BG (dim blue)     — unused; void is '.' not ' '
#   '.,' → FADE (dim cyan)   — distant stars + void fill
#   ':-' → FADE              — mid-distance
#   '+*' → MID (cyan)        — approaching
#   '%@#'→ BRIGHT (bold wht) — close / flying past
_GRADIENT = ' .,:-+*%@#'
_N        = len(_GRADIENT)

# Characters used to render the void — must have fill ratio contribution
_VOID_CHAR = '.'   # FADE tier, visible but recedes


def _make_stars(n: int, w: int, h: int, seed: int = 42) -> list[tuple[float, float, float]]:
    """Return n stars as (x, y, z) in normalised coords.

    x, y ∈ (-1, 1),  z ∈ (0.05, 1.0] — depth (z=0 is the camera, z=1 is far away).
    Uses a simple LCG so the result is deterministic.
    """
    stars = []
    rng = seed
    def rand():
        nonlocal rng
        rng = (rng * 1664525 + 1013904223) & 0xFFFFFFFF
        return rng / 0xFFFFFFFF

    for _ in range(n):
        x = rand() * 2.0 - 1.0
        y = rand() * 2.0 - 1.0
        z = rand() * 0.95 + 0.05
        stars.append((x, y, z))
    return stars


def _render_frame(
    stars: list[tuple[float, float, float]],
    frame_idx: int,
    w: int,
    h: int,
    speed: float = 0.018,
) -> list[str]:
    """Render one frame.

    Each star's z decreases each frame (it flies toward the camera).  When it
    reaches z ≤ 0 it wraps back to z = 1.0 at a fresh random (x, y).
    """
    t = frame_idx * speed

    # Build an empty canvas filled with the void character
    canvas = [[_VOID_CHAR] * w for _ in range(h)]

    cx, cy = w / 2.0, h / 2.0

    for sx, sy, sz in stars:
        # Advance star toward camera
        z = sz - t
        # Wrap — keep the star visually in place by using a stable offset
        while z <= 0.0:
            z += 1.0

        # Perspective projection — terminal cells are ~2:1 so scale y by 0.5
        scale = 1.0 / z
        px = int(cx + sx * scale * cx * 0.9)
        py = int(cy + sy * scale * cy * 0.9 * 0.5)

        if 0 <= px < w and 0 <= py < h:
            # Brightness: closer (z small) → brighter
            # z in (0, 1]: map to gradient index 1..N-1 (skip BG space)
            brightness = 1.0 - z          # 0 (far) → 1 (close)
            idx = max(1, min(_N - 1, int(brightness * (_N - 1)) + 1))
            # Use a small symbol that stays within tier boundaries
            char = _GRADIENT[idx]
            canvas[py][px] = char

    return [''.join(row) for row in canvas]


def generate(out_path: Path) -> None:
    """Generate _FRAMES frames of the starfield and write to out_path."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    stars = _make_stars(_STARS, _W, _H)

    print(f'Generating {_FRAMES} starfield frames at {_W}×{_H} @ {_FPS}fps ...')
    frames = [_render_frame(stars, i, _W, _H) for i in range(_FRAMES)]

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
