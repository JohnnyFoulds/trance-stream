"""Standalone tool: play a strudel_debug.html snippet and write the audio to a WAV file.

Purpose
-------
``test_strudel_page.py`` and ``test_strudel_wav_analysis.py`` capture only RMS / spectral
centroid scalars in real time.  This script captures the full PCM audio stream as a WAV
file on disk, which is required for detailed spectral analysis (band energy, MFCC distance,
trancegate gate profile, sidechain pump depth, etc.).

The ``window.__captureWav(seconds)`` function is already implemented in
``research/strudel_debug.html`` — it polls an AnalyserNode at the audio-frame rate and
returns a ``{ samples: Float32Array, sampleRate: number }`` object.  This script drives the
page via Playwright, calls that function after a warmup period, and writes the result to disk.

Prerequisites
-------------
- ``playwright`` Python package installed: ``pip install playwright``
- Chromium: ``playwright install chromium``
- No separate HTTP server needed: this script starts one automatically on ``--port``.

Snippets
--------
- ``c1`` — SA's exact pad code (G minor, no kick): trancegate + rlpf + lpenv + room
- ``c2`` — Pad + TR-909 kick (G minor): matches SA video GWXCCBsOMSg at t=40s
- ``c3`` — Experiment (A minor): same chain as c1 but different key for our generator

Usage
-----
From repo root::

    python tools/capture_strudel_wav.py --snippet c1 --duration 8 \\
        --out research/reference_audio/sa_trancegate_c1_8s.wav

    python tools/capture_strudel_wav.py --snippet c2 --duration 8 \\
        --out research/reference_audio/sa_sidechain_c2_8s.wav

    python tools/capture_strudel_wav.py --snippet c3 --duration 8 \\
        --out research/reference_audio/sa_experiment_c3_8s.wav

To reproduce audit captures exactly::

    python tools/capture_strudel_wav.py --snippet c1 --duration 8 --warmup 3 \\
        --out research/reference_audio/sa_trancegate_c1_8s.wav
    python tools/capture_strudel_wav.py --snippet c2 --duration 8 --warmup 3 \\
        --out research/reference_audio/sa_sidechain_c2_8s.wav
"""
import argparse
import http.server
import os
import socketserver
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np

# ── repo paths ────────────────────────────────────────────────────────────────
_REPO_ROOT    = Path(__file__).parent.parent
_RESEARCH_DIR = _REPO_ROOT / 'research'

# ── snippet metadata ──────────────────────────────────────────────────────────
_SNIPPET_LABELS = {
    'c1':  'pad only',
    'c2':  'pad + kick',
    'c3':  'experiment (A minor)',
    'c4':  'ear-training: acid lead',
    'c5':  'ear-training: noisehat',
    'c6':  'ear-training: gate ON',
    'c7':  'ear-training: gate OFF',
    'c8':  'ear-training: sweep ON',
    'c9':  'ear-training: sweep OFF',
    'c10': 'ear-training: kick dry',
    'c11': 'ear-training: kick wet',
    'c12': 'ear-training: pump ON',
    'c13': 'ear-training: pump OFF',
}


# ── HTTP server (embedded) ─────────────────────────────────────────────────────

