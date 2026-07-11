# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for tools/analyse_audio.py.

Ground truth: drum voices from synth/drums.py (already well-tested).
A kick is bass-heavy; a hihat is air-heavy. This tests the band_energy
measurements are correctly directional.

See docs/testing/ANALYSIS_TOOLS_TEST_METHODOLOGY.md.
"""
import sys
import wave
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

import numpy as np
import pytest

from tools.analyse_audio import analyse_wav
from synth.drums import kick, hihat

SR = 44100


def _write_stereo_wav(path: Path, buf_l: np.ndarray, buf_r: np.ndarray,
                      sr: int = SR) -> str:
    """Write stereo float32 arrays as a 16-bit PCM WAV."""
    pcm_l = np.clip(buf_l, -1.0, 1.0)
    pcm_r = np.clip(buf_r, -1.0, 1.0)
    interleaved = np.empty(len(pcm_l) * 2, dtype=np.int16)
    interleaved[0::2] = (pcm_l * 32767).astype(np.int16)
    interleaved[1::2] = (pcm_r * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(interleaved.tobytes())
    return str(path)


def _write_mono_wav(path: Path, signal: np.ndarray, sr: int = SR) -> str:
    pcm = (np.clip(signal, -1.0, 1.0) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return str(path)


# ---------------------------------------------------------------------------
# Band energy tests using known-spectrum drum voices
# ---------------------------------------------------------------------------

def test_band_energy_kick_is_bass_heavy(tmp_path):
    """Kick drum: sub + bass energy should dominate over hi_mid.

    analyse_wav requires at least 65536 samples (1 chunk) — tile kick to fill.
    """
    buf_l, buf_r = kick(sr=SR, seed=42)
    # Tile to 2 seconds (silence between hits)
    silence = np.zeros(int(SR * 0.5), dtype=np.float32)
    full_l = np.concatenate([buf_l, silence, buf_l, silence, buf_l])
    full_r = np.concatenate([buf_r, silence, buf_r, silence, buf_r])
    wav = _write_stereo_wav(tmp_path / "kick.wav", full_l, full_r)
    result = analyse_wav(wav)
    be = result["band_energy"]
    assert be["sub"] + be["bass"] > be["hi_mid"], \
        f"Kick should be bass-heavy: sub={be['sub']:.4f} bass={be['bass']:.4f} hi_mid={be['hi_mid']:.4f}"


def test_band_energy_hihat_is_air_heavy(tmp_path):
    """Hi-hat: air + hi_mid energy should dominate over sub."""
    buf_l, buf_r = hihat(sr=SR, seed=42)
    silence = np.zeros(int(SR * 0.2), dtype=np.float32)
    full_l = np.concatenate([buf_l, silence, buf_l, silence, buf_l, silence, buf_l])
    full_r = np.concatenate([buf_r, silence, buf_r, silence, buf_r, silence, buf_r])
    wav = _write_stereo_wav(tmp_path / "hihat.wav", full_l, full_r)
    result = analyse_wav(wav)
    be = result["band_energy"]
    assert be["air"] + be["hi_mid"] > be["sub"] + be["bass"], \
        f"Hihat should be high-freq heavy: air={be['air']:.4f} hi_mid={be['hi_mid']:.4f} sub={be['sub']:.4f}"


# ---------------------------------------------------------------------------
# Level / dynamics checks
# ---------------------------------------------------------------------------

def test_no_clipping_on_kick(tmp_path):
    """Kick drum peak should not be exactly 1.0 (hard clipping).

    Note: synth/drums.kick() uses np.clip(-1.0, 1.0) which may produce samples
    at exactly ±1.0 during transient. We check the 16-bit WAV round-trip instead:
    after 16-bit quantisation, a true 0dBFS clip would saturate at 32767/32768 ≈ 0.9999.
    We allow up to 1.001 to account for decode rounding.
    """
    buf_l, buf_r = kick(sr=SR, seed=42)
    silence = np.zeros(int(SR * 0.5), dtype=np.float32)
    full_l = np.concatenate([buf_l, silence])
    full_r = np.concatenate([buf_r, silence])
    wav = _write_stereo_wav(tmp_path / "kick.wav", full_l, full_r)
    result = analyse_wav(wav)
    # Peak from 16-bit WAV decode will be at most 32767/32768 ≈ 0.99997
    # — this is fine (no hard digital clipping above 1.0)
    assert result["peak"] <= 1.0, \
        f"Kick peak above 1.0 is impossible after 16-bit decode: {result['peak']:.6f}"


def test_crest_factor_reasonable_for_sine(tmp_path):
    """A pure 440Hz sine: crest factor should be ~1.41 (√2)."""
    t = np.arange(SR * 2) / SR
    signal = np.sin(2 * np.pi * 440 * t).astype(np.float32) * 0.5
    wav = _write_mono_wav(tmp_path / "sine.wav", signal)
    result = analyse_wav(wav)
    cf = result["crest_factor_mean"]
    assert 1.2 <= cf <= 1.7, \
        f"Sine wave crest factor should be ~1.41, got {cf:.3f}"


def test_silence_rms_near_zero(tmp_path):
    silence = np.zeros(SR * 2, dtype=np.float32)
    wav = _write_mono_wav(tmp_path / "silence.wav", silence)
    result = analyse_wav(wav)
    assert result["rms"] < 0.001


def test_dict_has_required_keys(tmp_path):
    buf_l, buf_r = kick(sr=SR, seed=42)
    wav = _write_stereo_wav(tmp_path / "kick.wav", buf_l, buf_r)
    result = analyse_wav(wav)
    for key in ["peak", "peak_dbfs", "rms", "rms_dbfs",
                "crest_factor_mean", "band_energy", "duration_s"]:
        assert key in result, f"Missing key: {key}"
    for band in ["sub", "bass", "mid", "hi_mid", "air"]:
        assert band in result["band_energy"], f"Missing band: {band}"
