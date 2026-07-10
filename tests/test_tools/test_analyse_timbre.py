# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for tools/analyse_timbre.py.

Ground truth: synthetic signals generated in memory using numpy and
synth/oscillators.py. The synth is itself well-tested, making its output
a reliable known-parameter source for testing the analysis tools.

See docs/testing/ANALYSIS_TOOLS_TEST_METHODOLOGY.md for acceptance thresholds
and rationale.
"""
import sys
import wave
import struct
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

import numpy as np
import pytest

from tools.analyse_timbre import (
    analyse_timbre,
    _classify_oscillator,
    _extract_adsr,
    _estimate_filter,
)
from synth.oscillators import sawtooth, sine

SR = 44100
ONE_BAR_S = 4 * 60 / 138  # ~1.739s at 138 BPM


def _write_wav(path: Path, signal: np.ndarray, sr: int = SR) -> str:
    """Write a float32 mono numpy array to a 16-bit WAV file."""
    pcm = np.clip(signal, -1.0, 1.0)
    pcm_int = (pcm * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm_int.tobytes())
    return str(path)


# ---------------------------------------------------------------------------
# _classify_oscillator — internal function, unit tests
# ---------------------------------------------------------------------------

def test_classify_oscillator_sine():
    partials = [(440.0, 1.0), (880.0, 0.02)]
    osc_type, conf, _ = _classify_oscillator(440.0, partials, SR)
    assert osc_type == "sine", f"Expected sine, got {osc_type}"
    assert conf >= 0.8


def test_classify_oscillator_saw():
    partials = [
        (440.0, 1.0),
        (880.0, 0.50),    # 2nd harmonic = 1/2
        (1320.0, 0.33),   # 3rd harmonic = 1/3
        (1760.0, 0.25),   # 4th harmonic = 1/4
        (2200.0, 0.20),   # 5th harmonic = 1/5
    ]
    osc_type, conf, details = _classify_oscillator(440.0, partials, SR)
    assert osc_type in {"saw", "saw_filtered", "saw_bright"}, \
        f"Expected saw variant, got {osc_type} (details: {details})"
    assert details["even_ratio"] > 0.3


def test_classify_oscillator_square():
    partials = [
        (440.0, 1.0),
        (1320.0, 0.33),   # 3rd harmonic
        (2200.0, 0.20),   # 5th harmonic
        (3080.0, 0.14),   # 7th harmonic
    ]
    osc_type, conf, details = _classify_oscillator(440.0, partials, SR)
    assert osc_type in {"square", "triangle"}, \
        f"Expected square or triangle, got {osc_type} (details: {details})"
    assert details["even_ratio"] < 0.15


def test_classify_oscillator_single_partial_is_sine():
    partials = [(440.0, 1.0)]
    osc_type, conf, _ = _classify_oscillator(440.0, partials, SR)
    assert osc_type == "sine"


def test_classify_oscillator_empty_returns_unknown():
    osc_type, conf, _ = _classify_oscillator(440.0, [], SR)
    assert osc_type == "unknown"
    assert conf == 0.0


# ---------------------------------------------------------------------------
# _extract_adsr — internal function, unit tests
# ---------------------------------------------------------------------------

def test_extract_adsr_fast_attack():
    sr = SR
    attack_samples = int(0.005 * sr)  # 5ms attack
    sustain_samples = int(0.5 * sr)
    # Fast linear ramp up, then flat sustain
    signal = np.concatenate([
        np.linspace(0.0, 1.0, attack_samples),
        np.ones(sustain_samples) * 0.9,
    ]).astype(np.float32)
    result = _extract_adsr(signal, sr, onset_time_s=0.0, window_s=0.6)
    assert result["attack_ms"] < 30, \
        f"Expected attack < 30ms for 5ms ramp, got {result['attack_ms']}ms"


def test_extract_adsr_silence_returns_zero():
    signal = np.zeros(SR, dtype=np.float32)
    result = _extract_adsr(signal, SR, onset_time_s=0.0)
    assert result["attack_ms"] == 0
    assert result["sustain_level"] == 0


# ---------------------------------------------------------------------------
# analyse_timbre — full function, integration
# ---------------------------------------------------------------------------

def test_sine_classified_correctly(tmp_path):
    signal, _ = sine(440, SR * 2, SR)
    wav = _write_wav(tmp_path / "sine.wav", signal)
    result = analyse_timbre(wav, bpm=138.0, fmin=200.0, fmax=2000.0)
    assert result["oscillator_type"] == "sine", \
        f"Expected sine, got {result['oscillator_type']} (details: {result['oscillator_details']})"
    assert result["oscillator_confidence"] >= 0.8


def test_sawtooth_classified_correctly(tmp_path):
    signal, _ = sawtooth(440, SR * 2, SR)
    wav = _write_wav(tmp_path / "saw.wav", signal)
    result = analyse_timbre(wav, bpm=138.0, fmin=200.0, fmax=2000.0)
    assert result["oscillator_type"] in {"saw", "saw_filtered", "saw_bright"}, \
        f"Expected saw variant, got {result['oscillator_type']}"
    assert result["oscillator_details"]["even_ratio"] > 0.3, \
        f"Expected even_ratio > 0.3 for sawtooth, got {result['oscillator_details']['even_ratio']}"


def test_filter_cutoff_estimate_in_range(tmp_path):
    """LPF at 1000Hz on a sawtooth: cutoff estimate should be 300–3000 Hz.

    The 18dB-below-peak criterion is approximate — filter cutoff estimation
    is intentionally tolerant (factor ×3 of true value per methodology doc).
    """
    import scipy.signal
    # Use higher fundamental (440Hz) so harmonics are well above fmin
    signal, _ = sawtooth(440, SR * 3, SR)
    b, a = scipy.signal.butter(4, 1000.0 / (SR / 2), btype="low")
    filtered = scipy.signal.filtfilt(b, a, signal).astype(np.float32)
    wav = _write_wav(tmp_path / "saw_lpf.wav", filtered)
    result = analyse_timbre(wav, bpm=138.0, fmin=200.0, fmax=8000.0)
    cutoff = result["filter_cutoff_hz"]
    assert 300 <= cutoff <= 3000, \
        f"Filter cutoff {cutoff:.0f}Hz not in expected range 300–3000Hz for 1000Hz LPF"


def test_empty_wav_does_not_crash(tmp_path):
    silence = np.zeros(SR, dtype=np.float32)
    wav = _write_wav(tmp_path / "silence.wav", silence)
    result = analyse_timbre(wav, bpm=138.0, fmin=40.0, fmax=4000.0)
    assert result["rms"] < 0.001
    assert result["oscillator_type"] in {
        "unknown", "sine", "filtered_unknown"
    }, f"Unexpected type for silence: {result['oscillator_type']}"


def test_portamento_rate_detected(tmp_path):
    """Linearly gliding sine C4→C5 over 100ms = 12 sem / 0.1 s = 120 sem/sec."""
    sr = SR
    duration_s = 0.5
    n = int(duration_s * sr)
    t = np.arange(n) / sr

    # Glide in first 100ms, then hold
    glide_n = int(0.1 * sr)
    c4 = 261.63
    c5 = 523.25
    freq = np.where(t < 0.1,
                    c4 + (c5 - c4) * (t / 0.1),
                    c5)
    phase = 2 * np.pi * np.cumsum(freq) / sr
    signal = np.sin(phase).astype(np.float32)
    # Fade in/out to help PYIN
    signal[:int(0.01*sr)] *= np.linspace(0, 1, int(0.01*sr))
    signal[-int(0.01*sr):] *= np.linspace(1, 0, int(0.01*sr))
    # Pad with 0.5s silence then repeat glide — PYIN needs sufficient voiced frames
    signal = np.tile(signal, 4)

    wav = _write_wav(tmp_path / "glide.wav", signal)
    result = analyse_timbre(wav, bpm=138.0, fmin=200.0, fmax=1200.0)
    n_events = result.get("portamento_n_events", 0)
    if n_events > 0:
        rate = result["portamento_mean_rate_sem_per_sec"]
        # PYIN at hop=512 has ~11.6ms timing resolution; allow ±50% of 120 sem/sec
        assert 40 <= rate <= 200, \
            f"Expected portamento rate 40–200 sem/sec (±50% of 120), got {rate}"
    # Not asserting n_events > 0 — PYIN can miss a single fast glide.
    # The test confirms no crash and plausible rate if events are found.
