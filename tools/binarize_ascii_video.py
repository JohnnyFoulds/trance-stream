"""Pre-process an ASCII video frame file for use as a logo overlay.

Remaps all non-space characters to '#' (the BRIGHT tier in visualiser's
_av_color palette) so the overlay produces uniform bright color on every
content glyph over the CA background.  Space is preserved as-is (the
renderer treats it as transparent in contain/logo mode).

Usage:
    python tools/binarize_ascii_video.py <input.txt> <output.txt>
    python tools/binarize_ascii_video.py ascii_videos/death_angel_12fps_114x21.txt \
                                         ascii_videos/death_angel_12fps_114x21.txt
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from ascii_video import load_frames


def binarize(frames: list[list[str]]) -> list[list[str]]:
    """Remap every non-space char to '#', preserve spaces."""
    return [
        [''.join('#' if ch != ' ' else ' ' for ch in row) for row in frame]
        for frame in frames
    ]


def write_frames(frames: list[list[str]], fps: int, path: Path) -> None:
    """Write frames in the one-line-per-frame format (literal \\n row separator)."""
    lines = []
    for frame in frames:
        lines.append('\\n'.join(row for row in frame))
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('input',  help='Source frame file')
    parser.add_argument('output', help='Destination frame file (can be the same as input)')
    args = parser.parse_args()

    src = Path(args.input)
    dst = Path(args.output)

    frames, fps, w, h = load_frames(str(src))
    print(f"Loaded {len(frames)} frames  {w}x{h} @ {fps}fps  from {src}")

    before_chars = {ch for frame in frames for row in frame for ch in row if ch != ' '}
    binarized = binarize(frames)
    after_chars  = {ch for frame in binarized for row in frame for ch in row if ch != ' '}

    write_frames(binarized, fps, dst)
    print(f"Written to {dst}")
    print(f"Content chars before: {sorted(before_chars)}")
    print(f"Content chars after:  {sorted(after_chars)}")


if __name__ == '__main__':
    main()
