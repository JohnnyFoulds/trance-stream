# Analysis Tools Test Methodology

**Date**: 2026-07-10
**Branch**: `sidequest/pluck-arp-analysis`
**Scope**: Reverse-engineering and audio analysis tools in `tools/`

---

## Purpose

The synthesis pipeline (`synth/`, `instruments/`, `song/`) is already covered by pytest.
The reverse-engineering tools — `analyse_timbre.py`, `extract_drum_pattern.py`,
`audio_to_midi.py`, `analyse_audio.py` — have no tests. This is a correctness risk:
if these tools silently return wrong parameters, all synthesis built from their output
is wrong with no error signal. A tool that measures the wrong oscillator type or
mis-snaps the drum grid will cause us to build the wrong sound without knowing why.

This document defines the strategy, ground truth approach, acceptance thresholds,
and run instructions for the new test suite in `tests/test_tools/`.

---

## Scope

| Tool | Covered by this suite | Notes |
|---|---|---|
| `tools/analyse_timbre.py` | Yes — `test_analyse_timbre.py` | Oscillator classification, ADSR, portamento |
| `tools/extract_drum_pattern.py` | Yes — `test_extract_drum_pattern.py` | Grid snap, phase anchor, alignment error |
| `tools/audio_to_midi.py` | Yes — `test_audio_to_midi.py` | PYIN accuracy, rhythm grid |
| `tools/analyse_audio.py` | Yes — `test_analyse_audio.py` | Band energy, crest factor, no clipping |
| `synth/`, `instruments/`, `song/` | Already covered | `tests/test_synth/`, `tests/test_instruments.py`, `tests/test_song.py` |
| `research/strudel_debug.html` | Already covered | `tools/test_strudel_page.py` (Playwright) |
| Full round-trip (synth → analysis) | Yes — `test_roundtrip.py` | Closed loop, no Demucs required |
| Demucs pipeline | Yes — `test_pipeline_demucs.py` | `pytest.mark.slow` — excluded by default |
| Strudel → WAV → analysis | Yes — `tools/test_strudel_wav_analysis.py` | Playwright, requires HTTP server |

---

## Test levels

### Level 1 — Unit tests (fast, no file dependencies)

**File**: `tests/test_tools/test_analyse_timbre.py`, `test_extract_drum_pattern.py`,
`test_audio_to_midi.py`, `test_analyse_audio.py`

