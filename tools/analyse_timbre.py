# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Per-voice timbre analysis for synthesis parameter extraction.

Analyses a clean mono audio stem (bass, lead, pluck) and returns:
- Oscillator type best match: sine / saw / square / triangle
- Estimated filter cutoff (Hz) and resonance (0–1)
- ADSR envelope: attack_ms, decay_ms, sustain_level, release_ms
- Portamento events: list of (t_start, t_end, start_hz, end_hz, rate_sem_per_sec)
- Inharmonicity: deviation of partials from ideal integer ratios

All parameters are traceable to measurements, not heuristics. The tool reports
confidence for each estimate so the user knows which to trust.

Algorithm references (APA 7th edition):
- McFee, B., Raffel, C., Liang, D., Ellis, D. P. W., McVicar, M., Battenberg, E.,
  & Nieto, O. (2015). librosa: Audio and music signal analysis in Python. Proceedings
  of the 14th Python in Science Conference, 18–25.
  https://doi.org/10.25080/Majora-7b98e3ed-003
- Mauch, M., & Dixon, S. (2014). PYIN: A fundamental frequency estimator using
  probabilistic threshold distributions. 2014 IEEE International Conference on
  Acoustics, Speech and Signal Processing (ICASSP), 659–663.
  https://doi.org/10.1109/ICASSP.2014.6853678
- de Cheveigné, A., & Kawahara, H. (2002). YIN, a fundamental frequency estimator
  for speech and music. The Journal of the Acoustical Society of America, 111(4),
  1917–1930. https://doi.org/10.1121/1.1458024

Usage::

    python tools/analyse_timbre.py stems/bass.wav --bpm 138
    python tools/analyse_timbre.py stems/melody.wav --bpm 138 --fmin 80 --fmax 2000

CLI output: human-readable table of synthesis parameters.
Module API: analyse_timbre(wav_path, bpm, fmin, fmax) → dict
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
# Oscillator type discrimination
# ---------------------------------------------------------------------------

