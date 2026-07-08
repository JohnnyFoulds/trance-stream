# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Phase 0 reference audio extraction pipeline.

Extracts 90s WAV clips from each Switch Angel .webm session (skipping first 90s
of setup talk) and downloads her public pad samples.

Outputs:
  research/reference_audio/<id>_90s.wav   — 5 clips, ~15MB each
  research/reference_audio/pads/padN.wav  — pad10..14, ~2-6MB each
  research/reference_audio/targets.json   — measured spectral targets

Usage::

    python tools/extract_reference_audio.py [--skip-pads] [--skip-extract]

    --skip-pads      Skip downloading pad samples
    --skip-extract   Skip extracting WAV clips (useful if already done)
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import urllib.request
import wave
from pathlib import Path

try:
    import numpy as np
except ImportError:
    sys.exit("numpy required: pip install numpy")

REPO_ROOT = Path(__file__).parent.parent
VIDEOS_DIR = REPO_ROOT / "research" / "videos"
REF_DIR = REPO_ROOT / "research" / "reference_audio"
PADS_DIR = REF_DIR / "pads"
TARGETS_PATH = REF_DIR / "targets.json"

VIDEO_IDS = [
    "3fpx7Scysw4",       # Coding Trance IV — primary reference (128 OCR snapshots)
    "-pDO2RhcGhM",       # Coding Trance From Scratch YET AGAIN
    "GWXCCBsOMSg",       # Coding Trance Full Narrated — best documented build order
    "iu5rnQkfO6M",       # Coding Trance From Scratch Again
    "vn9VDbacUgQ",       # Coding Trance Official
]

PAD_URLS = {
    f"pad{n}": f"https://raw.githubusercontent.com/switchangel/pad/main/{n}_switch_angel_pad.wav"
    for n in range(10, 15)
}

SKIP_SECONDS = 90    # skip first 90s of setup talk in each session
CLIP_SECONDS = 90    # extract 90s of musical content

BANDS = [
    ("sub",    0,    80),
    ("bass",   80,   300),
    ("mid",    300,  2000),
    ("hi-mid", 2000, 8000),
    ("air",    8000, 22050),
]


def find_webm(video_id: str) -> Path | None:
    for f in VIDEOS_DIR.glob(f"{video_id}_*.webm"):
        return f
    return None


def extract_clip(webm_path: Path, out_path: Path) -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-i", str(webm_path),
        "-vn", "-acodec", "pcm_s16le", "-ar", "44100",
        "-ss", str(SKIP_SECONDS), "-t", str(CLIP_SECONDS),
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True)
    return result.returncode == 0


def download_pad(url: str, out_path: Path) -> bool:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with urllib.request.urlopen(url) as resp:
            data = resp.read()
        # Verify it's a real WAV (RIFF header)
        if not data[:4] == b"RIFF":
            print(f"  WARNING: {url} did not return a WAV file")
            return False
        out_path.write_bytes(data)
        return True
    except Exception as e:
        print(f"  ERROR: {e}")
        return False


