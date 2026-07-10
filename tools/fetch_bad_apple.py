"""One-off download helper for the Bad Apple ASCII frame file.

Downloads frames_30fps_60x32.txt from the backslashxx/bad-apple-ascii
GitHub release and writes it to ascii_videos/bad_apple_frames.txt.

Usage:
    python tools/fetch_bad_apple.py
    python tools/fetch_bad_apple.py --out /path/to/frames.txt
"""
import argparse
import io
import urllib.request
import zipfile
from pathlib import Path

RELEASE_URL = (
    "https://raw.githubusercontent.com/backslashxx/bad-apple-ascii/magisk-module/bad_apple.zip"
)
TARGET_FILE = "frames_30fps_60x32.txt"
DEFAULT_OUT = Path(__file__).parent.parent / "ascii_videos" / "bad_apple_frames.txt"


def fetch(out_path: Path) -> None:
    print(f"Downloading {RELEASE_URL} ...")
    with urllib.request.urlopen(RELEASE_URL) as resp:
        data = resp.read()
    print(f"  Downloaded {len(data):,} bytes")

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
        match = next((n for n in names if n.endswith(TARGET_FILE)), None)
        if match is None:
            raise FileNotFoundError(
                f"{TARGET_FILE!r} not found in archive. Contents: {names}"
            )
        content = zf.read(match)

    out_path.write_bytes(content)
    print(f"  Written {len(content):,} bytes → {out_path}")

    # Quick sanity check
    lines = content.decode("utf-8").splitlines()
    frame_count = sum(1 for l in lines if l.endswith("|") and l[:-1].isdigit())
    print(f"  Frame count: {frame_count}  (expected 6570)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help=f"Output path (default: {DEFAULT_OUT})")
    args = parser.parse_args()
    fetch(Path(args.out))
    print("Done.")


if __name__ == "__main__":
    main()