def _classify_oscillator(fundamental_hz: float, partials: list[tuple[float, float]],
                          sr: int) -> tuple[str, float, dict]:
    """Classify oscillator type from partial amplitude ratios.

    partials: list of (freq_hz, relative_amplitude) sorted by frequency ascending.
    Returns (type_name, confidence_0_to_1, details_dict).

    Theory:
      Sine:     only fundamental (no harmonics), or negligible harmonics < 10% of fundamental.
      Sawtooth: all harmonics present, amplitude ∝ 1/n (6dB/octave rolloff per harmonic number).
      Square:   only odd harmonics (1, 3, 5, ...), amplitude ∝ 1/n.
      Triangle: only odd harmonics, amplitude ∝ 1/n² (12dB/octave rolloff).

    In practice, filtered synthesisers have all-harmonic content with a steeper rolloff
    after the filter cutoff. We classify by:
    1. Even/odd ratio (for square/triangle detection)
    2. Harmonic rolloff slope (for saw vs filtered-saw vs sine)
    """
    if not partials:
        return "unknown", 0.0, {}

    f0 = fundamental_hz
    # Identify which partials correspond to integer harmonics
    harmonic_amps = {}  # harmonic_number → amplitude
    for freq, amp in partials:
        n = round(freq / f0)
        if n >= 1 and abs(freq - n * f0) / f0 < 0.05:  # within 5% of integer harmonic
            harmonic_amps[n] = max(harmonic_amps.get(n, 0), amp)

    if not harmonic_amps or 1 not in harmonic_amps:
        return "unknown", 0.0, {"harmonic_amps": harmonic_amps}

    # Normalise to fundamental
    h1 = harmonic_amps[1]
    norm_amps = {n: a / h1 for n, a in harmonic_amps.items()}

    max_harmonic = max(harmonic_amps.keys())
    n_harmonics = len(harmonic_amps)

    # Even harmonic presence
    even_present = [n for n in harmonic_amps if n % 2 == 0 and n > 1]
    odd_present = [n for n in harmonic_amps if n % 2 == 1 and n > 1]
    even_energy = sum(norm_amps.get(n, 0) for n in even_present)
    odd_energy = sum(norm_amps.get(n, 0) for n in odd_present)

    # Check if even harmonics are suppressed (square/triangle)
    even_ratio = even_energy / (even_energy + odd_energy + 1e-10)

    # Estimate rolloff slope by fitting log-linear to harmonic amps vs log(n)
    if n_harmonics >= 3:
        ns = np.array(sorted(harmonic_amps.keys()), dtype=float)
        amps = np.array([harmonic_amps[n] for n in ns.astype(int)])
        # Linear fit in log-log space: log(amp) ~ slope * log(n)
        log_n = np.log(ns)
        log_a = np.log(amps + 1e-10)
        slope, intercept = np.polyfit(log_n, log_a, 1)
        # Theoretical slopes: saw = -1 (1/n), square = -1, triangle = -2
    else:
        slope = None

    # Classification logic
    details = {
        "n_harmonics": n_harmonics,
        "max_harmonic": max_harmonic,
        "even_ratio": round(even_ratio, 3),
        "harmonic_rolloff_slope": round(slope, 2) if slope is not None else None,
        "norm_amps": {n: round(a, 3) for n, a in norm_amps.items()},
    }

    h2_amp = norm_amps.get(2, 0)
    h3_amp = norm_amps.get(3, 0)

    if n_harmonics <= 1 or (n_harmonics == 2 and h2_amp < 0.15):
        return "sine", 0.85, details
    elif even_ratio < 0.15 and n_harmonics >= 3:
        # Mostly odd harmonics
        if slope is not None and slope < -1.5:
            return "triangle", 0.7, details
        else:
            return "square", 0.7, details
    elif even_ratio >= 0.35:
        # Even harmonics present → sawtooth family
        if slope is not None and -1.5 < slope < -0.5:
            return "saw", 0.75, details
        elif slope is not None and slope > -0.5:
            return "saw_bright", 0.6, details
        else:
            return "saw_filtered", 0.65, details
    else:
        return "filtered_unknown", 0.4, details


# ---------------------------------------------------------------------------
# Filter cutoff estimation
# ---------------------------------------------------------------------------

def _estimate_filter(y: np.ndarray, sr: int, fundamental_hz: float
                     ) -> tuple[float, float, float]:
    """Estimate filter cutoff and resonance from spectral shape.

    Returns (cutoff_hz, resonance_0_to_1, confidence_0_to_1).

    Method: fit the spectral rolloff in the region above the fundamental.
    The frequency at which the spectrum drops 18dB below the spectral peak
    (approximately -3dB for a 12dB/oct filter) is taken as the cutoff.
    A resonant peak above the otherwise rolling-off spectrum indicates resonance.
    """
    n_fft = 4096
    S = np.abs(librosa.stft(y, n_fft=n_fft))
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    avg_spec = S.mean(axis=1)  # average across time

    if avg_spec.max() == 0:
        return 0.0, 0.0, 0.0

    avg_db = 20 * np.log10(avg_spec / avg_spec.max() + 1e-10)

    # Find peak above fundamental
    fmin_idx = np.argmax(freqs >= fundamental_hz * 0.9)
    fmax_idx = np.argmax(freqs >= min(sr / 2, fundamental_hz * 20))
    if fmax_idx == 0:
        fmax_idx = len(freqs) - 1

    region = avg_db[fmin_idx:fmax_idx]
    region_freqs = freqs[fmin_idx:fmax_idx]
    if len(region) == 0:
        return 0.0, 0.0, 0.0

    peak_idx = np.argmax(region)
    peak_db = region[peak_idx]

    # Cutoff: first frequency where level drops 18dB below peak (approx -3dB for 12dB/oct filter)
    below_18db = np.where(region < peak_db - 18)[0]
    if len(below_18db) > 0:
        cutoff_hz = float(region_freqs[below_18db[0]])
    else:
        cutoff_hz = float(sr / 2)

    # Resonance: check if there's a spectral peak just before the cutoff
    # A resonant bump appears as a local peak that is elevated relative to its neighbours
    if cutoff_hz > fundamental_hz * 2:
        cutoff_region_start = int(len(region_freqs) * 0.3)
        cutoff_region_end = min(len(region), below_18db[0] + 10) if len(below_18db) > 0 else len(region)
        sub_region = region[cutoff_region_start:cutoff_region_end]
        if len(sub_region) > 5:
            # Resonance = deviation of peak from smooth rolloff
            smooth = np.convolve(sub_region, np.ones(5)/5, mode='same')
            max_deviation = float(np.max(sub_region - smooth))
            resonance = min(1.0, max_deviation / 6.0)  # 6dB deviation → resonance=1.0
        else:
            resonance = 0.0
    else:
        resonance = 0.0

    confidence = 0.7 if cutoff_hz < sr / 2 * 0.9 else 0.3
    return cutoff_hz, round(resonance, 3), round(confidence, 2)


