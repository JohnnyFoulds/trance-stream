# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Extract Strudel REPL code snapshots from Switch Angel's YouTube videos.

Pipeline:
  1. Decode video to frames at 2 fps (enough to catch any REPL update)
  2. Detect frames where the Strudel REPL is visible (dark background, bright
     code text in top ~60% of frame)
  3. Among REPL frames, detect *changes* by comparing successive frames via
     structural similarity or pixel diff
  4. OCR each changed frame with Tesseract to extract the code text
  5. Write a timestamped JSONL log per video: one record per code change

Output per video <id>:
  research/extracted/<id>/frames/   — changed REPL frame PNGs
  research/extracted/<id>/code.jsonl — {timestamp_s, frame_path, code_text}
  research/extracted/<id>/summary.md — human-readable code evolution

Usage::

    python tools/extract_strudel_code.py <video_file> [--fps 2] [--out DIR]

Requirements::

    pip install opencv-python pytesseract Pillow numpy
    brew install tesseract  (macOS)
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
from pathlib import Path

try:
    import cv2
except ImportError:
    sys.exit("opencv-python required: pip install opencv-python")

try:
    import numpy as np
except ImportError:
    sys.exit("numpy required: pip install numpy")

try:
    import pytesseract
    from PIL import Image
except ImportError:
    sys.exit("pytesseract and Pillow required: pip install pytesseract Pillow")


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# How dark must the background be to count as a REPL frame?
# Strudel REPL is near-black (#1a1a2e or similar). Mean pixel brightness of
# the top 60% of frame should be low.
REPL_BRIGHTNESS_THRESHOLD = 80   # 0-255

# Minimum fraction of the frame that must be "dark" for REPL detection
REPL_DARK_FRACTION = 0.55

# Frame difference threshold to count as a "code change"
# (mean absolute pixel diff, 0-255 scale)
CHANGE_THRESHOLD = 8.0

# Tesseract config for code: PSM 6 = assume uniform block of text
TESS_CONFIG = "--psm 6 --oem 3 -c preserve_interword_spaces=1"

# Region of interest: Strudel code lives in the top-left ~80% of the frame.
# Crop to this region before OCR to reduce noise from visualiser at bottom.
ROI_TOP = 0.0
ROI_BOTTOM = 0.80
ROI_LEFT = 0.0
ROI_RIGHT = 1.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def is_repl_frame(frame: np.ndarray) -> bool:
    """Return True if this frame looks like the Strudel REPL."""
    h, w = frame.shape[:2]
    top_region = frame[:int(h * 0.6), :]
    gray = cv2.cvtColor(top_region, cv2.COLOR_BGR2GRAY)
    mean_brightness = float(gray.mean())
    dark_fraction = float((gray < REPL_BRIGHTNESS_THRESHOLD).mean())
    return mean_brightness < REPL_BRIGHTNESS_THRESHOLD and dark_fraction > REPL_DARK_FRACTION


def frame_diff(a: np.ndarray, b: np.ndarray) -> float:
    """Mean absolute pixel difference between two frames (grayscale)."""
    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY).astype(np.float32)
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY).astype(np.float32)
    return float(np.abs(ga - gb).mean())


