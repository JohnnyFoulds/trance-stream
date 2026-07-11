# Capturing Strudel Audio as a WAV File — Methodology

## Symptom

The existing Playwright test harness (`tools/test_strudel_page.py`,
`tools/test_strudel_wav_analysis.py`) captures only RMS amplitude and spectral centroid
scalars in real time.  There was no way to write the Strudel output to a WAV file on disk
without manually running a separate HTTP server and then manually calling
`window.__captureWav()` from a test script.  The methodology doc
`research/STRUDEL_DEBUG_PAGE.md` listed `capture_strudel_wav()` as pseudocode under
"Getting Strudel audio as a WAV file" — it was never implemented as a runnable tool.

The gap mattered because the following analyses require a WAV file, not a scalar:

- Trancegate gate profile (RMS per 16th-note slot over 2 bars)
- Sidechain pump depth (RMS ratio pre/post kick onset)
- Filter cutoff position (spectral centroid at rlpf=0.5 vs rlpf=0.877)
- lpenv sweep shape (short-time centroid over 300 ms after note onset)
- MFCC distance between Strudel reference and Python generator output

---

## Diagnosis

Traced `tools/test_strudel_wav_analysis.py` — it already calls
`page.evaluate("() => window.__captureWav(4)")` and uses `_write_wav()` to persist
the result.  The `window.__captureWav(seconds)` function is fully implemented in
`research/strudel_debug.html` (lines 223–257).

The only missing piece was a standalone CLI script that:

1. Starts its own HTTP server (no manual `python -m http.server` required)
2. Accepts `--snippet`, `--duration`, `--out`, `--warmup`, `--port` arguments
3. Prints a structured metrics report (RMS, centroid, PASS/FAIL)

---

## Root Cause

`capture_strudel_wav()` in `STRUDEL_DEBUG_PAGE.md` was documented as pseudocode only;
no runnable tool existed.  Researchers wishing to capture a reference WAV had to
assemble the code themselves from `test_strudel_wav_analysis.py` fragments.

---

## Fix Applied

Created `tools/capture_strudel_wav.py` — a self-contained CLI tool that:

1. Starts an embedded `socketserver.TCPServer` serving `research/` in a daemon thread
2. Launches headless Chromium via Playwright (no autoplay bypass flags — see constraints)
3. Waits for `#status` to contain "Ready" (timeout 30 s)
4. Clicks the snippet's Play button (which also resumes the suspended AudioContext)
5. Waits `--warmup` seconds for the synth to settle
6. Calls `window.__captureWav(duration_s)` and retrieves the Float32Array samples
7. Writes 16-bit mono PCM WAV to `--out`
8. Computes and prints RMS and spectral centroid inline (no librosa/scipy dependency)
9. Asserts RMS > 0.01; prints PASS or FAIL
10. Stops the snippet and shuts down the HTTP server

The `_write_wav()` helper is copied verbatim from `test_strudel_wav_analysis.py` to
keep the two tools consistent.  The spectral centroid is computed with a single FFT
window using `numpy.fft` only — no heavy import at startup.

---

## How `window.__captureWav()` Works

The function is implemented in `research/strudel_debug.html` at the bottom of the
`<script>` block.

**Setup (runs at page load):**

`window.__capturerSetup()` monkey-patches the `AudioContext` constructor.  When Strudel
calls `new AudioContext()`, the patched constructor:

1. Creates the real AudioContext (`_origAC`)
2. Creates an `AnalyserNode` with `fftSize = 2048` and connects it to the destination
3. Patches `ac.createGain()` so every GainNode created by Strudel connects to the
   AnalyserNode — this taps the full mixed output regardless of superdough's internal routing
4. Stores the AnalyserNode in `window.__captureAnalyser` and the context in
   `window.__captureAC`

This setup runs before `initStrudel()` is called, so the AnalyserNode is in place when
Strudel creates the AudioContext.

**Capture (`window.__captureWav(seconds)`):**

Returns a Promise.  Polls the AnalyserNode with `setInterval` at
`(fftSize / sampleRate) * 1000` ms intervals — one poll per audio frame.  Each poll
calls `analyser.getFloatTimeDomainData(buf)` and appends the frame to a buffer.  When
`totalSamples >= targetSamples`, the interval is cleared, all frames are concatenated
into a single `Float32Array`, and the Promise resolves with
`{ samples: Array.from(flat), sampleRate: sr }`.

Playwright's `page.evaluate()` awaits the Promise and transfers the data to Python as
a plain dict with a list of floats.