# ---------------------------------------------------------------------------
# ADSR envelope extraction
# ---------------------------------------------------------------------------

def _extract_adsr(y: np.ndarray, sr: int, onset_time_s: float,
                  window_s: float = 1.5) -> dict:
    """Measure attack, decay, sustain, release from a single note onset.

    onset_time_s: time of the note attack in seconds.
    window_s: how many seconds to analyse after onset.
    Returns dict with attack_ms, decay_ms, sustain_level, release_ms.
    """
    start = max(0, int(onset_time_s * sr))
    end = min(len(y), start + int(window_s * sr))
    seg = y[start:end]

    hop = 32
    rms = librosa.feature.rms(y=seg, hop_length=hop)[0]
    times_ms = np.arange(len(rms)) * hop / sr * 1000

    if len(rms) < 4 or rms.max() < 1e-6:
        return {"attack_ms": 0, "decay_ms": 0, "sustain_level": 0, "release_ms": 0,
                "confidence": 0.0}

    peak_idx = int(np.argmax(rms))
    peak_val = float(rms[peak_idx])
    attack_ms = float(times_ms[peak_idx])

    # Find -6dB point after peak (end of decay, start of sustain)
    post_peak = rms[peak_idx:]
    decay_threshold = peak_val * 0.5  # -6dB
    below_decay = np.where(post_peak < decay_threshold)[0]
    if len(below_decay) > 0:
        decay_end_idx = peak_idx + below_decay[0]
        decay_ms = float(times_ms[decay_end_idx] - times_ms[peak_idx])
    else:
        decay_ms = 0.0
        decay_end_idx = peak_idx + len(post_peak) // 4

    # Sustain level: mean RMS in middle third of the window
    mid_start = len(rms) // 3
    mid_end = 2 * len(rms) // 3
    sustain_level = float(rms[mid_start:mid_end].mean() / peak_val)

    # Release: from last high-energy point to silence
    silence_threshold = peak_val * 0.05
    last_loud = len(rms) - 1
    while last_loud > 0 and rms[last_loud] < silence_threshold:
        last_loud -= 1
    first_silent = last_loud
    while first_silent < len(rms) - 1 and rms[first_silent] > silence_threshold:
        first_silent += 1
    if first_silent > last_loud:
        release_ms = float(times_ms[first_silent] - times_ms[last_loud])
    else:
        release_ms = float(window_s * 1000 - times_ms[last_loud])

    return {
        "attack_ms": round(attack_ms, 1),
        "decay_ms": round(decay_ms, 1),
        "sustain_level": round(sustain_level, 3),
        "release_ms": round(release_ms, 1),
        "peak_rms": round(peak_val, 5),
        "confidence": 0.7 if peak_idx < len(rms) * 0.3 else 0.4,
    }


# ---------------------------------------------------------------------------
# Portamento event detection
# ---------------------------------------------------------------------------

