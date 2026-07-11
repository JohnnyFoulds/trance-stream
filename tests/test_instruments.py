# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Instrument-level unit tests for trance_stream_v3 (Phase 7).

Renders each instrument in isolation and asserts spectral and dynamic
properties.  No audio hardware, no file I/O except reading
research/reference_audio/targets.json.
"""

from __future__ import annotations

import sys
import pathlib
import json

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

REPO_ROOT = pathlib.Path(__file__).parent.parent
SR = 44100
BPM = 140.0
SPB = int(SR * 4 * 60 / BPM)   # 75600 samples per bar


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def rms(buf: np.ndarray) -> float:
    return float(np.sqrt((buf.astype(np.float64) ** 2).mean()))


def spectral_centroid(buf: np.ndarray, sr: int = SR) -> float:
    """Power-weighted spectral centroid in Hz."""
    spec = np.abs(np.fft.rfft(buf * np.hanning(len(buf))))
    freqs = np.fft.rfftfreq(len(buf), 1.0 / sr)
    power = spec ** 2
    denom = power.sum()
    return float((freqs * power).sum() / denom) if denom > 0 else 0.0


def band_energy_ratio(buf: np.ndarray, lo_hz: float, hi_hz: float,
                      sr: int = SR) -> float:
    """Fraction of total energy in [lo_hz, hi_hz)."""
    spec = np.abs(np.fft.rfft(buf * np.hanning(len(buf))))
    freqs = np.fft.rfftfreq(len(buf), 1.0 / sr)
    mask = (freqs >= lo_hz) & (freqs < hi_hz)
    total = (spec ** 2).sum()
    band = (spec[mask] ** 2).sum()
    return float(band / total) if total > 0 else 0.0


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def targets():
    """Load research/reference_audio/targets.json once per session."""
    path = REPO_ROOT / "research" / "reference_audio" / "targets.json"
    with path.open() as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# SupersawPad tests
# ---------------------------------------------------------------------------

def test_pad_not_silent():
    """Pad with open filter must produce audible output."""
    from instruments.pad import SupersawPad

    pad = SupersawPad(root_midi=55)
    l, r = pad.render([60, 62, 63, 65], SPB, cutoff_slider=0.877)
    assert rms(l) > 0.001, f"Pad is silent: rms={rms(l)}"


def test_pad_open_filter_higher_centroid_than_closed():
    """Opening the filter must raise spectral centroid."""
    from instruments.pad import SupersawPad

    pad_closed = SupersawPad(root_midi=55)
    pad_open   = SupersawPad(root_midi=55)
    l_closed, _ = pad_closed.render([60], SPB, cutoff_slider=0.35)
    l_open,   _ = pad_open.render([60],   SPB, cutoff_slider=0.877)
    c_closed = spectral_centroid(l_closed)
    c_open   = spectral_centroid(l_open)
    assert c_open > c_closed * 1.3, (
        f"Open centroid {c_open:.0f} Hz not > 1.3× closed {c_closed:.0f} Hz"
    )


def test_pad_trancegate_creates_rms_variation():
    """Trancegate at 1.5× bar rate should cause >2× variation in per-16th RMS."""
    from instruments.pad import SupersawPad

    sp16 = SPB // 16
    pad = SupersawPad(root_midi=55)
    l, _ = pad.render([60], SPB * 2, cutoff_slider=0.65)   # 2 bars
    rms_steps = [rms(l[i * sp16:(i + 1) * sp16]) for i in range(32)]
    rms_steps = [r for r in rms_steps if r > 1e-6]
    assert rms_steps, "Pad produced all-zero output — trancegate or synthesis is broken"
    ratio = max(rms_steps) / min(rms_steps)
    assert ratio > 2.0, f"Trancegate RMS variation ratio {ratio:.2f} < 2.0"


def test_pad_stereo_outputs_differ():
    """Left and right channels should differ (stereo detuning from supersaw)."""
    from instruments.pad import SupersawPad

    pad = SupersawPad(root_midi=55)
    l, r = pad.render([60, 63], SPB, cutoff_slider=0.65)
    # FDN reverb and supersaw panning must produce distinct L/R content.
    assert not np.array_equal(l, r), "Pad L and R channels are identical"


def test_pad_voicing_offsets_add_low_energy():
    """PAD_VOICING_OFFSETS (-14, -21) must add energy in sub-bass (<100 Hz)."""
    from instruments.pad import SupersawPad

    # Single note with voicing produces lows via -14/-21 semitone doublings.
    pad = SupersawPad(root_midi=55)
    l, _ = pad.render([60], SPB, cutoff_slider=0.877)
    sub_ratio = band_energy_ratio(l, 20, 100)
    # VOICING_GAINS=[1.0,0.35,0.15], total_weight=1.5 → -21 semitone voice is
    # 10% amplitude. band_energy_ratio applies a Hanning window which reduces
    # sub-bass power significantly; measured ratio is ~0.0023 when working.
    # Threshold set to 0.001 — strictly above zero but well below measured value,
    # so a missing/broken -21 semitone voice (ratio=0.0) fails cleanly.
    assert sub_ratio > 0.001, (
        f"Sub-bass ratio {sub_ratio:.4f} unexpectedly low — voicing offsets may be broken"
    )


# ---------------------------------------------------------------------------
# DrumKit tests
# ---------------------------------------------------------------------------

def test_kick_peak_level():
    """Kick peak should be > 0.7 (strong transient)."""
    from instruments.drums import DrumKit

    kit = DrumKit(seed=42)
    l, r = kit.render_kick(gain=1.0)
    assert abs(l).max() > 0.7, f"Kick peak {abs(l).max():.3f} < 0.7"


def test_kick_bass_dominant():
    """Kick should have most energy in bass band (<300 Hz)."""
    from instruments.drums import DrumKit

    kit = DrumKit(seed=42)
    l, _ = kit.render_kick(gain=1.0)
    bass_ratio = band_energy_ratio(l, 20, 300)
    assert bass_ratio > 0.4, f"Kick bass energy {bass_ratio:.2%} < 40%"


def test_hihat_air_dominant():
    """Hihat should have most energy above 4 kHz."""
    from instruments.drums import DrumKit

    kit = DrumKit(seed=42)
    l, _ = kit.render_hihat(gain=1.0)
    air_ratio = band_energy_ratio(l, 4000, 22050)
    assert air_ratio > 0.5, f"Hihat air energy {air_ratio:.2%} < 50%"


def test_drums_deterministic():
    """Same seed must produce identical output."""
    from instruments.drums import DrumKit

    kit1 = DrumKit(seed=42)
    kit2 = DrumKit(seed=42)
    l1, _ = kit1.render_kick()
    l2, _ = kit2.render_kick()
    assert np.array_equal(l1, l2), "Kick output differs with same seed"


def test_drums_different_seeds_differ():
    """Different seeds must produce different output."""
    from instruments.drums import DrumKit

    kit_a = DrumKit(seed=0)
    kit_b = DrumKit(seed=99)
    la, _ = kit_a.render_kick()
    lb, _ = kit_b.render_kick()
    assert not np.array_equal(la, lb), "Kicks with different seeds are identical"


def test_clap_not_silent():
    """Clap hit must produce non-trivial output."""
    from instruments.drums import DrumKit

    kit = DrumKit(seed=42)
    l, _ = kit.render_clap(gain=1.0)
    assert rms(l) > 0.001, f"Clap is silent: rms={rms(l):.6f}"


def test_kick_length_positive():
    """kick_length() must report a positive sample count."""
    from instruments.drums import DrumKit

    kit = DrumKit(seed=42)
    assert kit.kick_length() > 0, "kick_length() returned 0"


def test_hihat_length_shorter_with_shorter_decay():
    """Shorter decay_s should yield a shorter hihat buffer."""
    from instruments.drums import DrumKit

    kit = DrumKit(seed=42)
    l_long,  _ = kit.render_hihat(decay_s=0.12, gain=1.0)
    l_short, _ = kit.render_hihat(decay_s=0.05, gain=1.0)
    assert len(l_short) < len(l_long), (
        f"Short decay ({len(l_short)}) not shorter than long decay ({len(l_long)})"
    )


# ---------------------------------------------------------------------------
# AcidLead tests
# ---------------------------------------------------------------------------

def test_lead_not_silent():
    """Lead must produce audible output for a single note."""
    from instruments.lead import AcidLead

    lead = AcidLead(root_midi=55)
    l, _ = lead.render([60], SPB)
    assert rms(l) > 0.0001, f"Lead is silent: rms={rms(l)}"


def test_lead_fm_raises_sub_harmonic_energy():
    """FM (ratio 1:2) adds sub-harmonic warmth in the 100–800 Hz band.

    SA's fm .5 uses modulator at 0.5× carrier. For C4 (261 Hz) the sidebands
    land at ~130 Hz, ~392 Hz, ~653 Hz — all in the 100–800 Hz band.
    This is warm enrichment, not the reed-timbre 2k–8k energy from ratio 4:1.
    """
    from instruments.lead import AcidLead

    lead_no_fm   = AcidLead(root_midi=55)
    lead_with_fm = AcidLead(root_midi=55)
    l_no,   _ = lead_no_fm.render([60],   SPB, fm_depth=0.0)
    l_with, _ = lead_with_fm.render([60], SPB, fm_depth=0.55)
    lo_no   = band_energy_ratio(l_no,   100, 800)
    lo_with = band_energy_ratio(l_with, 100, 800)
    assert lo_with > lo_no * 1.01, (
        f"FM (ratio 1:2) should raise 100–800 Hz sub-harmonic energy by >1%: "
        f"no_fm={lo_no:.4f} with_fm={lo_with:.4f}"
    )


def test_lead_stereo_pair_same_length():
    """render() must return L and R buffers of equal length."""
    from instruments.lead import AcidLead

    lead = AcidLead(root_midi=55)
    l, r = lead.render([60, 63], SPB)
    assert len(l) == len(r) == SPB, (
        f"Buffer length mismatch: l={len(l)}, r={len(r)}, expected={SPB}"
    )


def test_lead_empty_notes_returns_silence():
    """Empty midi_notes list must return zero-filled buffers."""
    from instruments.lead import AcidLead

    lead = AcidLead(root_midi=55)
    l, r = lead.render([], SPB)
    assert rms(l) == 0.0 and rms(r) == 0.0, (
        f"Expected silence for empty notes; rms_l={rms(l)}, rms_r={rms(r)}"
    )


def test_lead_output_dtype_float32():
    """render() must return float32 arrays (not float64)."""
    from instruments.lead import AcidLead

    lead = AcidLead(root_midi=55)
    l, r = lead.render([60], SPB)
    assert l.dtype == np.float32, f"Lead L dtype is {l.dtype}, expected float32"
    assert r.dtype == np.float32, f"Lead R dtype is {r.dtype}, expected float32"


# ---------------------------------------------------------------------------
# Aggregate / cross-instrument tests using targets.json
# ---------------------------------------------------------------------------

def test_targets_json_is_loadable(targets):
    """targets.json must be present and parseable; _aggregate key must exist."""
    assert "_aggregate" in targets, "targets.json missing '_aggregate' key"
    agg = targets["_aggregate"]
    assert "mean_centroid_hz_avg" in agg, (
        "targets.json _aggregate missing 'mean_centroid_hz_avg'"
    )


def test_pad_centroid_within_reference_range(targets):
    """Pad centroid at full-open filter must fall within reference session range.

    The mix centroid across SA's sessions spans 425–929 Hz (targets._aggregate).
    A solo pad at full-open filter should fall in a plausible sub-range of that.
    We check that it is not implausibly dark (<100 Hz) or absurdly bright (>18 kHz).
    """
    from instruments.pad import SupersawPad

    pad = SupersawPad(root_midi=55)
    l, _ = pad.render([60, 63, 65, 67], SPB, cutoff_slider=0.877)
    centroid = spectral_centroid(l)
    # Reference: session centroids 425–929 Hz (mix with kick/bass).
    # Solo pad at full-open filter is brighter; allow up to 1500 Hz.
    assert 300.0 < centroid < 1500.0, (
        f"Pad centroid {centroid:.0f} Hz outside reference range [300, 1500] Hz"
    )
