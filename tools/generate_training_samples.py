#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Generate ear training audio samples for the Perceptual Evaluation Framework.

Produces two groups of samples in research/reference_audio/training/:

  Group A — vocabulary demonstrations (Python synthesis, isolated single concept)
    Each term in the shared vocabulary table gets an ON and OFF version so the
    listener can hear exactly what changes.

  Group B — comparative pairs (Python synthesis vs SA/Strudel reference)
    Python synthesis alongside the nearest Strudel ground-truth equivalent.
    See research/analysis/perceptual_evaluation_framework.md §8.

All samples are rendered as 44100 Hz stereo 16-bit WAV then converted to
192 kbps MP3 via ffmpeg. WAV files are temporary intermediates; only MP3s
are committed to the repo (WAVs are gitignored).

Usage
-----
    python tools/generate_training_samples.py
    python tools/generate_training_samples.py --out /tmp/training
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import wave

import numpy as np

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

SR = 44100
BPM = 140.0
SAMPLES_PER_BAR = int(SR * 4 * 60 / BPM)   # ~75857 samples per bar at 140 BPM

DEFAULT_OUT = os.path.join(_REPO, 'research', 'reference_audio', 'training')
REF_DIR = os.path.join(_REPO, 'research', 'reference_audio')


# ── WAV I/O ───────────────────────────────────────────────────────────────────

def write_wav(path: str, buf_l: np.ndarray, buf_r: np.ndarray) -> None:
    stereo = np.stack([buf_l, buf_r], axis=1)
    stereo = np.clip(stereo, -1.0, 1.0)
    pcm = (stereo * 32767).astype(np.int16)
    with wave.open(path, 'w') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


def to_mp3(wav_path: str, mp3_path: str, bitrate: str = '192k') -> None:
    result = subprocess.run(
        ['ffmpeg', '-y', '-i', wav_path, '-b:a', bitrate, mp3_path],
        capture_output=True)
    if result.returncode != 0:
        print(f"  WARNING: ffmpeg failed for {wav_path}: {result.stderr.decode()[:200]}")


def render_and_convert(out_dir: str, stem: str,
                       buf_l: np.ndarray, buf_r: np.ndarray) -> str:
    """Write WAV + MP3, return the MP3 path."""
    wav_path = os.path.join(out_dir, stem + '.wav')
    mp3_path = os.path.join(out_dir, stem + '.mp3')
    write_wav(wav_path, buf_l, buf_r)
    to_mp3(wav_path, mp3_path)
    rms = float(np.sqrt(np.mean(buf_l.astype(np.float64) ** 2)))
    status = 'OK' if rms > 0.001 else 'SILENT!'
    print(f"  {stem}.mp3  rms={rms:.4f}  [{status}]")
    return mp3_path


# ── Helpers ───────────────────────────────────────────────────────────────────

def n_bars_samples(n: float) -> int:
    return int(SAMPLES_PER_BAR * n)


