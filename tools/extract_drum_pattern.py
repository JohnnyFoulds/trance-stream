# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Drum pattern extractor — grid-aligned step sequencer representation.

Takes a drums stem WAV (from Demucs) and outputs a per-voice step pattern
snapped to the nearest 16th-note grid at a given BPM, suitable for direct
use in the trance_stream synthesis pipeline.

Outputs for each detected voice (kick, snare/clap, hihat):
  - A 16-step or 32-step boolean pattern (1=hit, 0=rest)
  - Onset times with sub-16th alignment error (for validation)
  - Detection confidence

Algorithm (grid-snapping):
  1. Bandpass-filter the drums stem into frequency bands corresponding to each voice:
       kick:  50–200Hz
       snare: 200–500Hz (or clap: 800–3000Hz)
       hihat: 5000–16000Hz
  2. Detect onsets in each band via spectral flux (Bello et al., 2005).
  3. Snap each onset to the nearest 16th-note grid position.
  4. If a grid position has ≥1 onset across all bars, set that step to 1.
  5. Report mean alignment error as confidence proxy.

Algorithm references (APA 7th edition):
- Bello, J. P., Daudet, L., Abdallah, S., Duxbury, C., Davies, M., & Sandler, M. B.
  (2005). A tutorial on onset detection in music signals. IEEE Transactions on Speech
  and Audio Processing, 13(5), 1035–1047. https://doi.org/10.1109/TSA.2005.851998
- McFee, B., Raffel, C., Liang, D., Ellis, D. P. W., McVicar, M., Battenberg, E.,
  & Nieto, O. (2015). librosa: Audio and music signal analysis in Python. Proceedings
  of the 14th Python in Science Conference, 18–25.
  https://doi.org/10.25080/Majora-7b98e3ed-003

Usage::

    python tools/extract_drum_pattern.py stems/drums.wav --bpm 138 --steps 16
    python tools/extract_drum_pattern.py stems/drums.wav --bpm 138 --steps 32 --bars 8

Module API::

    from tools.extract_drum_pattern import extract_drum_pattern
    pattern = extract_drum_pattern("stems/drums.wav", bpm=138.0, n_steps=16)
    # Returns dict with "kick", "snare", "hihat" each being a list[int] of length n_steps.
