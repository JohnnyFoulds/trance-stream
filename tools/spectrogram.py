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
import math
import wave
from pathlib import Path

try:
    import numpy as np
except ImportError:
    raise ImportError("numpy required: pip install numpy")

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

BANDS = [
    ("sub",    0,    80),
    ("bass",   80,   300),
    ("mid",    300,  2000),
    ("hi_mid", 2000, 8000),
    ("air",    8000, 22050),
]


def analyse_spectrum(wav_path: str) -> dict:
    """Compute spectral centroid, per-band energy, and brightness for a WAV file.

    Returns:
      mean_centroid_hz   — power-weighted spectral centroid averaged over all frames
      brightness_score   — fraction of energy above 2 kHz (0.0–1.0)
      band_energy        — {sub, bass, mid, hi_mid, air}: mean magnitude per frame
      band_energy_db     — same, relative to loudest band in dB
      duration_s
      framerate

    Note: thresholds are calibrated against measured SA reference clips (targets.json).
    SA clips at t=90s show centroid 425–929 Hz, brightness 2.3–4.8%.
    The comment "trance target: 800-2500 Hz" was aspirational; use targets.json values.
    """
    with wave.open(wav_path, "rb") as wf:
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

    CHUNK = 4096
    HOP   = CHUNK // 2

    band_accum = {name: [] for name, _, _ in BANDS}
    centroids  = []
    n_steps = (len(mono) - CHUNK) // HOP

    for i in range(n_steps):
        seg    = mono[i * HOP: i * HOP + CHUNK]
        window = np.hanning(CHUNK)
        spec   = np.abs(np.fft.rfft(seg * window))
        freqs  = np.fft.rfftfreq(CHUNK, 1.0 / framerate)

        power = spec ** 2
        denom = power.sum()
        if denom > 0:
            centroids.append(float((freqs * power).sum() / denom))

        for name, lo, hi in BANDS:
            mask = (freqs >= lo) & (freqs < hi)
            e = float(np.sqrt((spec[mask] ** 2).mean())) if mask.any() else 0.0
            band_accum[name].append(e)

    band_energy = {name: float(np.mean(v)) if v else 0.0
                   for name, v in band_accum.items()}

    peak_val = max(band_energy.values()) or 1e-9
    band_energy_db = {
        name: 20 * math.log10(max(v / peak_val, 1e-9))
        for name, v in band_energy.items()
    }

    hi_energy  = band_energy.get("hi_mid", 0) + band_energy.get("air", 0)
    all_energy = sum(band_energy.values()) or 1e-9
    brightness = hi_energy / all_energy

    return {
        "mean_centroid_hz": float(np.mean(centroids)) if centroids else 0.0,
        "brightness_score": brightness,
        "band_energy":      band_energy,
        "band_energy_db":   band_energy_db,
        "duration_s":       total_s,
        "framerate":        framerate,
    }


