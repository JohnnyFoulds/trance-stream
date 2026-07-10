"""Convert GIF/video files to ASCII frame text files for the trance-stream visualiser.

Output format: one-frame-per-line with literal \\n row separators (same as
bad_apple_frames.txt). The output filename encodes fps and dimensions:
    <stem>_<fps>fps_<width>x<height>.txt

Supported inputs:
    GIF, WEBP, PNG (animated) — via Pillow (PIL)
    MP4, AVI, MOV, MKV        — via opencv-python (cv2), imported lazily

Usage:
    python tools/convert_to_ascii.py <input> [--output-dir ascii_videos/] [--width 60]

The luminance-to-character gradient:
    GRADIENT = ' .,:-+*%@#'
Maps lum=0 (black) → space (BG tier, dim-blue in visualiser)
           lum=255 (white) → '#' (BRIGHT tier, bold-white in visualiser)
All four visualiser tiers are represented; '=' is intentionally excluded because
it falls through to BG/dim-blue, making it visually identical to space.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Pillow is in requirements-research.txt, not requirements-dev.txt.
# Imported at module level — callers must have it installed.
from PIL import Image, ImageSequence
import numpy as np

GRADIENT = ' .,:-+*%@#'
_N = len(GRADIENT)  # 10


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _frame_to_rows(pil_frame: Image.Image, target_width: int, target_height: int) -> list[str]:
    """Convert a single PIL image to a list of ASCII rows.

    Steps:
    1. Convert to RGBA (handles palette+transparency correctly), then to L (grayscale)
    2. Resize to target dimensions with LANCZOS filter
    3. Map each pixel luminance to a GRADIENT character via integer arithmetic
    """
    gray = pil_frame.convert('RGBA').convert('L')
    gray = gray.resize((target_width, target_height), Image.LANCZOS)
    arr = np.asarray(gray)  # shape (H, W), dtype uint8
    # Integer formula: avoids float rounding; clamp ensures idx in [0, N-1]
    indices = np.clip(arr.astype(np.int32) * _N // 256, 0, _N - 1)
    return [''.join(GRADIENT[i] for i in row) for row in indices.tolist()]


def _compute_target_height(pixel_width: int, pixel_height: int, target_width: int) -> int:
    """Compute target ASCII height preserving aspect ratio.

    The 0.5 factor accounts for terminal cells being approximately 2× taller
    than they are wide. Without it, the image would appear stretched vertically.

    Minimum height of 12 ensures the one-frame-per-line format detection in
    load_frames() fires correctly (requires literal_nl / real_nl > 10).
    """
    pixel_ar = pixel_width / max(pixel_height, 1)
    return max(12, round(target_width / pixel_ar * 0.5))


def _compute_fps(durations_ms: list[int]) -> int:
    """Convert per-frame durations (in ms) to a single integer fps value."""
    if not durations_ms:
        return 30
    avg_ms = sum(durations_ms) / len(durations_ms)
    return max(1, round(1000 / avg_ms))


def _gif_to_ascii_frames(
    img: Image.Image,
    target_width: int,
) -> tuple[list[list[str]], int, int, int]:
    """Extract all frames from an opened PIL Image and convert to ASCII.

    Uses img.copy() + seek loop rather than ImageSequence.Iterator.
    Iterator materializes each frame lazily and with disposal mode 2 (restore
    to background) can return the same composited canvas for every frame.
    img.copy() forces PIL to apply the current seek position's delta and return
    a fully composited independent frame.

    Returns (frames, fps, width, height).
    """
    pil_frames = []
    durations = []
    try:
        while True:
            pil_frames.append(img.copy())
            durations.append(int(img.info.get('duration', 100) or 100))
            img.seek(img.tell() + 1)
    except EOFError:
        pass

    fps = _compute_fps(durations)

    pw, ph = img.size
    target_height = _compute_target_height(pw, ph, target_width)

    frames = [_frame_to_rows(f, target_width, target_height) for f in pil_frames]
    return frames, fps, target_width, target_height


def _cv2_to_ascii_frames(
    path: str,
    target_width: int,
) -> tuple[list[list[str]], int, int, int]:
    """Convert a video file (MP4/AVI/etc.) to ASCII using opencv-python.

    Imported lazily — only needed for video files, not GIFs.
    """
    try:
        import cv2
    except ImportError as e:
        raise ImportError(
            "opencv-python is required for video files. "
            "Install it with: pip install opencv-python"
        ) from e

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValueError(f"Could not open video file: {path}")

    cv2_fps = cap.get(cv2.CAP_PROP_FPS)
    fps = max(1, round(cv2_fps)) if cv2_fps > 0 else 30

    ret, first = cap.read()
    if not ret:
        raise ValueError(f"Could not read first frame from: {path}")
    ph, pw = first.shape[:2]
    target_height = _compute_target_height(pw, ph, target_width)
    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)

    frames = []
    while True:
        ret, bgr = cap.read()
        if not ret:
            break
        gray_cv = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
        resized = cv2.resize(gray_cv, (target_width, target_height), interpolation=cv2.INTER_LANCZOS4)
        arr = np.clip(resized.astype(np.int32) * _N // 256, 0, _N - 1)
        frames.append([''.join(GRADIENT[i] for i in row) for row in arr.tolist()])

    cap.release()
    return frames, fps, target_width, target_height


def _write_frames(frames: list[list[str]], path: Path) -> None:
    """Write frames in one-frame-per-line format (literal \\n row separators).

    Same pattern as binarize_ascii_video.py:write_frames.
    """
    lines = ['\\n'.join(row for row in frame) for frame in frames]
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def convert_gif(
    input_path: str,
    output_dir: str,
    target_width: int = 60,
) -> tuple[str, int, int, int]:
    """Convert a GIF or video file to an ASCII frame text file.

    Dispatches to PIL (GIF/WEBP/PNG) or cv2 (MP4/AVI/MOV/MKV) based on suffix.

    Returns:
        (out_path, fps, width, height) — out_path is the absolute path to the
        written .txt file; fps/width/height describe its content.

    Output filename: f'{stem}_{fps}fps_{width}x{height}.txt'
    """
    in_path = Path(input_path)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    suffix = in_path.suffix.lower()
    video_suffixes = {'.mp4', '.avi', '.mov', '.mkv', '.webm'}

    if suffix in video_suffixes:
        frames, fps, w, h = _cv2_to_ascii_frames(str(in_path), target_width)
    else:
        # PIL path handles GIF, WEBP, PNG, JPEG, etc.
        with Image.open(str(in_path)) as img:
            frames, fps, w, h = _gif_to_ascii_frames(img, target_width)

    if not frames:
        raise ValueError(f"No frames extracted from: {input_path}")

    out_filename = f'{in_path.stem}_{fps}fps_{w}x{h}.txt'
    out_path = out_dir / out_filename
    _write_frames(frames, out_path)
    return str(out_path), fps, w, h


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument('input', help='Source GIF/video file path')
    parser.add_argument(
        '--output-dir',
        default=str(Path(__file__).parent.parent / 'ascii_videos'),
        help='Output directory (default: ascii_videos/ at repo root)',
    )
    parser.add_argument(
        '--width',
        type=int,
        default=60,
        help='Target ASCII width in characters (default: 60)',
    )
    args = parser.parse_args()

    out_path, fps, w, h = convert_gif(args.input, args.output_dir, args.width)
    print(f'Written: {out_path}')
    print(f'  {w}x{h} @ {fps}fps')


if __name__ == '__main__':
    main()