def analyse_spectrum(wav_path: Path) -> dict:
    with wave.open(str(wav_path), "rb") as wf:
        n_channels = wf.getnchannels()
        framerate = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    mono = pcm.reshape(-1, 2).mean(axis=1) if n_channels == 2 else pcm.flatten()

    CHUNK = 4096
    HOP = CHUNK // 2
    band_energy = {name: [] for name, _, _ in BANDS}
    centroids = []
    n_steps = (len(mono) - CHUNK) // HOP

    for i in range(n_steps):
        seg = mono[i * HOP: i * HOP + CHUNK]
        window = np.hanning(CHUNK)
        spec = np.abs(np.fft.rfft(seg * window))
        freqs = np.fft.rfftfreq(CHUNK, 1.0 / framerate)

        power = spec ** 2
        denom = power.sum()
        if denom > 0:
            centroids.append(float((freqs * power).sum() / denom))

        for name, lo, hi in BANDS:
            mask = (freqs >= lo) & (freqs < hi)
            e = float(np.sqrt((spec[mask] ** 2).mean())) if mask.any() else 0.0
            band_energy[name].append(e)

    vals = {name: float(np.mean(v)) for name, v in band_energy.items()}
    peak_val = max(vals.values()) or 1e-9
    vals_db = {name: round(20 * math.log10(max(v / peak_val, 1e-9)), 1)
               for name, v in vals.items()}

    mean_centroid = float(np.mean(centroids)) if centroids else 0.0
    hi_energy = vals["hi-mid"] + vals["air"]
    all_energy = sum(vals.values()) or 1e-9
    brightness = hi_energy / all_energy

    return {
        "mean_centroid_hz": round(mean_centroid, 1),
        "brightness_score": round(brightness, 4),
        "band_energy_db": vals_db,
        "band_energy_raw": {k: round(v, 6) for k, v in vals.items()},
        "duration_s": round(len(mono) / framerate, 1),
        "sample_rate": framerate,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--skip-pads", action="store_true")
    parser.add_argument("--skip-extract", action="store_true")
    args = parser.parse_args()

    REF_DIR.mkdir(parents=True, exist_ok=True)

    # --- Extract WAV clips ---
    if not args.skip_extract:
        print("Extracting reference WAV clips...")
        for vid_id in VIDEO_IDS:
            out = REF_DIR / f"{vid_id}_90s.wav"
            if out.exists():
                print(f"  {vid_id}: already exists, skipping")
                continue
            webm = find_webm(vid_id)
            if webm is None:
                print(f"  {vid_id}: WARNING — no .webm found in {VIDEOS_DIR}")
                continue
            print(f"  {vid_id}: extracting {SKIP_SECONDS}s–{SKIP_SECONDS+CLIP_SECONDS}s... ", end="", flush=True)
            if extract_clip(webm, out):
                size_mb = out.stat().st_size / 1_000_000
                print(f"ok ({size_mb:.1f} MB)")
            else:
                print("FAILED")

    # --- Download pad samples ---
    if not args.skip_pads:
        print("\nDownloading SA pad samples (Unlicense)...")
        for name, url in PAD_URLS.items():
            out = PADS_DIR / f"{name}.wav"
            if out.exists() and out.stat().st_size > 10_000:
                print(f"  {name}: already exists, skipping")
                continue
            print(f"  {name}: downloading... ", end="", flush=True)
            if download_pad(url, out):
                size_mb = out.stat().st_size / 1_000_000
                print(f"ok ({size_mb:.1f} MB)")
            else:
                print("FAILED")

    # --- Measure spectral targets ---
    print("\nMeasuring spectral targets...")
    targets = {}
    for vid_id in VIDEO_IDS:
        wav = REF_DIR / f"{vid_id}_90s.wav"
        if not wav.exists():
            print(f"  {vid_id}: missing, skipping")
            continue
        print(f"  {vid_id}: analysing...", end="", flush=True)
        stats = analyse_spectrum(wav)
        targets[vid_id] = stats
        print(f" centroid={stats['mean_centroid_hz']:.0f} Hz  brightness={stats['brightness_score']:.2%}")

    if targets:
        # Compute cross-video averages for use as integration test thresholds
        centroids = [t["mean_centroid_hz"] for t in targets.values()]
        brightnesses = [t["brightness_score"] for t in targets.values()]
        targets["_aggregate"] = {
            "note": "Cross-video averages — use these as integration test thresholds",
            "mean_centroid_hz_avg": round(sum(centroids) / len(centroids), 1),
            "mean_centroid_hz_min": round(min(centroids), 1),
            "mean_centroid_hz_max": round(max(centroids), 1),
            "brightness_score_avg": round(sum(brightnesses) / len(brightnesses), 4),
            "brightness_score_min": round(min(brightnesses), 4),
            "brightness_score_max": round(max(brightnesses), 4),
        }
        TARGETS_PATH.write_text(json.dumps(targets, indent=2))
        print(f"\nWrote {TARGETS_PATH}")

        agg = targets["_aggregate"]
        print(f"\nAggregate targets:")
        print(f"  centroid:   {agg['mean_centroid_hz_min']:.0f}–{agg['mean_centroid_hz_max']:.0f} Hz "
              f"(avg {agg['mean_centroid_hz_avg']:.0f} Hz)")
        print(f"  brightness: {agg['brightness_score_min']:.2%}–{agg['brightness_score_max']:.2%} "
              f"(avg {agg['brightness_score_avg']:.2%})")
        print(f"\nNOTE: These values are from 90s clips starting at t=90s (early-mid build-up).")
        print(f"      The filter is partially open at this point. Full-open targets will be")
        print(f"      higher (centroid 800-2500 Hz) once the arrangement is complete.")


if __name__ == "__main__":
    main()