def generate_spectrogram(wav_path: str, out_path: str = None,
                          title: str = None) -> str:
    """Generate a mel spectrogram PNG for a WAV file.

    Requires librosa and matplotlib. Returns the output PNG path.
    Raises ImportError if either dependency is missing.
    """
    if not HAS_LIBROSA:
        raise ImportError("librosa required: pip install librosa")
    if not HAS_MPL:
        raise ImportError("matplotlib required: pip install matplotlib")

    out_path = out_path or str(Path(wav_path).with_suffix(".png"))
    title    = title or Path(wav_path).name

    with wave.open(wav_path, "rb") as wf:
        n_channels = wf.getnchannels()
        framerate  = wf.getframerate()
        n_frames   = wf.getnframes()
        raw        = wf.readframes(n_frames)

    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if n_channels == 2:
        mono = pcm.reshape(-1, 2).mean(axis=1)
    else:
        mono = pcm.flatten()

    y  = mono
    sr = framerate
    if sr != 22050:
        target_len = int(len(y) * 22050 / sr)
        y = np.interp(
            np.linspace(0, len(y) - 1, target_len),
            np.arange(len(y)), y
        ).astype(np.float32)
        sr = 22050

    n_fft   = 2048
    hop_len = 512
    n_mels  = 128
    S       = librosa.feature.melspectrogram(y=y, sr=sr, n_fft=n_fft,
                                              hop_length=hop_len, n_mels=n_mels,
                                              fmax=sr // 2)
    S_db    = librosa.power_to_db(S, ref=np.max)

    centroid_hz = librosa.feature.spectral_centroid(y=y, sr=sr,
                                                     n_fft=n_fft,
                                                     hop_length=hop_len)[0]
    times = librosa.times_like(centroid_hz, sr=sr, hop_length=hop_len)
    mean_centroid = float(centroid_hz.mean())

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={"height_ratios": [4, 1]})
    fig.suptitle(title, fontsize=13, fontweight="bold")

    img = librosa.display.specshow(
        S_db, x_axis="time", y_axis="mel",
        sr=sr, hop_length=hop_len,
        fmax=sr // 2,
        ax=axes[0],
        cmap="magma",
    )
    axes[0].set_title("Mel spectrogram (dB)")
    plt.colorbar(img, ax=axes[0], format="%+2.0f dB")

    for freq_hz, label in ((80, "80"), (300, "300"), (2000, "2k"), (8000, "8k")):
        axes[0].axhline(y=freq_hz, color="cyan", linewidth=0.6, linestyle="--", alpha=0.5)
        axes[0].text(0.5, freq_hz * 1.05, label + " Hz", color="cyan",
                     fontsize=7, alpha=0.7, transform=axes[0].get_yaxis_transform())

    ax2 = axes[0].twinx()
    ax2.plot(times, centroid_hz, color="yellow", linewidth=0.8, alpha=0.6,
             label="centroid")
    ax2.set_ylabel("centroid (Hz)", color="yellow", fontsize=8)
    ax2.tick_params(axis="y", colors="yellow", labelsize=7)
    ax2.set_ylim(0, sr // 2)
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}"))

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
    plt.close(fig)
    return out_path


def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wav",   nargs="?", default="/tmp/trance_out.wav")
    parser.add_argument("--out", default=None, help="Output PNG path")
    parser.add_argument("--title", default=None)
    args = parser.parse_args()

    stats    = analyse_spectrum(args.wav)
    out_path = args.out or str(Path(args.wav).with_suffix(".png"))
    title    = args.title or Path(args.wav).name

    print(f"File:        {args.wav}")
    print(f"Duration:    {stats['duration_s']:.1f} s  ({stats['framerate']} Hz)")

    be       = stats["band_energy"]
    peak_val = max(be.values()) or 1e-9
    labels   = {
        "sub":    "sub",
        "bass":   "bass",
        "mid":    "mid",
        "hi_mid": "hi-mid",
        "air":    "air",
    }
    print("\nSpectral energy by band (relative to loudest):")
    for key, label in labels.items():
        v       = be.get(key, 0)
        db      = 20 * math.log10(max(v / peak_val, 1e-9))
        bar_str = "█" * int(30 * v / peak_val)
        print(f"  {label:10s}  {bar_str:<30s}  {db:+.1f} dB")

    print(f"\nSpectral centroid: mean={stats['mean_centroid_hz']:.0f} Hz")
    print(f"Brightness score:  {stats['brightness_score']:.2%} of energy above 2 kHz")
    print(f"  (SA ref clips at t=90s: centroid 425–929 Hz, brightness 2.3–4.8%)")
    print(f"  (see research/reference_audio/targets.json for measured values)")

    try:
        out = generate_spectrogram(args.wav, out_path, title)
        print(f"\nSaved: {out}")
    except ImportError as e:
        print(f"\nSkipping spectrogram image — {e}")


if __name__ == "__main__":
    main()
