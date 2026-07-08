# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Stem separation using Demucs htdemucs_6s model.

Separates a stereo WAV into: drums, bass, other, vocals, guitar, piano.
For Switch Angel's trance tracks (no vocals, no guitar), the relevant stems are:
  drums  — kick + hihat + clap combined
  bass   — bass line
  other  — pads + lead + pulse mixed (cannot be separated further with Demucs)

Usage::

    from tools.stem_separation import separate_stems
    stems = separate_stems("input.wav", "output_dir/")
    # Returns {"drums": "path/drums.wav", "bass": "path/bass.wav", ...}

CLI::

    python tools/stem_separation.py input.wav --out-dir stems/
"""
import argparse
import subprocess
import sys
from pathlib import Path


def separate_stems(wav_path: str, out_dir: str, model: str = "htdemucs_6s") -> dict[str, str]:
    """Separate wav_path into stems using Demucs.

    Returns dict mapping stem name to output WAV path.
    Downloads the model (~1GB) on first run (cached to ~/.cache/torch/hub/).

    Raises RuntimeError if demucs is not installed or separation fails.
    """
    wav_path = Path(wav_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Demucs outputs to: out_dir/<model>/<wav_stem>/<voice>.wav
    stem_name = wav_path.stem
    expected_dir = out_dir / model / stem_name

    # Run demucs
    cmd = [
        sys.executable, "-m", "demucs",
        "-n", model,
        str(wav_path),
        "-o", str(out_dir),
    ]
    print(f"  Running: demucs -n {model} {wav_path.name}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Demucs failed:\n{result.stderr}")

    # Collect output paths
    stems = {}
    for wav in expected_dir.glob("*.wav"):
        stems[wav.stem] = str(wav)

    if not stems:
        raise RuntimeError(f"No stems found in {expected_dir}")

    return stems


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wav", help="Input WAV file")
    parser.add_argument("--out-dir", default="research/reference_audio/stems",
                        help="Output directory for stems")
    parser.add_argument("--model", default="htdemucs_6s")
    args = parser.parse_args()

    print(f"Separating {args.wav}...")
    stems = separate_stems(args.wav, args.out_dir, args.model)
    print(f"\nStem outputs:")
    for name, path in sorted(stems.items()):
        size_mb = Path(path).stat().st_size / 1_000_000
        print(f"  {name:10s}  {path}  ({size_mb:.1f} MB)")


if __name__ == "__main__":
    main()
