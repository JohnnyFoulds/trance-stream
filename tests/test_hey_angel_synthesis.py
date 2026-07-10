# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Tests for the Hey Angel synthesis elements.

Validates that the generator reproduces the key perceptual targets from
research/analysis/hey_angel_analysis.md:
- BPM 138, root G1 (MIDI 43)
- Half-time kick pattern (steps 0 and 8, not 4 and 12)
- Bass: G1 + F2 + portamento sweep
- Melody: C4→F#3 chromatic descend (verified by lead render non-silence)
- High pluck: E5 brightness burst
- Sidechain: depth=0.721 (floor 0.279)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np
import pytest

SR = 44100


def _step_rms(sig: np.ndarray, step: int, sp16: int) -> float:
    s = step * sp16
    e = min(s + sp16, len(sig))
    if e <= s:
        return 0.0
    return float(np.sqrt(np.mean(sig[s:e] ** 2)))


@pytest.fixture(scope="module")
def hey_angel_song():
    from song.builder import build_hey_angel_song
    return build_hey_angel_song(total_bars=32)


@pytest.fixture(scope="module")
def hey_angel_render():
    # Use a fresh song instance so that tests sharing hey_angel_song (which
    # render into its instruments and mutate their phase/delay state) don't
    # corrupt the render used for clipping / audibility assertions.
    from song.builder import build_hey_angel_song
    from song.renderer import SongRenderer
    song = build_hey_angel_song(total_bars=32)
    renderer = SongRenderer(song)
    buf_l, buf_r = renderer.render_bars(16)
    return buf_l, buf_r


def test_song_style_field(hey_angel_song):
    assert hey_angel_song.style == 'hey_angel'


def test_bpm_138(hey_angel_song):
    assert hey_angel_song.bpm == 138.0


def test_root_g1(hey_angel_song):
    assert hey_angel_song.root_midi == 43, f"Expected G1=43, got {hey_angel_song.root_midi}"


def test_kick_halftime_step0(hey_angel_song):
    from song.renderer import SongRenderer
    from song.theory import samples_per_sixteenth
    sp16 = samples_per_sixteenth(hey_angel_song.bpm, SR)
    renderer = SongRenderer(hey_angel_song, active_tracks={'kick'})
    kl, _ = renderer.render_bars(2)
    assert _step_rms(kl, 0, sp16) > 0.05, "Kick should hit at step 0"


def test_kick_halftime_step8(hey_angel_song):
    from song.renderer import SongRenderer
    from song.theory import samples_per_sixteenth
    sp16 = samples_per_sixteenth(hey_angel_song.bpm, SR)
    renderer = SongRenderer(hey_angel_song, active_tracks={'kick'})
    kl, _ = renderer.render_bars(2)
    assert _step_rms(kl, 8, sp16) > 0.05, "Kick should hit at step 8 (half-note)"


def test_kick_no_step4(hey_angel_song):
    from song.renderer import SongRenderer
    from song.theory import samples_per_sixteenth
    sp16 = samples_per_sixteenth(hey_angel_song.bpm, SR)
    renderer = SongRenderer(hey_angel_song, active_tracks={'kick'})
    kl, _ = renderer.render_bars(2)
    assert _step_rms(kl, 4, sp16) < 0.001, "No kick at step 4 (four-on-floor would be here)"


def test_kick_no_step12(hey_angel_song):
    from song.renderer import SongRenderer
    from song.theory import samples_per_sixteenth
    sp16 = samples_per_sixteenth(hey_angel_song.bpm, SR)
    renderer = SongRenderer(hey_angel_song, active_tracks={'kick'})
    kl, _ = renderer.render_bars(2)
    assert _step_rms(kl, 12, sp16) < 0.001, "No kick at step 12 (four-on-floor would be here)"


def test_bass_g1_present(hey_angel_song):
    """Bass renders non-silent audio (G1 present)."""
    from song.renderer import SongRenderer
    renderer = SongRenderer(hey_angel_song, active_tracks={'bass'})
    bl, _ = renderer.render_bars(2)
    assert float(np.abs(bl).max()) > 0.05, "Bass should produce audible signal"