def tile_kick_pattern(kit, n_samples: int, gain: float = 0.8) -> tuple:
    """4-on-the-floor kick pattern tiled to n_samples."""
    kick_l, kick_r = kit.render_kick(gain=gain)
    kick_len = len(kick_l)
    beat_len = SAMPLES_PER_BAR // 4
    buf_l = np.zeros(n_samples, dtype=np.float32)
    buf_r = np.zeros(n_samples, dtype=np.float32)
    for beat in range(n_samples // beat_len + 1):
        start = beat * beat_len
        end = min(start + kick_len, n_samples)
        if start >= n_samples:
            break
        buf_l[start:end] += kick_l[:end - start]
        buf_r[start:end] += kick_r[:end - start]
    return buf_l, buf_r


def tile_hihat_pattern(kit, n_samples: int, gain: float = 1.0,
                       decay_s: float = 0.08) -> tuple:
    """16th-note hi-hat pattern tiled to n_samples."""
    hh_l, hh_r = kit.render_hihat(decay_s=decay_s, gain=gain)
    hh_len = len(hh_l)
    slot_len = SAMPLES_PER_BAR // 16
    buf_l = np.zeros(n_samples, dtype=np.float32)
    buf_r = np.zeros(n_samples, dtype=np.float32)
    for slot in range(n_samples // slot_len + 1):
        start = slot * slot_len
        end = min(start + hh_len, n_samples)
        if start >= n_samples:
            break
        buf_l[start:end] += hh_l[:end - start]
        buf_r[start:end] += hh_r[:end - start]
    return buf_l, buf_r


def render_pad_bars(pad, n_bars: int, midi_notes: list | None = None) -> tuple:
    """Render n_bars of SupersawPad, maintaining state across bars."""
    midi_notes = midi_notes or [43]
    total = np.zeros(n_bars_samples(n_bars), dtype=np.float32)
    total_r = np.zeros_like(total)
    pos = 0
    for _ in range(n_bars):
        n = SAMPLES_PER_BAR
        l, r = pad.render(midi_notes, n, bar_offset_samples=pos)
        total[pos:pos + n] += l
        total_r[pos:pos + n] += r
        pos += n
    return total, total_r


# ── Group A: vocabulary demonstrations ───────────────────────────────────────

def generate_vocabulary_samples(out_dir: str) -> list[str]:
    from instruments.drums import DrumKit
    from instruments.pad import SupersawPad
    from synth.effects import SchroederReverb, Sidechain

    print("\n[Group A] Vocabulary demonstrations")
    manifest = []
    N_BARS = 4
    n = n_bars_samples(N_BARS)

    kit = DrumKit(seed=42, sr=SR, kick_decay_s=0.50, kick_pitch_floor=53.0)

    # ── transient: kick with vs without attack click ──────────────────────────
    print("  transient pair")
    kick_l, kick_r = kit.render_kick(gain=1.0)
    # With transient — normal kick
    tiled_l, tiled_r = tile_kick_pattern(kit, n, gain=1.0)
    manifest.append(render_and_convert(out_dir, 'A01_transient_with',
                                       tiled_l, tiled_r))
    # Without transient — 10ms linear fade-in on the kick buffer
    fade_samples = int(SR * 0.010)
    fade = np.linspace(0.0, 1.0, fade_samples)
    kick_notrans_l = kick_l.copy()
    kick_notrans_r = kick_r.copy()
    kick_notrans_l[:fade_samples] *= fade
    kick_notrans_r[:fade_samples] *= fade
    kick_len = len(kick_notrans_l)
    beat_len = SAMPLES_PER_BAR // 4
    nt_l = np.zeros(n, dtype=np.float32)
    nt_r = np.zeros(n, dtype=np.float32)
    for beat in range(n // beat_len + 1):
        start = beat * beat_len
        end = min(start + kick_len, n)
        if start >= n:
            break
        nt_l[start:end] += kick_notrans_l[:end - start]
        nt_r[start:end] += kick_notrans_r[:end - start]
    manifest.append(render_and_convert(out_dir, 'A02_transient_without',
                                       nt_l, nt_r))

    # ── dry vs wet: kick alone ─────────────────────────────────────────────────
    print("  dry/wet pair")
    dry_l, dry_r = tile_kick_pattern(kit, n, gain=0.8)
    manifest.append(render_and_convert(out_dir, 'A03_dry_kick', dry_l, dry_r))

    reverb = SchroederReverb(room_size=0.85, wet=0.6, sr=SR)
    wet_l = dry_l.copy()
    wet_r = dry_r.copy()
    wet_l, wet_r = reverb.process(wet_l, wet_r)
    manifest.append(render_and_convert(out_dir, 'A04_wet_kick', wet_l, wet_r))

    # ── gate: pad with vs without trancegate ──────────────────────────────────
    print("  gate pair")
    # Gate ON — TRANCEGATE_FLOOR=0.0 (true binary silence on off-slots)
    pad_gate_on = SupersawPad(root_midi=43, cutoff_slider=0.50,
                              gain=0.6, sr=SR, bpm=BPM)
    # Monkey-patch floor to 0.0 for this render
    import song.theory as _theory
    _orig_floor = _theory.TRANCEGATE_FLOOR
    _theory.TRANCEGATE_FLOOR = 0.0
    gate_on_l, gate_on_r = render_pad_bars(pad_gate_on, N_BARS)
    manifest.append(render_and_convert(out_dir, 'A05_gate_on',
                                       gate_on_l, gate_on_r))
    # Gate OFF — floor=1.0 (continuous pad, no gating)
    _theory.TRANCEGATE_FLOOR = 1.0
    pad_gate_off = SupersawPad(root_midi=43, cutoff_slider=0.50,
                               gain=0.6, sr=SR, bpm=BPM)
    gate_off_l, gate_off_r = render_pad_bars(pad_gate_off, N_BARS)
    manifest.append(render_and_convert(out_dir, 'A06_gate_off',
                                       gate_off_l, gate_off_r))
    _theory.TRANCEGATE_FLOOR = _orig_floor  # restore

    # ── sweep: pad with lpenv vs static filter ────────────────────────────────
    print("  sweep pair")
    # Sweep ON — normal SupersawPad (lpenv active, filter opens each bar)
    pad_sweep_on = SupersawPad(root_midi=43, cutoff_slider=0.50,
                               gain=0.6, sr=SR, bpm=BPM)
    sweep_on_l, sweep_on_r = render_pad_bars(pad_sweep_on, N_BARS)
    manifest.append(render_and_convert(out_dir, 'A07_sweep_on',
                                       sweep_on_l, sweep_on_r))
    # Sweep OFF — render pad but patch lpenv decay to near-zero so filter stays static
    # Do this by overriding the lpenv constants temporarily
    pad_sweep_off = SupersawPad(root_midi=43, cutoff_slider=0.70,
                                gain=0.6, sr=SR, bpm=BPM)
    # Override: bypass lpenv by setting decay to near-instant (filter always at base)
    # We patch the private _lpenv_t_s to a very large value so the filter is
    # already at base cutoff before the first sample
    pad_sweep_off._lpenv_t_s = 999.0
    sweep_off_l, sweep_off_r = render_pad_bars(pad_sweep_off, N_BARS)
    manifest.append(render_and_convert(out_dir, 'A08_sweep_off',
                                       sweep_off_l, sweep_off_r))

    # ── pump: pad + kick with vs without sidechain ────────────────────────────
    print("  pump pair")
    kick_bus_l, kick_bus_r = tile_kick_pattern(kit, n, gain=0.8)

    pad_for_pump = SupersawPad(root_midi=43, cutoff_slider=0.50,
                               gain=0.5, sr=SR, bpm=BPM)
    pad_l, pad_r = render_pad_bars(pad_for_pump, N_BARS)

    # With pump
    sc = Sidechain(depth=0.6, attack_s=0.16, sr=SR)
    pad_pumped_l, pad_pumped_r = sc.process(pad_l, pad_r, kick_bus_l)
    pump_on_l = np.clip(kick_bus_l + pad_pumped_l, -1.0, 1.0)
    pump_on_r = np.clip(kick_bus_r + pad_pumped_r, -1.0, 1.0)
    manifest.append(render_and_convert(out_dir, 'A09_pump_on',
                                       pump_on_l, pump_on_r))
    # Without pump
    pump_off_l = np.clip(kick_bus_l + pad_l * 0.5, -1.0, 1.0)
    pump_off_r = np.clip(kick_bus_r + pad_r * 0.5, -1.0, 1.0)
    manifest.append(render_and_convert(out_dir, 'A10_pump_off',
                                       pump_off_l, pump_off_r))

    # ── spread: stereo supersaw vs mono ───────────────────────────────────────
    print("  spread pair")
    pad_spread = SupersawPad(root_midi=43, cutoff_slider=0.50,
                             gain=0.6, sr=SR, bpm=BPM)
    spread_l, spread_r = render_pad_bars(pad_spread, N_BARS)
    manifest.append(render_and_convert(out_dir, 'A11_spread_stereo',
                                       spread_l, spread_r))
    mono = (spread_l + spread_r) * 0.5
    manifest.append(render_and_convert(out_dir, 'A12_spread_mono', mono, mono))

    # ── sub: bass with vs without sub-bass ───────────────────────────────────
    print("  sub pair")
    from instruments.bass import AcidBass

    bass = AcidBass(sr=SR)
    bass_n = n_bars_samples(N_BARS)
    # Render repeating bass note
    note_len = SAMPLES_PER_BAR
    bass_l_full = np.zeros(bass_n, dtype=np.float32)
    bass_r_full = np.zeros(bass_n, dtype=np.float32)
    for bar in range(N_BARS):
        bl, br = bass.render(43, note_len)
        bass_l_full[bar * note_len:(bar + 1) * note_len] = bl
        bass_r_full[bar * note_len:(bar + 1) * note_len] = br
    manifest.append(render_and_convert(out_dir, 'A13_sub_with',
                                       bass_l_full * 0.6, bass_r_full * 0.6))
    # Remove sub by high-passing at 80 Hz
    from scipy.signal import butter, sosfilt
    sos = butter(2, 80.0 / (SR / 2), btype='high', output='sos')
    bass_nosub_l = sosfilt(sos, bass_l_full).astype(np.float32)
    bass_nosub_r = sosfilt(sos, bass_r_full).astype(np.float32)
    manifest.append(render_and_convert(out_dir, 'A14_sub_without',
                                       bass_nosub_l * 0.6, bass_nosub_r * 0.6))

    return manifest


# ── Group B: comparative pairs ────────────────────────────────────────────────

def generate_comparative_samples(out_dir: str) -> list[str]:
    from instruments.drums import DrumKit
    from instruments.pad import SupersawPad
    from synth.effects import Sidechain

    print("\n[Group B] Comparative pairs")
    manifest = []
    N_BARS = 4
    n = n_bars_samples(N_BARS)

    # ── B01/B02: pad — Strudel reference vs Python synthesis ──────────────────
    # Strudel: copy existing sa_trancegate_c1_8s.wav trimmed to 4 bars
    print("  pad comparison")
    src_wav = os.path.join(REF_DIR, 'sa_trancegate_c1_8s.wav')
    if os.path.exists(src_wav):
        dst_mp3 = os.path.join(out_dir, 'B01_pad_strudel.mp3')
        to_mp3(src_wav, dst_mp3)
        print(f"  B01_pad_strudel.mp3  [copied from sa_trancegate_c1_8s.wav]")
        manifest.append(dst_mp3)
    else:
        print(f"  B01_pad_strudel.mp3  [SKIPPED — sa_trancegate_c1_8s.wav not found]")

    import song.theory as _theory
    _orig_floor = _theory.TRANCEGATE_FLOOR
    _theory.TRANCEGATE_FLOOR = 0.0
    pad_cmp = SupersawPad(root_midi=43, cutoff_slider=0.50,
                          gain=0.6, sr=SR, bpm=BPM)
    cmp_l, cmp_r = render_pad_bars(pad_cmp, N_BARS)
    _theory.TRANCEGATE_FLOOR = _orig_floor
    manifest.append(render_and_convert(out_dir, 'B02_pad_python',
                                       cmp_l, cmp_r))

    # ── B03/B04: kick — TR-909 reference vs Python synthesis ──────────────────
    print("  kick comparison")
    src_kick = os.path.join(REF_DIR, 'kick_compare_tr909_reference.wav')
    if os.path.exists(src_kick):
        dst_mp3 = os.path.join(out_dir, 'B03_kick_tr909.mp3')
        to_mp3(src_kick, dst_mp3)
        print(f"  B03_kick_tr909.mp3  [copied from kick_compare_tr909_reference.wav]")
        manifest.append(dst_mp3)
    else:
        print(f"  B03_kick_tr909.mp3  [SKIPPED — kick_compare_tr909_reference.wav not found]")

    kit = DrumKit(seed=42, sr=SR, kick_decay_s=0.50, kick_pitch_floor=53.0)
    kick_l, kick_r = tile_kick_pattern(kit, n, gain=0.8)
    manifest.append(render_and_convert(out_dir, 'B04_kick_python',
                                       kick_l, kick_r))

    # ── B05/B06: sidechain — Strudel reference vs Python ─────────────────────
    print("  sidechain comparison")
    src_sc = os.path.join(REF_DIR, 'sa_sidechain_c2_8s.wav')
    if os.path.exists(src_sc):
        dst_mp3 = os.path.join(out_dir, 'B05_sidechain_strudel.mp3')
        to_mp3(src_sc, dst_mp3)
        print(f"  B05_sidechain_strudel.mp3  [copied from sa_sidechain_c2_8s.wav]")
        manifest.append(dst_mp3)
    else:
        print(f"  B05_sidechain_strudel.mp3  [SKIPPED — sa_sidechain_c2_8s.wav not found]")

    _theory.TRANCEGATE_FLOOR = 0.0
    pad_sc = SupersawPad(root_midi=43, cutoff_slider=0.50,
                         gain=0.5, sr=SR, bpm=BPM)
    pad_l, pad_r = render_pad_bars(pad_sc, N_BARS)
    _theory.TRANCEGATE_FLOOR = _orig_floor
    kick_bus_l, kick_bus_r = tile_kick_pattern(kit, n, gain=0.8)
    sc = Sidechain(depth=0.6, attack_s=0.16, sr=SR)
    pad_sc_l, pad_sc_r = sc.process(pad_l, pad_r, kick_bus_l)
    mix_l = np.clip(kick_bus_l + pad_sc_l, -1.0, 1.0)
    mix_r = np.clip(kick_bus_r + pad_sc_r, -1.0, 1.0)
    manifest.append(render_and_convert(out_dir, 'B06_sidechain_python',
                                       mix_l, mix_r))

    # ── B07/B08: full mix — SA reference vs OPT-002 best ─────────────────────
    print("  full mix comparison")
    # Trim first ~27.4s of hey_angel_trimmed.wav (= the reference duration)
    src_ref = os.path.join(REF_DIR, 'hey_angel_trimmed.wav')
    if os.path.exists(src_ref):
        dst_mp3 = os.path.join(out_dir, 'B07_fullmix_sa.mp3')
        to_mp3(src_ref, dst_mp3)
        print(f"  B07_fullmix_sa.mp3  [copied from hey_angel_trimmed.wav]")
        manifest.append(dst_mp3)
    else:
        print(f"  B07_fullmix_sa.mp3  [SKIPPED — hey_angel_trimmed.wav not found]")

    # Render 16-bar cover with OPT-002 best params
    best_wav = os.path.join(out_dir, '_tmp_best_params.wav')
    print(f"  rendering 16-bar cover (OPT-002 params)…")
    result = subprocess.run(
        [sys.executable,
         os.path.join(_REPO, 'hey_angel_cover.py'),
         '--bars', '16', '--wav', best_wav],
        capture_output=True, cwd=_REPO)
    if result.returncode == 0 and os.path.exists(best_wav):
        dst_mp3 = os.path.join(out_dir, 'B08_fullmix_ours.mp3')
        to_mp3(best_wav, dst_mp3)
        print(f"  B08_fullmix_ours.mp3  [rendered 16 bars]")
        manifest.append(dst_mp3)
    else:
        print(f"  B08_fullmix_ours.mp3  [FAILED: {result.stderr.decode()[:200]}]")

    return manifest


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--out', default=DEFAULT_OUT,
                    help='Output directory (default: research/reference_audio/training/)')
    args = ap.parse_args()

    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    print(f"Output → {out_dir}")
    print(f"SR={SR} Hz, BPM={BPM}, {SAMPLES_PER_BAR} samples/bar")

    manifest = []
    manifest += generate_vocabulary_samples(out_dir)
    manifest += generate_comparative_samples(out_dir)

    # Clean up temp WAV files (MP3s are the keeper)
    for f in os.listdir(out_dir):
        if f.endswith('.wav') and not f.startswith('_'):
            os.remove(os.path.join(out_dir, f))

    tmp = os.path.join(out_dir, '_tmp_best_params.wav')
    if os.path.exists(tmp):
        os.remove(tmp)

    print(f"\n{'─'*60}")
    print(f"Generated {len(manifest)} MP3 files in {out_dir}/")
    for p in manifest:
        print(f"  {os.path.basename(p)}")
    print(f"\nAll WAV intermediates cleaned up.")
    print(f"To play a sample:  afplay {manifest[0]}")


if __name__ == '__main__':
    main()