def ocr_frame(frame: np.ndarray) -> str:
    """Run Tesseract OCR on the code region of a frame."""
    h, w = frame.shape[:2]
    y1 = int(h * ROI_TOP)
    y2 = int(h * ROI_BOTTOM)
    x1 = int(w * ROI_LEFT)
    x2 = int(w * ROI_RIGHT)
    roi = frame[y1:y2, x1:x2]

    # Upscale for better OCR accuracy (Tesseract works best at ~300 dpi)
    scale = 2
    roi_up = cv2.resize(roi, (roi.shape[1] * scale, roi.shape[0] * scale),
                        interpolation=cv2.INTER_CUBIC)

    # Invert: dark background → white, bright text → black (Tesseract prefers this)
    gray = cv2.cvtColor(roi_up, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    pil_img = Image.fromarray(thresh)
    text = pytesseract.image_to_string(pil_img, config=TESS_CONFIG)
    return text.strip()


def extract_frames(video_path: str, fps: float, out_dir: Path) -> list[tuple[float, np.ndarray]]:
    """Extract frames at `fps` from video_path using ffmpeg, return (timestamp, frame) pairs."""
    out_dir.mkdir(parents=True, exist_ok=True)
    pattern = str(out_dir / "frame_%06d.png")

    cmd = [
        "ffmpeg", "-y", "-i", video_path,
        "-vf", f"fps={fps}",
        "-q:v", "2",
        pattern,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ffmpeg error: {result.stderr[-500:]}", file=sys.stderr)
        return []

    frames = []
    frame_files = sorted(out_dir.glob("frame_*.png"))
    for i, fp in enumerate(frame_files):
        timestamp_s = i / fps
        img = cv2.imread(str(fp))
        if img is not None:
            frames.append((timestamp_s, img, str(fp)))
    return frames


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_video(video_path: str, fps: float, out_base: Path) -> None:
    video_id = Path(video_path).stem[:11]
    out_dir = out_base / video_id
    frames_dir = out_dir / "frames"
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n=== Processing: {video_path} ===")
    print(f"Output: {out_dir}")

    # 1. Extract frames
    print(f"Extracting frames at {fps} fps...")
    raw_dir = out_dir / "raw_frames"
    all_frames = extract_frames(video_path, fps, raw_dir)
    print(f"  {len(all_frames)} frames extracted")

    # 2. Filter to REPL frames
    repl_frames = [(ts, img, fp) for ts, img, fp in all_frames if is_repl_frame(img)]
    print(f"  {len(repl_frames)} REPL frames detected ({100*len(repl_frames)//max(len(all_frames),1)}%)")

    if not repl_frames:
        print("  WARNING: No REPL frames detected — check REPL_BRIGHTNESS_THRESHOLD")
        return

    # 3. Detect code changes
    frames_dir.mkdir(parents=True, exist_ok=True)
    records = []
    prev_img = None
    change_count = 0

    for ts, img, raw_fp in repl_frames:
        if prev_img is None or frame_diff(prev_img, img) > CHANGE_THRESHOLD:
            change_count += 1
            fname = f"change_{change_count:04d}_t{int(ts):05d}s.png"
            dst = frames_dir / fname
            cv2.imwrite(str(dst), img)

            # OCR
            print(f"  OCR frame at t={ts:.1f}s ...", end=" ", flush=True)
            code_text = ocr_frame(img)
            print(f"({len(code_text)} chars)")

            records.append({
                "timestamp_s": round(ts, 2),
                "frame_path": str(dst.relative_to(out_base.parent)),
                "code_text": code_text,
            })
            prev_img = img

    print(f"  {change_count} code changes detected")

    # 4. Write JSONL
    jsonl_path = out_dir / "code.jsonl"
    with open(jsonl_path, "w") as f:
        for rec in records:
            f.write(json.dumps(rec) + "\n")
    print(f"  Code log: {jsonl_path}")

    # 5. Write summary markdown
    summary_path = out_dir / "summary.md"
    with open(summary_path, "w") as f:
        f.write(f"# Code evolution: {Path(video_path).name}\n\n")
        f.write(f"Video: `{video_path}`  \n")
        f.write(f"Extracted: {change_count} code snapshots\n\n")
        for rec in records:
            mins = int(rec['timestamp_s']) // 60
            secs = int(rec['timestamp_s']) % 60
            f.write(f"## t={mins}:{secs:02d}  ({rec['timestamp_s']}s)\n\n")
            f.write("```javascript\n")
            f.write(rec['code_text'])
            f.write("\n```\n\n")
    print(f"  Summary: {summary_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("video", nargs="+", help="Video file(s) to process")
    parser.add_argument("--fps", type=float, default=2.0,
                        help="Frames per second to extract (default: 2)")
    parser.add_argument("--out", type=str,
                        default="research/extracted",
                        help="Output base directory (default: research/extracted)")
    args = parser.parse_args()

    out_base = Path(args.out)
    out_base.mkdir(parents=True, exist_ok=True)

    for video_path in args.video:
        if not os.path.exists(video_path):
            print(f"File not found: {video_path}", file=sys.stderr)
            continue
        process_video(video_path, args.fps, out_base)

    print("\nDone.")


if __name__ == "__main__":
    main()