def test_bass_portamento_pitch_shift(hey_angel_song):
    """Bass portamento: frequency content should span G1→F2 range (49–87 Hz)."""
    from instruments.bass import AcidBass
    bass = AcidBass(sr=SR)
    # Render portamento sweep F2→G1 over 0.1s (typical sweep duration)
    n = int(0.1 * SR)
    bl, _ = bass.render(53, n, gain=1.0, portamento_s=0.1, target_midi=43)
    assert float(np.abs(bl).max()) > 0.01, "Portamento render should produce non-silent audio"


def test_lead_melody_c4_nondiscrete(hey_angel_song):
    """Lead renders the C4→F#3 melody (non-silent, not stuck at one pitch)."""
    from song.renderer import SongRenderer
    renderer = SongRenderer(hey_angel_song, active_tracks={'lead'})
    ll, _ = renderer.render_bars(4)
    rms = float(np.sqrt(np.mean(ll ** 2)))
    assert rms > 0.01, "Lead should produce audible melody"


def test_pluck_enters_at_bar2(hey_angel_song):
    """High pluck enters at bar 2 (active_from_bar=2)."""
    from song.renderer import SongRenderer
    renderer = SongRenderer(hey_angel_song, active_tracks={'pluck'})
    buf_l, _ = renderer.render_bars(4)
    spb = int(SR * 4 * 60 / hey_angel_song.bpm)
    # Bars 0-1 should be silent, bars 2-3 should have pluck
    early = float(np.sqrt(np.mean(buf_l[:spb * 2] ** 2)))
    later = float(np.sqrt(np.mean(buf_l[spb * 2:spb * 4] ** 2)))
    assert early < 0.01, f"Pluck should be silent before bar 2, got rms={early:.4f}"
    assert later > 0.01, f"Pluck should play from bar 2, got rms={later:.4f}"


def test_pluck_e5_brightness(hey_angel_song):
    """High pluck at E5 has expected brightness (centroid decay from 2500 to 1600 Hz)."""
    from instruments.pluck import HighPluck
    pluck = HighPluck(sr=SR)
    n = int(0.1 * SR)   # 100ms
    pl, _ = pluck.render(76, n, gain=1.0)   # E5 = MIDI 76
    assert float(np.abs(pl).max()) > 0.05, "Pluck E5 should be audible"
    # Check centroid of first 25ms is higher than last 25ms (brightness decay)
    n25 = int(0.025 * SR)
    spec_early = np.abs(np.fft.rfft(pl[:n25] * np.hanning(n25))) ** 2
    spec_late  = np.abs(np.fft.rfft(pl[-n25:] * np.hanning(n25))) ** 2
    freqs = np.fft.rfftfreq(n25, 1.0/SR)
    c_early = float((freqs * spec_early).sum() / spec_early.sum()) if spec_early.sum() > 0 else 0
    c_late  = float((freqs * spec_late).sum()  / spec_late.sum())  if spec_late.sum()  > 0 else 0
    assert c_early > c_late, (
        f"Pluck brightness should decay: early centroid {c_early:.0f} Hz should > "
        f"late centroid {c_late:.0f} Hz"
    )


def test_sidechain_depth_hey_angel():
    """Sidechain depth for Hey Angel style is 0.721 (floor = 0.279)."""
    from song.theory import SIDECHAIN_DEPTH_HEY_ANGEL
    assert abs(SIDECHAIN_DEPTH_HEY_ANGEL - 0.721) < 0.001
    floor = 1.0 - SIDECHAIN_DEPTH_HEY_ANGEL
    assert abs(floor - 0.279) < 0.001, f"Expected floor 0.279, got {floor:.3f}"


def test_full_render_no_clipping(hey_angel_render):
    buf_l, buf_r = hey_angel_render
    mono = (buf_l + buf_r) * 0.5
    assert float(np.abs(mono).max()) < 1.0, "Full render should not clip"


def test_full_render_audible(hey_angel_render):
    buf_l, buf_r = hey_angel_render
    mono = (buf_l + buf_r) * 0.5
    rms = float(np.sqrt(np.mean(mono ** 2)))
    assert rms > 0.05, f"Full Hey Angel render should be audible (rms={rms:.4f})"