class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    """SimpleHTTPRequestHandler that suppresses access logs and serves research/."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(_RESEARCH_DIR), **kwargs)

    def log_message(self, fmt, *args):  # noqa: N802
        pass  # suppress per-request stdout noise


def _start_server(port: int) -> socketserver.TCPServer:
    """Start a background HTTP server serving research/ on *port*."""
    socketserver.TCPServer.allow_reuse_address = True
    server = socketserver.TCPServer(('', port), _QuietHandler)
    thread = threading.Thread(target=server.serve_forever)
    thread.daemon = True
    thread.start()
    return server


# ── WAV writer (copied verbatim from test_strudel_wav_analysis.py) ─────────────

def _write_wav(path: str, samples: list, sample_rate: int) -> str:
    """Write a list of floats to a 16-bit mono WAV file."""
    arr = np.array(samples, dtype=np.float32)
    arr = np.clip(arr, -1.0, 1.0)
    pcm = (arr * 32767).astype(np.int16)
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm.tobytes())
    return path


# ── inline spectral centroid (no librosa / scipy) ─────────────────────────────

def _spectral_centroid(samples: list, sr: int) -> float:
    """Return the mean spectral centroid in Hz using a single FFT window."""
    arr = np.array(samples, dtype=np.float32)
    if len(arr) == 0:
        return 0.0
    spec  = np.abs(np.fft.rfft(arr * np.hanning(len(arr))))
    freqs = np.fft.rfftfreq(len(arr), 1.0 / sr)
    pw    = spec ** 2
    return float((freqs * pw).sum() / pw.sum()) if pw.sum() > 0 else 0.0


# ── main capture routine ───────────────────────────────────────────────────────

def capture(snippet: str, duration: float, out_path: str, warmup: float, port: int) -> int:
    """
    Play *snippet* in strudel_debug.html, wait *warmup* seconds, capture *duration*
    seconds of audio, write to *out_path*, print metrics, return exit code.
    """
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print('FAIL: playwright not installed — pip install playwright && playwright install chromium')
        return 1

    url = f'http://localhost:{port}/strudel_debug.html'

    # Ensure output directory exists
    out_dir = Path(out_path).parent
    if out_dir and not out_dir.exists():
        out_dir.mkdir(parents=True, exist_ok=True)

    server = _start_server(port)
    try:
        with sync_playwright() as p:
            # No --autoplay-policy or --disable-web-security (CLAUDE.md rule)
            browser = p.chromium.launch(headless=True)
            page    = browser.new_page()

            console_log = []
            page.on('console',   lambda m: console_log.append({'type': m.type, 'text': m.text[:300]}))
            page.on('pageerror', lambda e: console_log.append({'type': 'pageerror', 'text': str(e)[:300]}))

            page.goto(url)

            # Wait for strudel_debug.html to finish its async init sequence
            try:
                page.wait_for_function(
                    "() => document.getElementById('status').textContent.includes('Ready')",
                    timeout=30000,
                )
            except Exception:
                print('FAIL: strudel_debug.html did not become ready (timeout)')
                browser.close()
                return 1

            # Click the play button — this also resumes the suspended AudioContext
            # (playSnippet() calls ctx.resume() inside the click handler, which is the
            # only context in which the browser allows it).
            page.locator(f"button[onclick=\"playSnippet('{snippet}')\"]").click()

            # Warmup: let the synth settle (worklets fully loaded, gate phase stable)
            time.sleep(warmup)

            # Capture audio — __captureWav() returns a Promise; Playwright awaits it
            result     = page.evaluate(f'() => window.__captureWav({duration})')
            samples    = result.get('samples', [])
            sample_rate = result.get('sampleRate', 44100)

            # Write WAV
            _write_wav(out_path, samples, sample_rate)

            # Compute metrics inline (no scipy / librosa)
            arr      = np.array(samples, dtype=np.float32)
            rms      = float(np.sqrt(np.mean(arr ** 2))) if len(arr) > 0 else 0.0
            centroid = _spectral_centroid(samples, sample_rate)

            # Stop playback
            page.locator(f"button[onclick=\"playSnippet('{snippet}')\"]").locator('..').locator('button.stop').click()

            browser.close()
    finally:
        server.shutdown()

    # Print report
    label  = _SNIPPET_LABELS.get(snippet, snippet)
    status = 'PASS' if rms > 0.01 else 'FAIL'

    print(f'Snippet:  {snippet} ({label})')
    print(f'Duration: {duration} s')
    print(f'WAV:      {out_path}')
    print(f'RMS:      {rms:.4f}')
    print(f'Centroid: {centroid:.0f} Hz')
    print(f'Status:   {status}')

    if rms <= 0.01:
        print('FAIL: captured audio is silent')
        return 1

    return 0


# ── CLI ────────────────────────────────────────────────────────────────────────

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description='Play a strudel_debug.html snippet and write a WAV file to disk.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument('--snippet',  required=True, choices=['c1', 'c2', 'c3'],
                   help='Which snippet to play (c1=pad only, c2=pad+kick, c3=experiment)')
    p.add_argument('--duration', type=float, default=8.0,
                   help='Seconds to capture after warmup (default: 8.0)')
    p.add_argument('--out',      required=True,
                   help='Output WAV path')
    p.add_argument('--warmup',   type=float, default=3.0,
                   help='Seconds to let synth settle before capture (default: 3.0)')
    p.add_argument('--port',     type=int, default=8765,
                   help='HTTP server port (default: 8765)')
    return p.parse_args()


if __name__ == '__main__':
    args = _parse_args()
    sys.exit(capture(
        snippet  = args.snippet,
        duration = args.duration,
        out_path = args.out,
        warmup   = args.warmup,
        port     = args.port,
    ))
