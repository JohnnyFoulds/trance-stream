# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Download Switch Angel's live-coding trance videos from YouTube.

Hardcodes the canonical set of video IDs so the research pipeline is
fully reproducible — same videos, same versions, regardless of when it
is run.

Usage::

    python tools/download_videos.py [--out DIR] [--ids ID [ID ...]]

Requirements::

    pip install yt-dlp
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Canonical video set — ordered by research priority.
# Each entry: (video_id, title, reason_for_inclusion)
VIDEOS: list[tuple[str, str, str]] = [
    (
        "3fpx7Scysw4",
        "Coding Trance IV",
        "Most recent trance live-code session — latest patterns",
    ),
    (
        "-pDO2RhcGhM",
        "Coding Trance Music From Scratch YET AGAIN",
        "Full from-scratch build — shows complete arrangement construction",
    ),
    (
        "iu5rnQkfO6M",
        "Coding Trance Music from Scratch (Again)",
        "Earlier from-scratch session — compare technique evolution",
    ),
    (
        "vn9VDbacUgQ",
        "Coding Trance (Official)",
        "Official track — final polished code visible",
    ),
    (
        "GWXCCBsOMSg",
        "Coding Trance Music (Full Narrated)",
        "Narrated — she explains her decisions in real time",
    ),
]


def download(video_id: str, title: str, out_dir: Path) -> bool:
    url = f"https://www.youtube.com/watch?v={video_id}"
    out_template = str(out_dir / f"{video_id}_%(title)s.%(ext)s")
    cmd = [
        "yt-dlp",
        "-f", "bestvideo[height<=720]+bestaudio/best[height<=720]",
        "--write-info-json",
        "--no-playlist",
        "-o", out_template,
        url,
    ]
    print(f"Downloading: {video_id} — {title}")
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out", default="research/videos",
        help="Output directory (default: research/videos)",
    )
    parser.add_argument(
        "--ids", nargs="*",
        help="Specific video IDs to download (default: all canonical videos)",
    )
    args = parser.parse_args()

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    target_ids = set(args.ids) if args.ids else None
    videos = [(vid, title, reason) for vid, title, reason in VIDEOS
              if target_ids is None or vid in target_ids]

    if not videos:
        print("No matching video IDs found.", file=sys.stderr)
        sys.exit(1)

    print(f"Downloading {len(videos)} video(s) to {out_dir}/\n")
    failed = []
    for vid, title, reason in videos:
        ok = download(vid, title, out_dir)
        if not ok:
            failed.append(vid)

    print(f"\n{len(videos) - len(failed)}/{len(videos)} downloaded successfully.")
    if failed:
        print(f"Failed: {failed}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