Synthetic WAV files are generated in memory using numpy and written to `tmp_path`
(pytest's temporary directory fixture). No network, no downloads, no pre-existing
audio files except where noted (MIDI files already committed to the repo).

Tests cover:
- Each tool's public API with known-property inputs
- Edge cases: silence, no onsets, signals below fmin
- Internal helper functions (imported via private names) where the logic is complex
  enough to warrant isolated testing (oscillator classifier, grid snapper)

### Level 2 — Integration / round-trip (no Demucs)

**File**: `tests/test_tools/test_roundtrip.py`

The synthesis pipeline renders audio with known parameters. The analysis tools are
run on that audio. The test asserts that the tools recover parameters consistent
with what was rendered. This is the closed loop that validates the tools end-to-end
without requiring any reference audio file or external model.

### Level 3 — Full pipeline with Demucs

**File**: `tests/test_tools/test_pipeline_demucs.py`

Marked `@pytest.mark.slow`. Excluded from the default `pytest` run. Requires
`pip install -r requirements-ml.txt` (~2GB PyTorch + ~1GB Demucs model on first run).

Validates that Demucs stem separation → analysis → MIDI gives plausible results
when run on a full trance_stream render.

### Level 4 — Strudel WAV capture (Playwright)

**File**: `tools/test_strudel_wav_analysis.py`

Not a pytest file. Run standalone. Requires a Chromium browser and a local HTTP
server on port 8765 serving the `research/` directory.

Validates the full circle: Strudel generates audio → Python captures it as a WAV
via a `ScriptProcessorNode` tap injected into `strudel_debug.html` → analysis tools
run on the WAV → measurements match known SA synthesis parameters.

---

## Ground truth strategy

The analysis tools must be testable without reference audio. The Python synth
provides this: it generates deterministic WAV files from known parameters, and is
itself well-tested. A sawtooth at 440 Hz with a 1000 Hz LPF applied is a ground truth
signal whose expected analysis results are known exactly. If `analyse_timbre.py`
classifies it as `"sine"`, the test fails — and the bug is in the tool, not the signal.

```
Python synth (known params)
     │  render_bars() / oscillators.sawtooth() / drums.kick() → WAV
     ▼
Analysis tools
(analyse_timbre / extract_drum_pattern / audio_to_midi / analyse_wav)
     │  measured params
     ▼
pytest assert(measured ≈ known, tolerance=±threshold)
```

---

## Strudel WAV capture path

The Strudel debug page (`research/strudel_debug.html`) generates audio entirely
within a WebAudio `AudioContext`. Python cannot access the audio buffer directly.
To make the Strudel output testable with the Python analysis tools, a
`ScriptProcessorNode` tap is added to `strudel_debug.html`:

```javascript
window.__captureWav = function(seconds) {
    return new Promise(resolve => {
        const bufferSize = 4096;
        const processor = audioContext.createScriptProcessor(bufferSize, 1, 1);
        const samples = [];
        processor.onaudioprocess = function(e) {
            const input = e.inputBuffer.getChannelData(0);
            samples.push(...input);
            if (samples.length >= seconds * audioContext.sampleRate) {
                processor.disconnect();
                resolve(new Float32Array(samples.slice(0, seconds * audioContext.sampleRate)));
            }
        };
        audioContext.destination.channelCount = 1;
        // Tap from master gain or destination
        masterGain.connect(processor);
        processor.connect(audioContext.destination);
    });
};
```

`ScriptProcessorNode` is deprecated (MDN Web Docs, 2024) but is universally
supported in Chromium. `AudioWorkletNode` would require cross-origin isolation
headers (`Cross-Origin-Opener-Policy: same-origin`) on the HTTP server, which is
unnecessary complexity for a local test script.

From the Playwright test, the captured `Float32Array` is decoded and written as a
WAV file using Python's `wave` module, then passed to the analysis tools.

---

## Acceptance thresholds

These tolerances reflect real measurement uncertainty in the analysis algorithms,
not implementation sloppiness. They were derived from:
- PYIN pitch detection accuracy: ±0.1 semitone on clean monophonic audio
  (Mauch & Dixon, 2014)
- FFT-based filter cutoff estimation: inherent resolution limited by bin width;
  18dB threshold detection has ±log(1.5) octave accuracy on realistic signals
- Spectral flux onset detection timing: hop_length=256 / 44100 Hz = 5.8ms per frame;
  30ms allows for 5 frames of timing slop

| Measurement | Threshold | Rationale |
|---|---|---|
| Oscillator type | correct categorical label | Binary pass/fail |
| Oscillator confidence | ≥ 0.8 | Confident classification |
| Filter cutoff | within ×1.5 of true value | log-space ±50%: adequate for synthesis |
| Portamento rate | ±33% of true rate | PYIN frame resolution limits precision |
| Pitch detection (dominant note) | ±1 semitone | PYIN guarantee on clean audio |
| Drum grid alignment error | < 30ms | < one quarter of a 16th note at 138 BPM |
| Spectral centroid (round-trip) | within SA reference range 425–929 Hz | From `targets.json` |
| Crest factor | 1.5 – 12.0 | Trance target range |
| Peak level | < 0.99 | No clipping |

---

## How to run

```bash
# Unit + integration tests (no Demucs, ~30–60s)
cd /path/to/trance-stream
pytest tests/test_tools/ -v

# All slow tests including Demucs pipeline (~5–10 min, first run downloads models)
pytest tests/test_tools/ -m slow -v

# Full test suite excluding Demucs (fast)
pytest tests/ -v --ignore=tests/test_tools/test_pipeline_demucs.py

# Strudel WAV analysis test (requires HTTP server on :8765)
python -m http.server 8765 --directory research &
python tools/test_strudel_wav_analysis.py
# Expected: "ALL PASS" + exit code 0
```

---

## References

Mauch, M., & Dixon, S. (2014). PYIN: A fundamental frequency estimator using
probabilistic threshold distributions. *2014 IEEE International Conference on
Acoustics, Speech and Signal Processing (ICASSP)*, 659–663.
https://doi.org/10.1109/ICASSP.2014.6853678

de Cheveigné, A., & Kawahara, H. (2002). YIN, a fundamental frequency estimator
for speech and music. *The Journal of the Acoustical Society of America*, *111*(4),
1917–1930. https://doi.org/10.1121/1.1458024

McFee, B., Raffel, C., Liang, D., Ellis, D. P. W., McVicar, M., Battenberg, E.,
& Nieto, O. (2015). librosa: Audio and music signal analysis in Python.
*Proceedings of the 14th Python in Science Conference*, 18–25.
https://doi.org/10.25080/Majora-7b98e3ed-003

Bello, J. P., Daudet, L., Abdallah, S., Duxbury, C., Davies, M., & Sandler, M. B.
(2005). A tutorial on onset detection in music signals. *IEEE Transactions on Speech
and Audio Processing*, *13*(5), 1035–1047. https://doi.org/10.1109/TSA.2005.851998
