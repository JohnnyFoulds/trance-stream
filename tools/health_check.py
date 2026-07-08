# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Composite trance-quality health check for a rendered WAV file.

Runs 7 pass/fail tests derived from docs/trance-reference.md Section 4, and
optionally computes MFCC cosine similarity against a reference WAV.

Usage::

    python tools/health_check.py [WAV_PATH] [--ref REF_WAV]

    WAV_PATH   Rendered WAV to check  (default: /tmp/trance_out.wav)
    --ref      Reference WAV for MFCC similarity (default: /tmp/switch_angel_ref.wav
               if it exists; skipped if absent)

Requirements::

    pip install librosa scipy numpy
"""

import argparse
import math
import os
import sys
import wave

try:
    import numpy as np
except ImportError:
    sys.exit("numpy required: pip install numpy")

try:
    import librosa
    import scipy.stats
    from scipy.spatial.distance import cosine as cosine_dist
except ImportError:
    sys.exit("librosa and scipy required: pip install librosa scipy")

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
parser.add_argument("wav", nargs="?", default="/tmp/trance_out.wav",
                    help="Rendered WAV to check")
parser.add_argument("--ref", default="/tmp/switch_angel_ref.wav",
                    help="Reference WAV for MFCC similarity (skipped if absent)")
args = parser.parse_args()

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"

results: list[tuple[str, str, str]] = []   # (name, status, detail)


def check(name: str, passed: bool, detail: str) -> None:
    results.append((name, PASS if passed else FAIL, detail))


# ---------------------------------------------------------------------------
# Load WAV
# ---------------------------------------------------------------------------

print(f"Health check: {args.wav}\n")

y, sr = librosa.load(args.wav, sr=22050, mono=True)
duration_s = len(y) / sr
print(f"  Duration: {duration_s:.1f} s  ({sr} Hz mono)\n")

# ---------------------------------------------------------------------------
# 1. BPM
# ---------------------------------------------------------------------------

y_p = librosa.effects.percussive(y, margin=3)
prior = scipy.stats.uniform(130, 20)
tempo_arr, _ = librosa.beat.beat_track(y=y_p, sr=sr, hop_length=512, prior=prior)
bpm = float(tempo_arr) if np.ndim(tempo_arr) == 0 else float(tempo_arr[0])
check("BPM", 136.0 <= bpm <= 145.0, f"{bpm:.1f}  (target: ~140, librosa ±5)")

# ---------------------------------------------------------------------------
# 2. Beat-period autocorrelation (Groove/Drop groove check)
# ---------------------------------------------------------------------------

onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=512)
ac = librosa.autocorrelate(onset_env, max_size=sr // 512 * 4)
ac = ac / (ac[0] + 1e-9)
beat_period_frames = int((60.0 / 140.0) * sr / 512)
beat_ac = float(ac[beat_period_frames]) if beat_period_frames < len(ac) else 0.0
check("Beat autocorr", beat_ac >= 0.40,
      f"{beat_ac:.3f}  (target: >0.40 — four-on-floor periodicity)")

# ---------------------------------------------------------------------------
# 3. Spectral centroid mean
# ---------------------------------------------------------------------------

centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=512)[0]
c_mean = float(centroid.mean())
check("Centroid mean", 800.0 <= c_mean <= 3500.0,
      f"{c_mean:.0f} Hz  (target: 800–3500 Hz)")

# ---------------------------------------------------------------------------
# 4. Centroid std — LFO audibility
# ---------------------------------------------------------------------------

c_std = float(centroid.std())
check("Centroid std (LFO)", c_std >= 200.0,
      f"{c_std:.0f} Hz  (target: >200 Hz — filter LFO audible)")

# ---------------------------------------------------------------------------
# 5. LFO rate in centroid FFT
# ---------------------------------------------------------------------------

frames_per_sec = sr // 512
c_chunked = [
    float(centroid[i:i + frames_per_sec].mean())
    for i in range(0, len(centroid) - frames_per_sec, frames_per_sec)
]
if len(c_chunked) >= 4:
    lfo_spec = np.abs(np.fft.rfft(c_chunked - np.mean(c_chunked)))
    lfo_freqs = np.fft.rfftfreq(len(c_chunked), d=1.0)
    peak_lfo = float(lfo_freqs[np.argmax(lfo_spec)])
    check("LFO rate", 0.01 <= peak_lfo <= 0.50,
          f"{peak_lfo:.3f} Hz  (target: 0.01–0.50 Hz)")
else:
    results.append(("LFO rate", SKIP, "clip too short"))

# ---------------------------------------------------------------------------
# 6. Chroma entropy
# ---------------------------------------------------------------------------

y_h = librosa.effects.harmonic(y, margin=8)
chroma = librosa.feature.chroma_cens(y=y_h, sr=sr, hop_length=512)
cm = chroma.mean(axis=1)
cm = cm / (cm.sum() + 1e-9)
entropy = float(-np.sum(cm * np.log2(cm + 1e-9)))
check("Chroma entropy", 1.5 <= entropy <= 3.5,
      f"{entropy:.2f}  (target: 1.5–3.5, max {math.log2(12):.2f})")

# ---------------------------------------------------------------------------
# 7. Band energy ratios
# ---------------------------------------------------------------------------

S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)
BANDS = [
    ("sub",    0,    80),
    ("bass",   80,   300),
    ("mid",    300,  2000),
    ("hi-mid", 2000, 8000),
]
band_rms: dict[str, float] = {}
for name, lo, hi in BANDS:
    mask = (freqs >= lo) & (freqs < hi)
    band_rms[name] = float(np.sqrt((S[mask] ** 2).mean())) if mask.any() else 0.0

peak_band = max(band_rms.values()) or 1e-9
bass_db = 20 * math.log10(band_rms["bass"] / peak_band + 1e-9)
himid_db = 20 * math.log10(band_rms["hi-mid"] / peak_band + 1e-9)
band_detail = "  ".join(
    f"{n}: {20*math.log10(v/peak_band+1e-9):+.1f}dB"
    for n, v in band_rms.items()
)
# Bass should be the strongest or within 6 dB of strongest; hi-mid not too loud
bass_ok = bass_db >= -6.0
himid_ok = himid_db <= -10.0
check("Band balance", bass_ok and himid_ok,
      f"{band_detail}  (bass ≥−6 dB, hi-mid ≤−10 dB)")

# ---------------------------------------------------------------------------
# 8. MFCC cosine similarity vs reference
# ---------------------------------------------------------------------------

ref_path = args.ref
if os.path.exists(ref_path):
    y_ref, sr_ref = librosa.load(ref_path, sr=22050, mono=True)
    mfcc_gen = librosa.feature.mfcc(y=y,     sr=sr,     n_mfcc=13).mean(axis=1)
    mfcc_ref = librosa.feature.mfcc(y=y_ref, sr=sr_ref, n_mfcc=13).mean(axis=1)
    sim = float(1.0 - cosine_dist(mfcc_gen, mfcc_ref))
    check("MFCC similarity", sim >= 0.70,
          f"{sim:.4f}  (target: >0.70 vs Switch Angel reference)")
else:
    results.append(("MFCC similarity", SKIP,
                    f"reference not found at {ref_path}"))

# ---------------------------------------------------------------------------
# Print report
# ---------------------------------------------------------------------------

print("=" * 60)
print(f"{'CHECK':<22}  {'STATUS'}  DETAIL")
print("-" * 60)
for name, status, detail in results:
    print(f"  {name:<20}  {status}  {detail}")
print("=" * 60)

passed = sum(1 for _, s, _ in results if "PASS" in s)
failed = sum(1 for _, s, _ in results if "FAIL" in s)
skipped = sum(1 for _, s, _ in results if "SKIP" in s)
total = passed + failed
print(f"\n  {passed}/{total} checks passed  ({skipped} skipped)\n")

sys.exit(0 if failed == 0 else 1)
