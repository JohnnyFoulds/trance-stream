# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""One-off download helper for the Star Wars asciimation frame file.

Downloads the canonical Simon Jansen asciimation from bhwang/ascii-star-wars,
converts the 14-lines-per-frame format to the one-line-per-frame format used
by ascii_video.py, and writes it to ascii_videos/starwars_15fps_frames.txt.

Usage:
    python tools/fetch_starwars.py
    python tools/fetch_starwars.py --out /path/to/frames.txt
"""
import argparse
import urllib.request
from pathlib import Path

SOURCE_URL = (
    "https://raw.githubusercontent.com/bhwang/ascii-star-wars/main/src/asciimation.txt"
)
DEFAULT_OUT = Path(__file__).parent.parent / "ascii_videos" / "starwars_15fps_frames.txt"

FRAME_LINES = 14   # 1 timing line + 13 content rows per frame
CONTENT_ROWS = 13


def fetch(out_path: Path) -> None:
    print(f"Downloading {SOURCE_URL} ...")
    with urllib.request.urlopen(SOURCE_URL) as resp:
        data = resp.read()
    print(f"  Downloaded {len(data):,} bytes")

    lines = data.decode("utf-8", errors="replace").splitlines()
    print(f"  Raw lines: {len(lines)}")

    # Parse 14-line blocks, expand RLE: each block has a timing value on line 1
    # (display duration in units of 1/15 s). Repeat the frame that many times
    # so wall-clock frame indexing (frame_idx = round(elapsed * fps)) is correct.
    output_lines: list[str] = []
    i = 0
    while i + FRAME_LINES <= len(lines):
        timing_str = lines[i].strip()
        duration = int(timing_str) if timing_str.isdigit() else 1
        content = lines[i + 1 : i + FRAME_LINES]   # 13 content rows
        frame_line = "\\n".join(content)
        for _ in range(duration):
            output_lines.append(frame_line)
        i += FRAME_LINES

    out_path.write_text("\n".join(output_lines) + "\n", encoding="utf-8")
    print(f"  Written {out_path.stat().st_size:,} bytes → {out_path}")
    print(f"  Frame count : {len(output_lines)}  (expected ~15973)")

    # Infer dimensions from first non-blank frame
    width = 0
    height = 0
    for line in output_lines:
        rows = line.split("\\n")
        w = max((len(r) for r in rows), default=0)
        if w > 0:
            width = w
            height = len(rows)
            break
    print(f"  Dimensions  : {width}×{height}  (expected 67×13)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help=f"Output path (default: {DEFAULT_OUT})")
    args = parser.parse_args()
    fetch(Path(args.out))
    print("Done.")


if __name__ == "__main__":
    main()