**Important detail:** the AnalyserNode is mono (single channel).  The captures are
therefore mono regardless of the stereo width of the Strudel synthesis.  This is
sufficient for all current analysis tasks (centroid, RMS, onset detection, gate profile).

---

## Known Limitations

| Limitation | Impact | Mitigation |
|---|---|---|
| Mono capture only | Stereo width not measurable | All current analyses are mono-compatible |
| Warmup latency | BPM-dependent gate phase | 3 s default is sufficient: at 140 BPM, one bar = 1.71 s, so 3 s covers at least 1.75 full bars — enough for the trancegate to complete at least 1 full cycle at 1.5 cycles/bar |
| AudioContext suspended without user gesture | No sound until click | Handled: `playSnippet()` calls `ctx.resume()` inside the Playwright `.click()` handler |
| AnalyserNode reads stale buffer when context is suspended | Non-zero data after stop | Stop is called after capture, not before — irrelevant to capture quality |
| `__captureWav` polls at frame rate, not sample rate | ~46 ms time resolution per frame | For 8 s captures this is negligible; shorter captures may have coarser resolution |
| No network access in some CI environments | `strudel.b-cdn.net` sample bank load fails | Run with network access; kick sample (c2) requires the tidal-drum-machines CDN |

---

## How to Verify a Capture Is Valid

A capture is valid if all of the following are true:

1. **RMS > 0.01** — the script asserts this and prints PASS/FAIL
2. **Centroid 200–3000 Hz** — expected range for SA's pad with `rlpf(0.5)`
3. **No silence at start** — plot the waveform; the trancegate should be audible from
   the first second (after 3 s warmup the gate has cycled at least once)
4. **No getTrigger errors in console** — printed by Playwright's console handler if
   a sample bank failed to load

Quick verification from the WAV::

    python tools/analyse_audio.py research/reference_audio/sa_trancegate_c1_8s.wav

Expected output (approximate): peak > 0.1, rms > 0.01, sub band energy > 0.

---

## Exact Commands to Reproduce Every Audit Capture

All commands run from the repository root.

### c1 — Pad only (G minor, trancegate reference)

```bash
python tools/capture_strudel_wav.py \
    --snippet c1 \
    --duration 8 \
    --warmup 3 \
    --out research/reference_audio/sa_trancegate_c1_8s.wav
```

Expected output::

    Snippet:  c1 (pad only)
    Duration: 8.0 s
    WAV:      research/reference_audio/sa_trancegate_c1_8s.wav
    RMS:      ~0.08
    Centroid: ~1000 Hz
    Status:   PASS

### c2 — Pad + kick (G minor, sidechain reference)

```bash
python tools/capture_strudel_wav.py \
    --snippet c2 \
    --duration 8 \
    --warmup 3 \
    --out research/reference_audio/sa_sidechain_c2_8s.wav
```

Expected output::

    Snippet:  c2 (pad + kick)
    Duration: 8.0 s
    WAV:      research/reference_audio/sa_sidechain_c2_8s.wav
    RMS:      ~0.10
    Centroid: ~900 Hz
    Status:   PASS

### c3 — Experiment (A minor)

```bash
python tools/capture_strudel_wav.py \
    --snippet c3 \
    --duration 8 \
    --warmup 3 \
    --out research/reference_audio/sa_experiment_c3_8s.wav
```

### Alternative: run the HTTP server manually (original workflow)

If the embedded server conflicts with a running server on port 8765::

    cd /Users/johannes/switch-angel/trance-stream/research && python -m http.server 8765 &
    python tools/capture_strudel_wav.py --snippet c1 --duration 8 \
        --out research/reference_audio/sa_trancegate_c1_8s.wav
    python tools/capture_strudel_wav.py --snippet c2 --duration 8 \
        --out research/reference_audio/sa_sidechain_c2_8s.wav

---

## Constraints

The following flags are **explicitly prohibited** in all Playwright calls in this project
(CLAUDE.md):

- `--autoplay-policy=no-user-gesture-required`
- `--disable-web-security`

These bypass AudioContext suspension rules and mask the real failure mode (no user-gesture
= no resume = no audio).  The script relies on `playSnippet()`'s click handler to resume
the AudioContext, which is the correct path and mirrors real browser behaviour.

---

## References

Microsoft. (2020). *Playwright* (Version 1.x) [Software]. Microsoft.
https://playwright.dev

World Wide Web Consortium. (2021). *Web Audio API*. W3C Recommendation.
https://www.w3.org/TR/webaudio/
