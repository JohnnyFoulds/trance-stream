"""Strudel → WAV capture → analysis tool test.

Tests the full closed loop:
  1. Strudel plays audio via WebAudio in a headless Chromium browser
  2. Python captures the audio via window.__captureWav() (AnalyserNode polling)
  3. Captured float32 array is written to a WAV file
  4. The analysis tools (analyse_audio, analyse_timbre) run on the WAV
  5. Measurements are asserted against known SA synthesis parameters

Requires:
  - Local HTTP server on port 8765 serving research/:
      python -m http.server 8765 --directory research
  - playwright installed: pip install playwright
  - Chromium: playwright install chromium

Usage:
    python -m http.server 8765 --directory research &
    python tools/test_strudel_wav_analysis.py
    # Expected: ALL PASS, exit code 0
"""
import sys
import time
import wave
import struct
import tempfile
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))

import numpy as np

URL = 'http://localhost:8765/strudel_debug.html'


def _write_wav(path: str, samples: list, sample_rate: int) -> str:
    """Write a list of floats to a 16-bit mono WAV file."""
    arr = np.array(samples, dtype=np.float32)
    arr = np.clip(arr, -1.0, 1.0)
    pcm = (arr * 32767).astype(np.int16)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return path


def _spectral_centroid(samples: list, sr: int) -> float:
    arr = np.array(samples, dtype=np.float32)
    spec = np.abs(np.fft.rfft(arr * np.hanning(len(arr))))
    freqs = np.fft.rfftfreq(len(arr), 1.0 / sr)
    pw = spec ** 2
    return float((freqs * pw).sum() / pw.sum()) if pw.sum() > 0 else 0.0


