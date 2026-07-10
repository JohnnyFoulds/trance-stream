#!/usr/bin/env python3
"""Validate Hey Angel synthesis against analysis targets.

Measures the key parameters from our generator output and compares to
research/analysis/hey_angel_analysis.md targets.

Usage:
    python tools/validate_hey_angel.py
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import numpy as np

SR = 44100


def _rms_windows(signal: np.ndarray, win_s: float = 0.05) -> np.ndarray:
    win = int(win_s * SR)
    n = len(signal)
    windows = []
    for i in range(0, n - win, win):
        windows.append(float(np.sqrt(np.mean(signal[i:i+win]**2))))
    return np.array(windows)


def main():
    from song.builder import build_hey_angel_song
    from song.renderer import SongRenderer

    print("Building Hey Angel song...")
    song = build_hey_angel_song(total_bars=32)
    renderer = SongRenderer(song)
    buf_l, buf_r = renderer.render_bars(16)
    mono = (buf_l + buf_r) * 0.5

    print(f"\n{'='*60}")
    print("HEY ANGEL SYNTHESIS VALIDATION")
    print(f"{'='*60}")

    results = []

    # ── BPM ───────────────────────────────────────────────────────────────────
    bpm_ok = abs(song.bpm - 138.0) < 1.0
    results.append(('BPM', song.bpm, 138.0, bpm_ok))

    # ── Root MIDI ─────────────────────────────────────────────────────────────
    root_ok = song.root_midi == 43
    results.append(('Root MIDI', song.root_midi, 43, root_ok))

    # ── Kick pattern (half-time: energy on steps 0 and 8, silence on 4 and 12) ─
    from song.theory import samples_per_sixteenth
    sp16 = samples_per_sixteenth(song.bpm, SR)
    kick_renderer = SongRenderer(song, active_tracks={'kick'})
    kl, _ = kick_renderer.render_bars(4)
    # Check energy at each sixteenth: steps 0 and 8 should have peak, steps 4 and 12 silent
    def step_rms(sig, step, sp16):
        s = step * sp16
        e = min(s + sp16, len(sig))
        return float(np.sqrt(np.mean(sig[s:e]**2))) if e > s else 0.0
    rms_0  = step_rms(kl, 0, sp16)
    rms_4  = step_rms(kl, 4, sp16)
    rms_8  = step_rms(kl, 8, sp16)
    rms_12 = step_rms(kl, 12, sp16)
    # Half-time: steps 0 and 8 have kick (energy > 0.05), steps 4 and 12 silent
    kick_0_ok  = rms_0 > 0.05
    kick_8_ok  = rms_8 > 0.05
    kick_4_ok  = rms_4 < 0.001   # no kick at step 4
    kick_12_ok = rms_12 < 0.001  # no kick at step 12
    results.append(('Kick step 0 has energy', f'{rms_0:.4f}', '> 0.05', kick_0_ok))
    results.append(('Kick step 8 has energy', f'{rms_8:.4f}', '> 0.05', kick_8_ok))
    results.append(('Kick step 4 is silent', f'{rms_4:.6f}', '< 0.001', kick_4_ok))
    results.append(('Kick step 12 is silent', f'{rms_12:.6f}', '< 0.001', kick_12_ok))

    # ── Sidechain depth ───────────────────────────────────────────────────────
    rms_wins = _rms_windows(mono, 0.05)
    peak = rms_wins.max()
    trough = rms_wins.min()
    floor_ratio = trough / (peak + 1e-9)
    # Target: floor ~0.279 (floor can be lower because of bass going silent between notes)
    sc_ok = floor_ratio < 0.5  # at least some sidechain ducking
    results.append(('Sidechain floor ratio', floor_ratio, '< 0.5', sc_ok))

    # ── Spectral centroid (bars 4+, pluck active) ─────────────────────────────
    spb = int(SR * 4 * 60 / song.bpm)
    start = 4 * spb
    if start < len(mono):
        seg = mono[start:min(start + 4 * spb, len(mono))]
        n = min(len(seg), SR * 5)
        seg = seg[:n]
        spec = np.abs(np.fft.rfft(seg * np.hanning(len(seg))))
        freqs = np.fft.rfftfreq(len(seg), 1.0/SR)
        pw = spec**2
        centroid = float((freqs * pw).sum() / pw.sum()) if pw.sum() > 0 else 0.0
        # Hey Angel analysis has melody (185-260 Hz) + pluck (660 Hz) so centroid ~200-800 Hz
        centroid_ok = 100.0 <= centroid <= 1200.0
        results.append(('Spectral centroid (bars 4-8)', f'{centroid:.0f} Hz', '100-1200 Hz', centroid_ok))
    else:
        results.append(('Spectral centroid', 'N/A (render too short)', '100-1200 Hz', False))

    # ── No clipping ───────────────────────────────────────────────────────────
    peak_amp = float(np.abs(mono).max())
    no_clip = peak_amp < 1.0
    results.append(('Peak amplitude', f'{peak_amp:.4f}', '< 1.0', no_clip))

    # ── Non-silent output ─────────────────────────────────────────────────────
    total_rms = float(np.sqrt(np.mean(mono**2)))
    not_silent = total_rms > 0.01
    results.append(('Total RMS', f'{total_rms:.4f}', '> 0.01', not_silent))

    # ── Style field ───────────────────────────────────────────────────────────
    results.append(('Song style', song.style, 'hey_angel', song.style == 'hey_angel'))

    # ── Print table ───────────────────────────────────────────────────────────
    passed = 0
    failed = 0
    for name, got, want, ok in results:
        status = '✓ PASS' if ok else '✗ FAIL'
        if ok:
            passed += 1
        else:
            failed += 1
        print(f"{status}  {name:<35} got={got}  want={want}")

    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed")
    if failed == 0:
        print("ALL PASS")
        return 0
    else:
        return 1


if __name__ == '__main__':
    sys.exit(main())