"""
import argparse
import sys
from pathlib import Path

try:
    import numpy as np
except ImportError:
    sys.exit("numpy required: pip install numpy")

try:
    import librosa
except ImportError:
    sys.exit("librosa required: pip install librosa")

try:
    from scipy.signal import butter, filtfilt, find_peaks
except ImportError:
    sys.exit("scipy required: pip install scipy")


# ---------------------------------------------------------------------------
# Band definitions per voice
# ---------------------------------------------------------------------------

VOICE_BANDS = {
    "kick":  (60,   200),   # 40Hz lower bound causes butterworth NaN; 60Hz is safe
    "snare": (200,  500),
    "clap":  (800,  3000),
    "hihat": (5000, 18000),
}


def _bandpass(y: np.ndarray, sr: int, lo: float, hi: float) -> np.ndarray:
    hi = min(hi, sr / 2 - 1)
    if lo >= hi:
        return np.zeros_like(y)
    b, a = butter(4, [lo / (sr / 2), hi / (sr / 2)], btype='band')
    return filtfilt(b, a, y)


def _detect_onsets_in_band(y_band: np.ndarray, sr: int,
                            hop: int = 256, delta: float = 0.15) -> np.ndarray:
    """Return onset times (seconds) in a frequency-limited signal."""
    onset_frames = librosa.onset.onset_detect(
        y=y_band, sr=sr, hop_length=hop,
        delta=delta, backtrack=True,
        units='frames',
    )
    return librosa.frames_to_time(onset_frames, sr=sr, hop_length=hop)


def _snap_to_grid(onset_times: np.ndarray, bpm: float, n_steps: int,
                  n_bars: int) -> tuple[list[int], float]:
    """Snap onset times to a n_steps-per-bar grid.

    Uses the first onset as the phase anchor (downbeat reference). This avoids
    the common error of assuming t=0 is beat 1 (it rarely is in a song excerpt).

    Returns (pattern, mean_alignment_error_ms).
    pattern: list[int] of length n_steps, 1 if any bar has an onset on that step.
    """
    if len(onset_times) == 0:
        return [0] * n_steps, 0.0

    step_s = 60.0 / bpm / (n_steps / 4)  # duration of one step in seconds

    # Use first onset as phase anchor = step 0
    phase_anchor = float(onset_times[0])

    pattern = [0] * n_steps
    alignment_errors = []

    for t in onset_times:
        offset = t - phase_anchor
        step_float = offset / step_s
        nearest_step = int(round(step_float)) % n_steps
        alignment_error_ms = abs(step_float - round(step_float)) * step_s * 1000
        alignment_errors.append(alignment_error_ms)
        pattern[nearest_step] = 1

    mean_error = float(np.mean(alignment_errors)) if alignment_errors else 0.0
    return pattern, round(mean_error, 2)


def extract_drum_pattern(wav_path: str, bpm: float = 138.0, n_steps: int = 16,
                          start_s: float = 0.0, end_s: float | None = None,
                          voices: list[str] | None = None) -> dict:
    """Extract a step-sequencer drum pattern from a drums stem WAV.

    Parameters
    ----------
    wav_path : str
        Path to drums stem WAV (Demucs output recommended).
    bpm : float
        Song tempo in BPM.
    n_steps : int
        Pattern length in 16th-note steps (16 = one bar, 32 = two bars).
    start_s : float
        Start time (seconds) for analysis window. Use to skip intro.
    end_s : float | None
        End time (seconds). If None, analyse to end of file.
    voices : list[str] | None
        Voices to extract. Default: ["kick", "snare", "hihat"].
        Options: "kick", "snare", "clap", "hihat".

    Returns
    -------
    dict with keys:
        kick, snare, clap, hihat (each a list[int] of length n_steps)
        alignment_errors (dict: voice → mean alignment error in ms)
        n_onsets (dict: voice → total onset count)
        bar_s, step_s, bpm, n_steps
        confidence_notes (list of warning strings)
    """
    if voices is None:
        voices = ["kick", "snare", "hihat"]

    y, sr = librosa.load(wav_path, sr=None, mono=True)

    # Trim to analysis window
    start_idx = int(start_s * sr)
    end_idx = int(end_s * sr) if end_s is not None else len(y)
    y = y[start_idx:end_idx]

    bar_s = 4 * 60.0 / bpm
    step_s = bar_s / n_steps
    n_bars = len(y) / sr / bar_s

    result = {
        "bpm": bpm,
        "n_steps": n_steps,
        "bar_s": round(bar_s, 4),
        "step_s": round(step_s, 4),
        "duration_s": round(len(y) / sr, 2),
        "n_bars_analysed": round(n_bars, 1),
        "alignment_errors": {},
        "n_onsets": {},
        "confidence_notes": [],
    }

    for voice in voices:
        if voice not in VOICE_BANDS:
            result["confidence_notes"].append(f"Unknown voice '{voice}' — skipping")
            continue

        lo, hi = VOICE_BANDS[voice]
        y_band = _bandpass(y, sr, lo, hi)
        y_band = np.nan_to_num(y_band, nan=0.0, posinf=0.0, neginf=0.0)
        onset_times = _detect_onsets_in_band(y_band, sr)

        pattern, mean_error = _snap_to_grid(onset_times, bpm, n_steps, int(n_bars) + 1)
        result[voice] = pattern
        result["alignment_errors"][voice] = mean_error
        result["n_onsets"][voice] = len(onset_times)

        step_ms = step_s * 1000
        if mean_error > step_ms * 0.25:
            result["confidence_notes"].append(
                f"WARNING: {voice} alignment error {mean_error:.1f}ms > 25% of step "
                f"({step_ms * 0.25:.1f}ms). Pattern may be unreliable — check BPM."
            )
        if len(onset_times) == 0:
            result["confidence_notes"].append(
                f"WARNING: No {voice} onsets detected. Check frequency band or stem quality."
            )

    # Fill missing voices with empty patterns
    for voice in VOICE_BANDS:
        if voice not in result:
            result[voice] = [0] * n_steps

    return result


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def _pattern_to_str(pattern: list[int], chars: tuple[str, str] = ("X", ".")) -> str:
    return " ".join(chars[0] if s else chars[1] for s in pattern)


def _print_report(r: dict) -> None:
    print(f"\nDrum pattern @ {r['bpm']} BPM, {r['n_steps']} steps/bar")
    print(f"Duration: {r['duration_s']}s ({r['n_bars_analysed']:.1f} bars analysed)")
    print(f"Step duration: {r['step_s']*1000:.1f}ms\n")

    for voice in ["kick", "snare", "clap", "hihat"]:
        if voice not in r or all(s == 0 for s in r[voice]):
            continue
        n = r["n_onsets"].get(voice, 0)
        err = r["alignment_errors"].get(voice, 0)
        pattern_str = _pattern_to_str(r[voice])
        print(f"  {voice:6s}  [{pattern_str}]  ({n} onsets, err={err:.1f}ms)")

    strudel_kick = '"' + " ".join("x" if s else "~" for s in r.get("kick", [])) + '"'
    strudel_hh = '"' + " ".join("x" if s else "~" for s in r.get("hihat", [])) + '"'
    print(f"\nStrudel notation:")
    print(f"  kick:  {strudel_kick}")
    print(f"  hihat: {strudel_hh}")

    if r["confidence_notes"]:
        print(f"\nWarnings:")
        for note in r["confidence_notes"]:
            print(f"  {note}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wav", help="Drums stem WAV file")
    parser.add_argument("--bpm", type=float, default=138.0)
    parser.add_argument("--steps", type=int, default=16,
                        help="Pattern length in 16th-note steps (16 or 32)")
    parser.add_argument("--start", type=float, default=0.0,
                        help="Start time (seconds) to skip intro")
    parser.add_argument("--end", type=float, default=None,
                        help="End time (seconds)")
    parser.add_argument("--voices", nargs="+",
                        default=["kick", "snare", "hihat"],
                        help="Voices to extract")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    result = extract_drum_pattern(
        args.wav, bpm=args.bpm, n_steps=args.steps,
        start_s=args.start, end_s=args.end, voices=args.voices,
    )

    if args.json:
        import json
        print(json.dumps(result, indent=2))
    else:
        _print_report(result)


if __name__ == "__main__":
    main()