def run():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("SKIP: playwright not installed — pip install playwright && playwright install chromium")
        return 0

    passes, failures = [], []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        console_log = []
        page.on('console', lambda m: console_log.append({'type': m.type, 'text': m.text[:300]}))
        page.on('pageerror', lambda e: console_log.append({'type': 'pageerror', 'text': str(e)[:300]}))
        page.goto(URL)

        print('Waiting for Ready...')
        page.wait_for_function(
            "() => document.getElementById('status').textContent.includes('Ready')",
            timeout=30000)
        print('Page ready.')

        with tempfile.TemporaryDirectory() as tmpdir:
            # ── Snippet c1: pad only ──────────────────────────────────────────
            print('\n--- Snippet c1 (pad only) ---')
            page.locator("button[onclick=\"playSnippet('c1')\"]").click()
            time.sleep(3)  # let Strudel warm up and start playing

            # Capture 4 seconds of audio
            result = page.evaluate("() => window.__captureWav(4)")
            samples_c1 = result.get('samples', [])
            sr_c1 = result.get('sampleRate', 44100)
            print(f'  Captured {len(samples_c1)} samples at {sr_c1}Hz')

            # Non-silence check
            rms_c1 = float(np.sqrt(np.mean(np.array(samples_c1) ** 2))) if samples_c1 else 0.0
            print(f'  RMS: {rms_c1:.4f}')
            if rms_c1 > 0.01:
                passes.append(f'c1: non-silent (RMS={rms_c1:.4f})')
            else:
                failures.append(f'c1: near-silent RMS={rms_c1:.4f} — expected > 0.01')

            wav_c1 = _write_wav(f"{tmpdir}/c1.wav", samples_c1, sr_c1)

            # Spectral centroid — SA pad with rlpf(0.5) = (0.5*12)^4 = 1296 Hz
            # Expect centroid somewhere in 400–2500 Hz range (rlpf shapes a broad band)
            centroid_c1 = _spectral_centroid(samples_c1, sr_c1)
            print(f'  Spectral centroid: {centroid_c1:.0f}Hz')
            if 200 <= centroid_c1 <= 3000:
                passes.append(f'c1: centroid {centroid_c1:.0f}Hz in expected range 200–3000Hz')
            else:
                failures.append(f'c1: centroid {centroid_c1:.0f}Hz outside expected range 200–3000Hz')

            # analyse_audio on the captured WAV
            try:
                from tools.analyse_audio import analyse_wav
                wav_stats = analyse_wav(wav_c1)
                print(f'  analyse_wav peak={wav_stats["peak"]:.4f} rms={wav_stats["rms"]:.5f}')
                if wav_stats["peak"] > 0.01:
                    passes.append(f'c1: analyse_wav peak={wav_stats["peak"]:.4f}')
                else:
                    failures.append(f'c1: analyse_wav peak near-zero — capture or analysis failed')
            except Exception as e:
                failures.append(f'c1: analyse_wav raised {type(e).__name__}: {e}')

            # analyse_timbre
            try:
                from tools.analyse_timbre import analyse_timbre
                timbre = analyse_timbre(wav_c1, bpm=140.0, fmin=40.0, fmax=4000.0)
                osc = timbre.get('oscillator_type', 'unknown')
                cutoff = timbre.get('filter_cutoff_hz', 0)
                print(f'  analyse_timbre osc={osc} cutoff={cutoff:.0f}Hz')
                if osc != 'unknown':
                    passes.append(f'c1: oscillator classified as {osc!r}')
                else:
                    failures.append(f'c1: oscillator classified as "unknown" — check harmonic analysis')
                # rlpf(0.5) → (0.5*12)^4 = 1296 Hz; filter estimate should be < 4000 Hz
                if cutoff < 4000:
                    passes.append(f'c1: filter_cutoff_hz={cutoff:.0f}Hz < 4000Hz')
                else:
                    failures.append(f'c1: filter_cutoff_hz={cutoff:.0f}Hz unexpectedly high')
            except Exception as e:
                failures.append(f'c1: analyse_timbre raised {type(e).__name__}: {e}')

            # ── Snippet c2: pad + kick ────────────────────────────────────────
            page.locator("button[onclick=\"playSnippet('c1')\"]").locator('..').locator('button.stop').click()
            time.sleep(1)
            print('\n--- Snippet c2 (pad + kick) ---')
            page.locator("button[onclick=\"playSnippet('c2')\"]").click()
            time.sleep(3)

            result2 = page.evaluate("() => window.__captureWav(4)")
            samples_c2 = result2.get('samples', [])
            sr_c2 = result2.get('sampleRate', 44100)
            rms_c2 = float(np.sqrt(np.mean(np.array(samples_c2) ** 2))) if samples_c2 else 0.0
            print(f'  RMS: {rms_c2:.4f}')
            if rms_c2 > 0.01:
                passes.append(f'c2: non-silent (RMS={rms_c2:.4f})')
            else:
                failures.append(f'c2: near-silent RMS={rms_c2:.4f}')

            wav_c2 = _write_wav(f"{tmpdir}/c2.wav", samples_c2, sr_c2)

            # c2 has kick → sub-bass energy should be higher than c1
            try:
                from tools.analyse_audio import analyse_wav as analyse_wav2
                stats_c1 = analyse_wav(wav_c1)
                stats_c2 = analyse_wav2(wav_c2)
                sub_c1 = stats_c1['band_energy']['sub']
                sub_c2 = stats_c2['band_energy']['sub']
                print(f'  Sub energy: c1={sub_c1:.4f}  c2={sub_c2:.4f}')
                if sub_c2 >= sub_c1:
                    passes.append(f'c2 sub energy {sub_c2:.4f} >= c1 sub energy {sub_c1:.4f} (kick adds sub)')
                else:
                    failures.append(f'c2 sub {sub_c2:.4f} < c1 sub {sub_c1:.4f} — kick not adding sub bass?')
            except Exception as e:
                failures.append(f'c2: sub energy comparison raised {type(e).__name__}: {e}')

            # ── Stop and verify silence ───────────────────────────────────────
            page.locator("button[onclick=\"playSnippet('c2')\"]").locator('..').locator('button.stop').click()
            time.sleep(1.5)

            # Capture 1s — should be near-silent
            result_stop = page.evaluate("() => window.__captureWav(1)")
            samples_stop = result_stop.get('samples', [])
            rms_stop = float(np.sqrt(np.mean(np.array(samples_stop) ** 2))) if samples_stop else 0.0
            print(f'\n--- After stop ---')
            print(f'  Post-stop RMS: {rms_stop:.5f}')
            if rms_stop < 0.01:
                passes.append(f'After stop: RMS={rms_stop:.5f} < 0.01 (silence)')
            else:
                failures.append(f'After stop: RMS={rms_stop:.5f} >= 0.01 — audio still playing?')

        browser.close()

    # ── Console error check ───────────────────────────────────────────────────
    js_errors = [e for e in console_log if e['type'] in ('error', 'pageerror')]
    if not js_errors:
        passes.append('Console: no JS errors')
    else:
        for e in js_errors:
            failures.append(f'Console JS error: {e["text"][:100]}')

    # ── Verdict ───────────────────────────────────────────────────────────────
    print('\n═══ RESULTS ═══')
    for p in passes:
        print(f'  PASS  {p}')
    for f in failures:
        print(f'  FAIL  {f}')
    print(f'\n═══ VERDICT: {len(passes)} passed, {len(failures)} failed ═══')
    return 0 if not failures else 1


if __name__ == '__main__':
    sys.exit(run())
