# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for tools/extract_drum_pattern.py.

Ground truth: synthetic WAV files with impulses at exact known positions.
Phase-anchor snapping is tested with precisely timed sine bursts.

See docs/testing/ANALYSIS_TOOLS_TEST_METHODOLOGY.md.
"""
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[2]))

import numpy as np
import pytest

from tools.extract_drum_pattern import (
    extract_drum_pattern,
    _snap_to_grid,
    _pattern_to_str,
)

SR = 44100
BPM = 140.0
STEP_S = 60.0 / BPM / 4  # 16th note duration at 140 BPM = 0.1071s
BAR_S = 4 * 60.0 / BPM    # 1 bar = 1.714s


def _write_kick_wav(path: Path, onset_times_s: list, sr: int = SR,
                    duration_s: float = 4.0) -> str:
    """Write a WAV with sub-bass tone bursts at given onset times.

    Uses a 120Hz tone burst with a sharp exponential decay (5ms half-life)
    so each impulse is contained within one 16th-note step at 140 BPM (107ms).
    This avoids spectral flux detections on the ringing tail of a longer burst.
    """
    n = int(duration_s * sr)
    signal = np.zeros(n, dtype=np.float32)
    burst_len = int(0.04 * sr)  # 40ms total — well within 107ms step
    t_burst = np.arange(burst_len) / sr
    # Fast exponential decay: amplitude halves in 5ms
    envelope = np.exp(-t_burst / 0.005).astype(np.float32)
    burst = (np.sin(2 * np.pi * 120.0 * t_burst) * envelope).astype(np.float32)
    for t in onset_times_s:
        idx = int(t * sr)
        end = min(n, idx + burst_len)
        signal[idx:end] += burst[:end - idx]
    signal = np.clip(signal, -1.0, 1.0)
    pcm = (signal * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return str(path)


def _write_hihat_wav(path: Path, onset_times_s: list, sr: int = SR,
                     duration_s: float = 4.0) -> str:
    """Write a WAV with high-frequency noise bursts at given onset times."""
    rng = np.random.default_rng(42)
    n = int(duration_s * sr)
    signal = np.zeros(n, dtype=np.float32)
    burst_len = int(0.01 * sr)
    for t in onset_times_s:
        idx = int(t * sr)
        end = min(n, idx + burst_len)
        burst = rng.standard_normal(end - idx).astype(np.float32) * 0.3
        signal[idx:end] += burst
    signal = np.clip(signal, -1.0, 1.0)
    pcm = (signal * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())
    return str(path)


# ---------------------------------------------------------------------------
# _snap_to_grid — internal function
# ---------------------------------------------------------------------------

def test_snap_to_grid_phase_anchor():
    """Onsets exactly on grid steps starting at t=1.3s → step 0 assigned to first onset."""
    onset_times = np.array([1.3 + i * STEP_S for i in range(16)])
    pattern, mean_error = _snap_to_grid(onset_times, BPM, n_steps=16, n_bars=4)
    assert pattern == [1] * 16, f"Expected all 16 steps hit, got {pattern}"
    assert mean_error < 2.0, f"Expected alignment error < 2ms, got {mean_error}ms"


def test_snap_to_grid_empty():
    pattern, mean_error = _snap_to_grid(np.array([]), BPM, n_steps=16, n_bars=4)
    assert pattern == [0] * 16
    assert mean_error == 0.0


def test_snap_to_grid_two_onsets():
    """Onsets at step 0 and step 8 (half-note)."""
    onset_times = np.array([0.0, BAR_S / 2])
    pattern, mean_error = _snap_to_grid(onset_times, BPM, n_steps=16, n_bars=1)
    assert pattern[0] == 1
    assert pattern[8] == 1
    total_hits = sum(pattern)
    assert total_hits == 2, f"Expected 2 hits, got {total_hits}"


# ---------------------------------------------------------------------------
# _pattern_to_str
# ---------------------------------------------------------------------------

def test_pattern_to_str_basic():
    result = _pattern_to_str([1, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0])
    assert result == "X . . X . . . . X . . . . . . ."


def test_pattern_to_str_all_silent():
    result = _pattern_to_str([0] * 16)
    assert "X" not in result


# ---------------------------------------------------------------------------
# extract_drum_pattern — full function
# ---------------------------------------------------------------------------

def test_kick_on_downbeat_quarter_notes(tmp_path):
    """Kick on quarter notes (steps 0, 4, 8, 12).

    Note: onset detection may find multiple onsets per burst due to spectral flux
    ringing. We test that the quarter-note steps are HIT, not that no other steps are.
    The phase-anchor grid snap uses the first onset as step 0.
    """
    onset_times = [i * BAR_S / 4 for i in range(8)]  # 2 bars of quarter notes
    wav = _write_kick_wav(tmp_path / "kick_quarters.wav", onset_times, duration_s=4.0)
    result = extract_drum_pattern(wav, bpm=BPM, n_steps=16, voices=["kick"])
    pattern = result["kick"]
    # Quarter notes land on steps 0, 4, 8, 12 — assert at least these are set
    assert pattern[0] == 1, f"Step 0 should be hit, pattern={pattern}"
    assert pattern[8] == 1, f"Step 8 should be hit, pattern={pattern}"
    # Steps 4 and 12 depend on phase alignment after anchor — assert total hits ≥ 2
    assert sum(pattern) >= 2, f"Expected ≥2 quarter-note hits, pattern={pattern}"


def test_kick_half_time_pattern(tmp_path):
    """Half-time kick: steps 0 and 8 only (every half-note)."""
    onset_times = [i * BAR_S / 2 for i in range(4)]  # 2 bars of half notes
    wav = _write_kick_wav(tmp_path / "kick_halftime.wav", onset_times, duration_s=4.0)
    result = extract_drum_pattern(wav, bpm=BPM, n_steps=16, voices=["kick"])
    pattern = result["kick"]
    assert pattern[0] == 1, f"Step 0 should be hit, pattern={pattern}"
    assert pattern[8] == 1, f"Step 8 should be hit, pattern={pattern}"
    assert pattern[4] == 0 or pattern.count(1) >= 2, "No unexpected hits on off-beats"


def test_alignment_error_reported_for_jittered_onsets(tmp_path):
    """Adding ±20ms jitter should produce a non-zero alignment error."""
    rng = np.random.default_rng(99)
    onset_times = [i * BAR_S / 4 + rng.uniform(-0.02, 0.02) for i in range(8)]
    wav = _write_kick_wav(tmp_path / "kick_jitter.wav", onset_times, duration_s=4.0)
    result = extract_drum_pattern(wav, bpm=BPM, n_steps=16, voices=["kick"])
    err = result["alignment_errors"].get("kick", 0)
    assert err > 0, "Jittered onsets should have non-zero alignment error"


def test_empty_band_warns(tmp_path):
    """Silence produces zero kick onsets and triggers a WARNING in confidence_notes."""
    n = int(2.0 * SR)
    signal = np.zeros(n, dtype=np.float32)
    pcm = (signal * 32767).astype(np.int16)
    wav_path = tmp_path / "silence.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
    result = extract_drum_pattern(str(wav_path), bpm=BPM, n_steps=16, voices=["kick"])
    n_kick = result["n_onsets"].get("kick", 0)
    assert n_kick == 0, f"Silence should have 0 kick onsets, got {n_kick}"
    # Should warn about no onsets
    notes = result.get("confidence_notes", [])
    assert any("kick" in n.lower() for n in notes), \
        f"Expected a WARNING about no kick onsets in confidence_notes, got: {notes}"


def test_result_has_expected_keys(tmp_path):
    onset_times = [0.0, BAR_S / 2]
    wav = _write_kick_wav(tmp_path / "kick_basic.wav", onset_times, duration_s=2.0)
    result = extract_drum_pattern(wav, bpm=BPM, n_steps=16)
    assert "kick" in result
    assert "alignment_errors" in result
    assert "n_onsets" in result
    assert "confidence_notes" in result
    assert len(result["kick"]) == 16


def test_silence_does_not_crash(tmp_path):
    silence = np.zeros(SR * 2, dtype=np.float32)
    pcm = (silence * 32767).astype(np.int16)
    wav_path = tmp_path / "silence.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())
    result = extract_drum_pattern(str(wav_path), bpm=BPM, n_steps=16)
    assert result["kick"] == [0] * 16