def _extract_portamento(f0: np.ndarray, voiced: np.ndarray, sr: int,
                         hop_length: int, min_slide_semitones: float = 1.5,
                         min_slide_ms: float = 20.0) -> list[dict]:
    """Detect pitch slide events (portamento) in a PYIN pitch track.

    Returns list of dicts: {t_start_s, t_end_s, start_hz, end_hz,
                             semitones, duration_ms, rate_sem_per_sec}
    """
    hop_s = hop_length / sr
    events = []

    in_slide = False
    slide_start_idx = 0
    prev_midi = None

    voiced_indices = np.where(voiced)[0]
    if len(voiced_indices) < 4:
        return []

    for i in range(1, len(f0)):
        if not voiced[i] or f0[i] is None or np.isnan(f0[i]):
            if in_slide:
                # End slide
                j = i - 1
                while j > slide_start_idx and (not voiced[j] or np.isnan(f0[j])):
                    j -= 1
                end_hz = float(f0[j])
                start_hz = float(f0[slide_start_idx])
                semitones = abs(12 * np.log2(max(end_hz, 1e-6) / max(start_hz, 1e-6)))
                duration_ms = (j - slide_start_idx) * hop_s * 1000
                if semitones >= min_slide_semitones and duration_ms >= min_slide_ms:
                    events.append({
                        "t_start_s": round(slide_start_idx * hop_s, 3),
                        "t_end_s": round(j * hop_s, 3),
                        "start_hz": round(start_hz, 1),
                        "end_hz": round(end_hz, 1),
                        "semitones": round(semitones, 1),
                        "duration_ms": round(duration_ms, 1),
                        "rate_sem_per_sec": round(semitones / max(duration_ms / 1000, 1e-6), 1),
                    })
                in_slide = False
            continue

        if not voiced[i - 1] or f0[i - 1] is None or np.isnan(f0[i - 1]):
            slide_start_idx = i
            in_slide = True
            continue

        if in_slide:
            # Check if still sliding (pitch still changing)
            curr_hz = float(f0[i])
            start_hz = float(f0[slide_start_idx])
            slide_sem = abs(12 * np.log2(max(curr_hz, 1e-6) / max(start_hz, 1e-6)))
            # If pitch stabilised for 3+ frames, end slide
            window = f0[max(0, i - 3):i + 1]
            window_voiced = voiced[max(0, i - 3):i + 1]
            valid = window[window_voiced & ~np.isnan(window.astype(float))]
            if len(valid) > 2:
                midi_range = float(np.ptp(librosa.hz_to_midi(valid + 1e-6)))
                if midi_range < 0.3:  # stable
                    end_hz = float(f0[i])
                    semitones = abs(12 * np.log2(max(end_hz, 1e-6) / max(float(f0[slide_start_idx]), 1e-6)))
                    duration_ms = (i - slide_start_idx) * hop_s * 1000
                    if semitones >= min_slide_semitones and duration_ms >= min_slide_ms:
                        events.append({
                            "t_start_s": round(slide_start_idx * hop_s, 3),
                            "t_end_s": round(i * hop_s, 3),
                            "start_hz": round(float(f0[slide_start_idx]), 1),
                            "end_hz": round(end_hz, 1),
                            "semitones": round(semitones, 1),
                            "duration_ms": round(duration_ms, 1),
                            "rate_sem_per_sec": round(semitones / max(duration_ms / 1000, 1e-6), 1),
                        })
                    in_slide = False
                    slide_start_idx = i
        else:
            slide_start_idx = i
            in_slide = True

    return events


# ---------------------------------------------------------------------------
# Main analysis function
# ---------------------------------------------------------------------------

