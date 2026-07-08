# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Mel spectrogram and spectral centroid analysis for a WAV file.

Generates a mel spectrogram image and prints quantitative spectral measurements:
spectral centroid over time, energy per band, and a brightness score — all useful
for comparing the generated output against a reference track.

Usage::

    python tools/spectrogram.py [WAV_PATH] [--out PNG_PATH] [--title TITLE]

    WAV_PATH   Path to WAV file (default: /tmp/trance_out.wav)
    --out      Output PNG path (default: <wav>.png)
    --title    Title text displayed on the spectrogram

Typical A/B comparison workflow::

    python tools/spectrogram.py /tmp/switch_angel_ref.wav --out /tmp/ref_spec.png --title "Switch Angel Reference"
    python tools/spectrogram.py /tmp/gen_new.wav --out /tmp/gen_spec.png --title "Generated (new)"
    open /tmp/ref_spec.png /tmp/gen_spec.png
"""
import argparse
import math
import sys
import wave
from pathlib import Path

try:
    import numpy as np
except ImportError:
    sys.exit("numpy required: pip install numpy")

try:
    import librosa
    import librosa.display
    HAS_LIBROSA = True
except ImportError:
    HAS_LIBROSA = False

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("wav",   nargs="?", default="/tmp/trance_out.wav")
parser.add_argument("--out", default=None, help="Output PNG path")
parser.add_argument("--title", default=None)
args = parser.parse_args()

out_path = args.out or str(Path(args.wav).with_suffix(".png"))
title    = args.title or Path(args.wav).name

# ---------------------------------------------------------------------------
# Load WAV
# ---------------------------------------------------------------------------

with wave.open(args.wav, "rb") as wf:
    n_channels = wf.getnchannels()
    framerate  = wf.getframerate()
    n_frames   = wf.getnframes()
    raw        = wf.readframes(n_frames)

pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
if n_channels == 2:
    mono = pcm.reshape(-1, 2).mean(axis=1)
else:
    mono = pcm.flatten()

total_s = len(mono) / framerate
print(f"File:        {args.wav}")
print(f"Duration:    {total_s:.1f} s  ({framerate} Hz, {n_channels} ch)")

# ---------------------------------------------------------------------------
# Spectral analysis (numpy FFT — no librosa dependency for the text report)
# ---------------------------------------------------------------------------

CHUNK  = 4096
HOP    = CHUNK // 2
BANDS  = [
    ("sub",    0,    80),
    ("bass",   80,   300),
    ("mid",    300,  2000),
    ("hi-mid", 2000, 8000),
    ("air",    8000, 22050),
]

band_energy   = {name: [] for name, _, _ in BANDS}
centroids     = []
n_steps = (len(mono) - CHUNK) // HOP

for i in range(n_steps):
    seg      = mono[i * HOP: i * HOP + CHUNK]
    window   = np.hanning(CHUNK)
    spec     = np.abs(np.fft.rfft(seg * window))
    freqs    = np.fft.rfftfreq(CHUNK, 1.0 / framerate)

    # Spectral centroid
    power    = spec ** 2
    denom    = power.sum()
    if denom > 0:
        centroids.append(float((freqs * power).sum() / denom))

    for name, lo, hi in BANDS:
        mask = (freqs >= lo) & (freqs < hi)
        e = float(np.sqrt((spec[mask] ** 2).mean())) if mask.any() else 0.0
        band_energy[name].append(e)

print()
print("Spectral energy by band (relative to loudest):")
vals     = {name: float(np.mean(v)) for name, v in band_energy.items()}
peak_val = max(vals.values()) or 1e-9
for name, v in vals.items():
    db      = 20 * math.log10(max(v / peak_val, 1e-9))
    bar_str = "█" * int(30 * v / peak_val)
    print(f"  {name:10s}  {bar_str:<30s}  {db:+.1f} dB")

mean_centroid = float(np.mean(centroids)) if centroids else 0.0
print(f"\nSpectral centroid: mean={mean_centroid:.0f} Hz  "
      f"(trance target: 800-2500 Hz)")

# Simple brightness score: fraction of energy above 2 kHz
hi_energy  = vals["hi-mid"] + vals["air"]
all_energy = sum(vals.values()) or 1e-9
brightness = hi_energy / all_energy
print(f"Brightness score:  {brightness:.2%} of energy above 2 kHz  "
      f"(Switch Angel ref: ~30-45%)")

# ---------------------------------------------------------------------------
# Spectrogram image (requires librosa + matplotlib)
# ---------------------------------------------------------------------------

if not HAS_LIBROSA or not HAS_MPL:
    missing = []
    if not HAS_LIBROSA: missing.append("librosa")
    if not HAS_MPL:     missing.append("matplotlib")
    print(f"\nSkipping spectrogram image — install: pip install {' '.join(missing)}")
    sys.exit(0)

print(f"\nGenerating mel spectrogram → {out_path}")

# Resample to 22050 Hz for faster mel computation if needed
y = mono
sr = framerate
if sr != 22050:
    # Simple downsample (skip librosa.resample to avoid resampy dep)
    ratio = 22050 / sr
    target_len = int(len(y) * ratio)
    y = np.interp(
        np.linspace(0, len(y) - 1, target_len),
        np.arange(len(y)), y
    ).astype(np.float32)
    sr = 22050

# Mel spectrogram
n_fft   = 2048
hop_len = 512
n_mels  = 128
S       = librosa.feature.melspectrogram(y=y, sr=sr, n_fft=n_fft,
                                          hop_length=hop_len, n_mels=n_mels,
                                          fmax=sr // 2)
S_db    = librosa.power_to_db(S, ref=np.max)

# Spectral centroid overlaid
centroid_hz = librosa.feature.spectral_centroid(y=y, sr=sr,
                                                  n_fft=n_fft,
                                                  hop_length=hop_len)[0]
times = librosa.times_like(centroid_hz, sr=sr, hop_length=hop_len)

fig, axes = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={"height_ratios": [4, 1]})
fig.suptitle(title, fontsize=13, fontweight="bold")

# Top: mel spectrogram
img = librosa.display.specshow(
    S_db, x_axis="time", y_axis="mel",
    sr=sr, hop_length=hop_len,
    fmax=sr // 2,
    ax=axes[0],
    cmap="magma",
)
axes[0].set_title("Mel spectrogram (dB)")
plt.colorbar(img, ax=axes[0], format="%+2.0f dB")

# Overlay frequency band boundaries
for freq_hz, label in ((80, "80"), (300, "300"), (2000, "2k"), (8000, "8k")):
    axes[0].axhline(y=freq_hz, color="cyan", linewidth=0.6, linestyle="--", alpha=0.5)
    axes[0].text(0.5, freq_hz * 1.05, label + " Hz", color="cyan",
                 fontsize=7, alpha=0.7, transform=axes[0].get_yaxis_transform())

# Overlay spectral centroid
ax2 = axes[0].twinx()
ax2.plot(times, centroid_hz, color="yellow", linewidth=0.8, alpha=0.6,
         label="centroid")
ax2.set_ylabel("centroid (Hz)", color="yellow", fontsize=8)
ax2.tick_params(axis="y", colors="yellow", labelsize=7)
ax2.set_ylim(0, sr // 2)
ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}"))

# Bottom: centroid over time (clearer view)
axes[1].plot(times, centroid_hz, color="orange", linewidth=1.0)
axes[1].set_xlabel("Time (s)")
axes[1].set_ylabel("Centroid (Hz)")
axes[1].set_title("Spectral centroid over time")
axes[1].axhline(y=mean_centroid, color="red", linewidth=0.8, linestyle="--",
                label=f"mean {mean_centroid:.0f} Hz")
axes[1].legend(fontsize=8)
axes[1].set_xlim(0, times[-1])

plt.tight_layout()
plt.savefig(out_path, dpi=100, bbox_inches="tight")
print(f"Saved: {out_path}")