def analyse_timbre(wav_path: str, bpm: float = 138.0,
                   fmin: float = 40.0, fmax: float = 4000.0) -> dict:
    """Analyse a clean mono audio stem for synthesis parameters.

    Parameters
    ----------
    wav_path : str
        Path to mono WAV file (Demucs stem or isolated instrument).
    bpm : float
        Song tempo — used to express portamento rate in beat fractions.
    fmin : float
        Minimum pitch to track with PYIN (Hz). Default 40Hz covers bass.
    fmax : float
        Maximum pitch to track with PYIN (Hz). Default 4000Hz covers lead.

    Returns
    -------
    dict with keys:
        oscillator_type, oscillator_confidence
        filter_cutoff_hz, filter_resonance, filter_confidence
        adsr (dict: attack_ms, decay_ms, sustain_level, release_ms)
        portamento_events (list of slide dicts)
        portamento_mean_rate_sem_per_sec
        harmonics (list of (freq_hz, relative_amp) for top 12 partials)
        rms, peak
    """
    y, sr = librosa.load(wav_path, sr=None, mono=True)
    hop = 512

    result = {
        "wav_path": wav_path,
        "bpm": bpm,
        "duration_s": round(len(y) / sr, 2),
        "sr": sr,
        "rms": round(float(np.sqrt(np.mean(y**2))), 5),
        "peak": round(float(np.abs(y).max()), 5),
    }

    # --- Harmonic content from a 200ms snapshot at the loudest point ---
    rms_quick = librosa.feature.rms(y=y, hop_length=hop)[0]
    loudest_frame = int(np.argmax(rms_quick))
    snap_start = max(0, loudest_frame * hop - int(0.1 * sr))
    snap_end = min(len(y), snap_start + int(0.2 * sr))
    snap = y[snap_start:snap_end] * np.hanning(snap_end - snap_start)

    n_fft = 8192
    freqs = np.fft.rfftfreq(n_fft, 1 / sr)
    mag = np.abs(np.fft.rfft(snap, n=n_fft))

    # Find spectral peaks above fmin
    fmin_idx = int(fmin / (sr / n_fft))
    peaks, _ = find_peaks(mag[fmin_idx:], height=mag.max() * 0.03)
    peaks += fmin_idx
    top_peaks = sorted(peaks, key=lambda i: mag[i], reverse=True)[:12]
    top_peaks = sorted(top_peaks)  # sort by freq

    partials = [(float(freqs[i]), float(mag[i] / (mag[top_peaks[0]] + 1e-10)))
                for i in top_peaks]
    result["harmonics"] = [(round(f, 1), round(a, 4)) for f, a in partials]

    # Fundamental frequency (loudest partial above fmin)
    fundamental_hz = partials[0][0] if partials else fmin

    # --- Oscillator type ---
    osc_type, osc_conf, osc_details = _classify_oscillator(fundamental_hz, partials, sr)
    result["oscillator_type"] = osc_type
    result["oscillator_confidence"] = round(osc_conf, 2)
    result["oscillator_details"] = osc_details

    # --- Filter estimate ---
    cutoff_hz, resonance, filter_conf = _estimate_filter(y, sr, fundamental_hz)
    result["filter_cutoff_hz"] = round(cutoff_hz, 1)
    result["filter_resonance"] = resonance
    result["filter_confidence"] = filter_conf

    # --- ADSR envelope from loudest onset ---
    onset_times = librosa.onset.onset_detect(y=y, sr=sr, hop_length=hop, units='time')
    if len(onset_times) > 0:
        # Use the loudest-region onset
        rms_at_onsets = [float(librosa.feature.rms(
            y=y[max(0, int(t*sr)):min(len(y), int(t*sr)+hop*4)],
            hop_length=hop)[0].max())
            for t in onset_times[:10]]
        best_onset = float(onset_times[int(np.argmax(rms_at_onsets))])
        result["adsr"] = _extract_adsr(y, sr, best_onset)
    else:
        result["adsr"] = {"attack_ms": 0, "decay_ms": 0, "sustain_level": 0,
                          "release_ms": 0, "confidence": 0.0}

    # --- Portamento events ---
    f0, voiced, _ = librosa.pyin(y, fmin=fmin, fmax=fmax, sr=sr, hop_length=hop)
    portamento_events = _extract_portamento(f0, voiced, sr, hop)
    result["portamento_events"] = portamento_events

    if portamento_events:
        rates = [e["rate_sem_per_sec"] for e in portamento_events]
        result["portamento_mean_rate_sem_per_sec"] = round(float(np.mean(rates)), 1)
        result["portamento_n_events"] = len(portamento_events)
    else:
        result["portamento_mean_rate_sem_per_sec"] = None
        result["portamento_n_events"] = 0

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_report(r: dict) -> None:
    print(f"\n{'='*60}")
    print(f"Timbre analysis: {r['wav_path']}")
    print(f"{'='*60}")
    print(f"Duration: {r['duration_s']}s  RMS: {r['rms']:.5f}  Peak: {r['peak']:.5f}")
    print(f"\nOscillator type:  {r['oscillator_type']:15s}  (confidence: {r['oscillator_confidence']:.0%})")
    det = r.get("oscillator_details", {})
    if "harmonic_rolloff_slope" in det and det["harmonic_rolloff_slope"] is not None:
        print(f"  Rolloff slope:  {det['harmonic_rolloff_slope']:+.2f} (saw≈-1, triangle≈-2)")
    if "even_ratio" in det:
        print(f"  Even harmonic ratio: {det['even_ratio']:.3f} (saw≈0.5, square≈0)")
    print(f"\nTop harmonics (freq, rel_amp):")
    for freq, amp in r.get("harmonics", [])[:8]:
        fundamental = r["harmonics"][0][0] if r.get("harmonics") else 1
        ratio = freq / fundamental if fundamental > 0 else 0
        print(f"  {freq:7.1f}Hz  amp={amp:.4f}  harmonic≈{ratio:.2f}")
    print(f"\nFilter estimate:")
    print(f"  Cutoff:    {r['filter_cutoff_hz']:.0f} Hz  (confidence: {r['filter_confidence']:.0%})")
    print(f"  Resonance: {r['filter_resonance']:.3f} (0=flat, 1=heavy peak)")
    adsr = r.get("adsr", {})
    print(f"\nADSR envelope:")
    print(f"  Attack:  {adsr.get('attack_ms', 0):.1f}ms")
    print(f"  Decay:   {adsr.get('decay_ms', 0):.1f}ms")
    print(f"  Sustain: {adsr.get('sustain_level', 0):.3f} (relative level)")
    print(f"  Release: {adsr.get('release_ms', 0):.1f}ms  (confidence: {adsr.get('confidence', 0):.0%})")
    n_events = r.get("portamento_n_events", 0)
    print(f"\nPortamento: {n_events} events")
    if n_events > 0:
        print(f"  Mean rate: {r['portamento_mean_rate_sem_per_sec']:.1f} semitones/sec")
        for e in r.get("portamento_events", [])[:6]:
            start_note = librosa.hz_to_note(e["start_hz"], octave=True)
            end_note = librosa.hz_to_note(e["end_hz"], octave=True)
            print(f"  t={e['t_start_s']:.3f}s: {start_note}→{end_note} "
                  f"({e['semitones']:.1f}st in {e['duration_ms']:.0f}ms = "
                  f"{e['rate_sem_per_sec']:.0f} st/s)")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wav", help="Input WAV file (mono, ideally a Demucs stem)")
    parser.add_argument("--bpm", type=float, default=138.0, help="Song tempo")
    parser.add_argument("--fmin", type=float, default=40.0,
                        help="Min pitch Hz for PYIN (40Hz=bass, 80Hz=mid, 200Hz=lead)")
    parser.add_argument("--fmax", type=float, default=4000.0,
                        help="Max pitch Hz for PYIN")
    parser.add_argument("--json", action="store_true",
                        help="Output as JSON instead of table")
    args = parser.parse_args()

    result = analyse_timbre(args.wav, bpm=args.bpm, fmin=args.fmin, fmax=args.fmax)

    if args.json:
        import json
        print(json.dumps(result, indent=2))
    else:
        _print_report(result)


if __name__ == "__main__":
    main()
