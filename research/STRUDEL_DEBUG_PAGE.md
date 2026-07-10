# Strudel Debug Page — Methodology and Usage Guide

## Purpose

`strudel_debug.html` is the **ground-truth reference tool** for the Python trance
generator. It runs Switch Angel's exact Strudel synthesis code in a real browser so
we can measure its output numerically and derive authoritative parameter targets —
not guesses.

The fundamental problem it solves: when the Python generator sounds wrong, there was
previously no way to know *what the correct value should be*. This page provides
that answer. Every synthesis constant in the generator must be traceable to a
measurement made here.

```
SA's Strudel code → strudel_debug.html → Playwright measurement
                                        → numeric target values
                                        → Python generator constants
                                        → rendered WAV → verify match
```

---

## Role in the development workflow

### When to use this tool

| Trigger | Action |
|---|---|
| **Before implementing any v3 synthesis parameter** | Run the relevant SA snippet, measure the output, record the target value *before writing a line of Python* |
| **After implementing a v3 parameter** | Render the generator's WAV, compare its spectral profile against the Strudel measurement, assert match within ±10% |
| **When something in the generator sounds wrong** | Add a diagnostic snippet to the page (edit the c3 textarea), isolate the parameter, get the expected value |
| **When SA updates her prebake.strudel on GitHub** | Re-run `test_strudel_page.py` and manually compare the inlined function bodies (see §Keeping functions in sync) |

### When NOT to use this tool

- Do not open it as a listening toy without capturing measurements — every session must produce a numeric record
- Do not change a Python generator constant without first running a measurement here to establish the target
- Do not treat a passing test as proof of synthesis quality — the test only verifies audio is present; quality measurement requires the WAV capture workflow (see §Getting Strudel audio as a WAV)

---

## The measurement workflow

Standard process for any synthesis parameter decision:

```
1. Identify the SA Strudel expression (e.g. rlpf(0.5))
2. Confirm a snippet in strudel_debug.html plays it, or add one to c3
3. Run the Playwright measurement script → capture the numeric value
4. Record the target in research/analysis/switch_angel_vocabulary.md
5. Implement the parameter in the Python generator
6. Render a WAV: python trance_stream_v3.py --bars 8 --wav /tmp/check.wav
7. Run: python tools/analyse_audio.py /tmp/check.wav  (or spectrogram.py)
8. Assert the measured value matches the Strudel target ±10%
9. Commit the parameter constant, the measurement, and the evidence
```

---

## Parameter measurement recipes

Each recipe specifies exactly which snippet to use, what to modify in the textarea,
what Python code to run, and what numeric target to expect.

### a. Sidechain pump depth — `duckdepth(.6)`

**Snippet:** c2 (pad + kick)  
**What to measure:** RMS ratio of pad signal immediately after a kick onset vs immediately before.

SA's `.duckdepth(.6)` means the pad ducks to 40% of its pre-kick level on each kick
hit. The pump effect is only audible if depth ≥ 50%. v2's `SIDECHAIN_DEPTH=0.08`
produces 8% reduction — inaudible.

```python
# In test_strudel_page.py or a standalone script:
# Capture ~4 bars of c2 audio as a WAV (see §Getting Strudel audio as a WAV),
# then:
import librosa, numpy as np
y, sr = librosa.load('/tmp/strudel_c2.wav', sr=44100)
# Detect kick onsets (~steps 0,4,8,11,14 per bar at 140 BPM)
onset_frames = librosa.onset.onset_detect(y=y, sr=sr, units='samples')
for onset in onset_frames[:8]:
    pre  = y[max(0, onset - int(sr*0.05)) : onset]           # 50ms before
    post = y[onset : onset + int(sr*0.01)]                   # 10ms after
    ratio = np.sqrt(np.mean(post**2)) / (np.sqrt(np.mean(pre**2)) + 1e-9)
    print(f'duck ratio: {ratio:.3f}')  # expect ~0.40
```

**Expected:** ratio ≈ 0.40 (60% reduction)  
**v2 value:** ~0.92 (8% reduction)  
**Generator constant:** `SIDECHAIN_DEPTH` (v3)

---

### b. Trancegate breathing profile — `trancegate(1.5, 45, 1)`

**Snippet:** c1 (pad only)  
**What to measure:** RMS per 16th-note slot over 2 bars. SA's gate produces a
smooth cosine sweep, not a hard on/off. The peak-to-trough ratio across the 32
slots should exceed 5×.

```python
import librosa, numpy as np
y, sr = librosa.load('/tmp/strudel_c1.wav', sr=44100)
# 2 bars at 140 BPM = 60/140*8 = 3.43s
# 1 16th note = 60/140/4 = 0.1071s = 4725 samples at 44100
slot = int(44100 * 60 / 140 / 4)   # samples per 16th note
n_slots = 32                         # 2 bars
rms_per_slot = []
for i in range(n_slots):
    chunk = y[i*slot : (i+1)*slot]
    rms_per_slot.append(np.sqrt(np.mean(chunk**2)))
ratio = max(rms_per_slot) / (min(rms_per_slot) + 1e-9)
print(f'gate peak/trough ratio: {ratio:.1f}')  # expect > 5
# Also plot to confirm smooth sinusoidal shape, not step function
```

**Expected:** ratio > 5×, smooth variation (not stepped)  
**v2 issue:** binary LFSR gate with cosine-smoothed boundaries → hard steps, ratio ~2–3×  
**Generator constant:** `TGATE_SPEED`, gate envelope shape (v3)

---

### c. Filter cutoff positions — `rlpf(0.5)` closed, `rlpf(0.877)` open

**Snippet:** c1, with trancegate temporarily replaced by `.gain(1)` in the textarea
so the filter is sustained and measurable.

The `rlpf(x)` formula is `(x * 12)^4` Hz:
- `rlpf(0.5)` = (6)^4 = **1,296 Hz** (closed/start position)
- `rlpf(0.877)` = (10.524)^4 = **12,268 Hz** (fully open)

```python
import librosa, numpy as np
y, sr = librosa.load('/tmp/strudel_c1_nogating.wav', sr=44100)
centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]
rolloff  = librosa.feature.spectral_rolloff(y=y, sr=sr, roll_percent=0.85)[0]
print(f'mean centroid: {np.mean(centroid):.0f} Hz')  # closed: ~800-1200; open: ~2500-4000
print(f'mean rolloff:  {np.mean(rolloff):.0f} Hz')   # closed: ~1500; open: ~6000+
```

Run this twice — once with `rlpf(0.5)` and once with `rlpf(0.877)` in the textarea
— and record both values. These become the floor and ceiling for the v3 filter arc.

**Expected (closed, rlpf=0.5):** centroid ~800–1,200 Hz  
**Expected (open, rlpf=0.877):** centroid ~2,500–4,000 Hz  
**v2 issue:** filter arc starts at slider 0.65 (~5 kHz) — starts too bright  
**Generator constants:** `PAD_CUTOFF_FLOOR_HZ`, `PAD_CUTOFF_OPEN_HZ` (v3)

---

### d. lpenv filter sweep shape — `lpenv(2)`

**Snippet:** c1 with both `.trancegate(...)` and `.room(.7)` removed (paste into c3
textarea) so the per-trigger sweep is isolated and unmixed with reverb.

```python
import librosa, numpy as np
y, sr = librosa.load('/tmp/strudel_c1_lpenv_only.wav', sr=44100)
# Short-time centroid with 10ms windows
hop = int(sr * 0.01)
centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=hop)[0]
# Find first note onset, then track centroid for 300ms
onset_samples = librosa.onset.onset_detect(y=y, sr=sr, units='samples')[0]
onset_frame   = onset_samples // hop
window_frames = int(0.3 * sr / hop)   # 300ms
sweep = centroid[onset_frame : onset_frame + window_frames]
print('centroid over first 300ms:', [f'{v:.0f}' for v in sweep[::3]])
# Expect: starts low (~800 Hz), rises to base cutoff by ~frame 6 (60ms), then stable
```

**Expected:** centroid rises from ~800 Hz to base cutoff within 60 ms  
**Generator constants:** `LPENV_DURATION_S=0.06`, `LPENV_START_HZ` (v3)

---

### e. Supersaw detuning width — `unison(5).detune(.6)`

**Snippet:** c3 textarea — set rlpf high (0.9), remove trancegate, play a single
sustained note to see the harmonic spectrum clearly:

```
n("0").add(-14).scale("g:minor")
  .s("supersaw").unison(5).detune(.6)
  .rlpf(0.9).lpenv(0).room(0)
```

```python
import librosa, numpy as np
y, sr = librosa.load('/tmp/strudel_detune.wav', sr=44100)
# Take FFT of steady-state portion (skip first 100ms)
start = int(sr * 0.1)
Y = np.abs(np.fft.rfft(y[start:start+sr]))  # 1s window
freqs = np.fft.rfftfreq(sr, 1/sr)
# Find peaks near G1 (49Hz) and its harmonics
# 60 cents spread across 5 voices ≈ each voice ±0..30 cents from root
# At 49 Hz: 30 cents = 49*(2^(30/1200)-1) = 0.86 Hz, so total spread ~1.7 Hz
# At 2nd harmonic (98 Hz): spread ~3.4 Hz — easier to see in FFT
# Zoom in on 80–120 Hz range, find the 5 peaks
band = (freqs >= 80) & (freqs <= 120)
print('peak region (80-120Hz):', sorted(freqs[band][np.argsort(Y[band])[-10:]][::-1]))
```

**Expected:** 5 peaks spread across ~60 cents at each harmonic  
**Generator constant:** `DETUNE_CENTS=60`, `SAW_COUNT=5` (v3)

---

### f. Kick syncopation pattern — `.beat("0,4,8,11,14", 16)`

**Snippet:** c2 (pad + kick)

```python
import librosa, numpy as np
y, sr = librosa.load('/tmp/strudel_c2.wav', sr=44100)
# Isolate percussive component
_, perc = librosa.effects.hpss(y)
# Detect onsets
onsets = librosa.onset.onset_detect(y=perc, sr=sr, units='samples')
# Map to 16th-note grid: 1 16th = 60/140/4 s = 4725 samples
slot = int(sr * 60 / 140 / 4)
grid = sorted(set((o // slot) % 16 for o in onsets))
print(f'kick grid positions: {grid}')  # expect [0, 4, 8, 11, 14]
# Step 12 must be ABSENT (that's the four-on-floor position SA replaces)
assert 12 not in grid, "Step 12 present — not SA's pattern"
```

**Expected:** positions `[0, 4, 8, 11, 14]`, step 12 absent  
**v2 issue:** fires at `[0, 4, 8, 12]` — missing the trance anticipation hits  
**Generator constant:** `KICK_STEPS` (v3)

---

## Adding new diagnostic snippets

When investigating a parameter not covered by c1/c2/c3:

1. Open `strudel_debug.html` in the browser
2. Edit the **c3 textarea** (the "Experiment" box) — it is intentionally editable
3. Strip down to the minimum code that isolates the parameter (remove trancegate,
   reverb, and any voices not under test — make the signal as clean as possible)
4. If the snippet should be permanent, add a new `<h2>` section to the HTML and
   document it here under a "Diagnostic snippets" heading

When adding a permanent snippet, also add a recipe to this doc following the format
above: snippet contents, what to measure, expected values, generator constant name.

---

## Getting Strudel audio as a WAV file

The Playwright probe captures only RMS and spectral centroid in real time. For full
spectral analysis (`analyse_spectrum()`, `health_check.py`, MFCC distance, band
energy), you need a WAV file on disk.

**Method:** inject a `MediaRecorder` into the page, record the audio output, extract
the blob as PCM bytes, and write to disk. This is the pattern to implement in
`tools/test_strudel_page.py` as `capture_strudel_wav()`:

```python
# Pseudocode — not yet implemented; implementation is a separate task
def capture_strudel_wav(page, snippet_id, duration_s=4, out_path='/tmp/strudel_ref.wav'):
    """
    Play snippet_id for duration_s seconds, record the AudioContext output to
    a WAV file at out_path using MediaRecorder. Requires the AnalyserNode probe
    to already be injected (so all GainNodes are tapped into the analyser chain).
    """
    page.evaluate("""() => {
        const dest = getAudioContext().createMediaStreamDestination();
        // Tap the existing analyser into the MediaRecorder destination
        window.__probe._analyser.connect(dest);
        window.__recChunks = [];
        window.__recorder  = new MediaRecorder(dest.stream, { mimeType: 'audio/webm' });
        window.__recorder.ondataavailable = e => window.__recChunks.push(e.data);
        window.__recorder.start();
    }""")
    page.locator(f'button[onclick="playSnippet(\\'{snippet_id}\\')"]').click()
    time.sleep(duration_s)
    page.evaluate("() => window.__recorder.stop()")
    time.sleep(0.5)  # let ondataavailable flush
    # Extract blob bytes via FileReader, convert webm → wav with ffmpeg or pydub
    # ... (implementation detail — write to out_path as 44100 Hz mono WAV)
```

Once you have the WAV, run the standard analysis chain:

```bash
python tools/analyse_audio.py /tmp/strudel_ref.wav
python tools/spectrogram.py   /tmp/strudel_ref.wav
python tools/health_check.py  /tmp/strudel_ref.wav
```

And compare against the generator's output:

```python
from tools.midi_compare import compare_midi
result = compare_midi('strudel_ref.mid', 'generator_output.mid', bpm=140)
print(result['rhythm_similarity'])   # target > 0.8
print(result['pitch_similarity'])    # target > 0.8
```

---

## Keeping the inlined SA functions in sync with prebake.strudel

The page inlines `trancegate`, `rlpf`, and `o` directly rather than loading the full
prebake. If SA updates her GitHub, the inline versions may drift.

**Check command:**

```bash
curl -s https://raw.githubusercontent.com/switchangel/strudel-scripts/main/prebake.strudel \
  | grep -A8 "register('trancegate'\|register('rlpf'\|register('o',"
```

Compare the output against the `SA_FUNCTIONS` block in `strudel_debug.html`.

If they differ:
1. Update `SA_FUNCTIONS` in the HTML
2. Re-run `python tools/test_strudel_page.py` — all 13 checks must pass
3. Add a note to the Debugging Sessions Log below with the change and date

**What the test catches and what it misses:**

The automated test will catch functional regressions (silence, missing sounds,
getTrigger errors). It will **not** catch subtle parameter changes in the function
bodies — e.g. if SA changes `trancegate`'s density formula. Manual review of the
function source is required after any sync.

---

## Architecture

### Why not load the full prebake?

SA's `prebake.strudel` contains `$:` top-level patterns (e.g. drum loops, synth demos)
that start playing immediately when evaluated. Loading the full file via
`window.evaluate(prebakeText)` causes:

- Hundreds of "Can't do arithmetic on control pattern" warnings per second
- Spurious audio output that pollutes RMS measurements
- Race conditions with our own snippet evaluation

**Fix:** inline only the three functions we actually use. Their current definitions
are captured verbatim from the prebake (grep for `register('trancegate'`, etc.).

### SA custom functions (as of 2026-07-10)

```js
register('trancegate', (density, seed, length, x) => {
  density = reify(density).add(.5);
  return x.struct(rand.mul(density).round().seg(16).rib(seed, length)).fill().clip(.7);
});

register('rlpf', (x, pat) => {
  // NOTE: use reify(x).mul(...) not pure(x).mul(...)
  // pure() wraps an already-reified Pattern in a second layer, breaking .mul/.pow
  return pat.lpf(reify(x).mul(12).pow(4));
});

register('o', (orbit, pat) => {
  pat = pat.orbit(orbit);
  if (window.mutedOrbits.includes(orbit))  return pat.hush();
  if (!window.soloedOrbits.length || window.soloedOrbits.includes(orbit)) return pat;
  return pat.hush();
});
```

### AudioWorklet warmup

superdough (the Strudel audio engine) loads its WebAudio worklets
(`supersaw-oscillator`, etc.) **lazily on first use**. If the first real play
fires before `audioWorklet.addModule()` completes, the node constructor throws
silently and the first few scheduler cycles produce no sound.

Fix: evaluate a silent `s("supersaw").gain(0)` at load time to trigger worklet
registration, then poll for `[superdough] ready` in the console before declaring
the page ready.

In **headless Chromium** (Playwright), `addModule()` sometimes takes longer than
the poll window — the warmup times out but audio still works because superdough
retries internally. The test accounts for this (see Verdict section).

---

## Automated Test

`tools/test_strudel_page.py` is the primary regression test. Run it after any
change to the page or whenever SA's prebake is updated.

```bash
# Requires a local HTTP server:
python -m http.server 8765 --directory research

# In another terminal:
python tools/test_strudel_page.py
```

Expected output: **13 passed, 0 failed**

### Probe strategy

Inject an `AnalyserNode` side-tap that connects to **every** `GainNode` created by
the `AudioContext`. This captures the full mixed output regardless of how superdough
routes its AudioWorklet signals.

```
  GainNode → AnalyserNode → destination
  GainNode ↗
  GainNode ↗
```

The probe polls the analyser every 100 ms via `setInterval`. When the AudioContext
is suspended (after Stop), the probe returns 0 rather than the stale last buffer.

### Verdict criteria (per snippet)

| Check | Criterion | Notes |
|---|---|---|
| PLAY | maxRMS > 0.05 AND sustained > 25% | Zeros are trancegate closing — correct |
| STOP | post-stop maxRMS < 0.01 | AudioContext suspended on Stop — cuts reverb tail |
| NO PAGE ERROR | error div empty | Any JS exception surfaced here |
| MISSING SOUNDS | no `[getTrigger] error` in console | Sample banks not loaded = silent failure |
| DISTINCT | centroid spread > 3% (c1 vs c2), > 0.5% (c1 vs c3) | Catches if all snippets produce identical audio |

### Console monitoring — critical

Strudel logs functional failures as `[log]` type, not `[error]`. The test explicitly
scans all console messages. Any `[getTrigger] error: sound X not found` means a
sound is silently dropping every scheduler tick — this is a FAIL regardless of RMS.

---

## Debugging Sessions Log

### 2026-07-10 — Initial debug session

**Symptom:** page shows "Playing ▶" but no sustained sound; automated test FAIL.

**Diagnosis steps:**

1. Ran `test_strudel_audio.py` (ScriptProcessorNode probe) → maxRMS 0.06, rmsLast5
   all zeros. Sound starts then immediately stops.

2. Opened headed browser, captured all console output → revealed two key errors:
   ```
   [getTrigger] error: AudioWorkletNode cannot be created:
     'supersaw-oscillator' is not defined in AudioWorkletGlobalScope.
   [warn]: Can't do arithmetic on control pattern.
   ```

3. Isolated "arithmetic" warning: appeared even with bare `n("0")` — confirmed as
   Strudel 1.3.0 internal, not our code.

4. Switched probe from ScriptProcessorNode to AnalyserNode side-tap on all gain
   nodes → maxRMS jumped to 0.51, sustained.

**Root causes:** ScriptProcessorNode tapped one gain node, missing superdough's
worklet audio path. Full prebake eval launched SA's demo `$:` patterns.

**Fixes:** AnalyserNode probe; inlined custom functions only; superdough warmup polling.

---

### 2026-07-10 — Real-browser AudioContext suspension

**Symptom:** Play button does nothing in real browser. No error in status div.

**Root cause:** `AudioContext` created during `initStrudel()` (no user gesture) stays
`suspended`. `window.evaluate()` does not call `resume()`. Only a click handler can.

**Fix:** `await getAudioContext().resume()` at the top of `playSnippet()`.

**Lesson:** never use `--autoplay-policy=no-user-gesture-required` in Playwright
tests — it masks this entire class of bug.

---

### 2026-07-10 — RolandTR909 bank not loaded

**Symptom:** snippet c2 kick silently absent. Console:
```
[getTrigger] error: sound RolandTR909_bd not found! Is it loaded?
```

**Root cause:** `initStrudel()` does not pre-load sample banks. `bank("RolandTR909")`
requires a prior `samples()` call with the drum-machines index URL.

**Fix:** `await samples('https://strudel.b-cdn.net/tidal-drum-machines.json')` added
to init, before `SA_FUNCTIONS` evaluation.

**Detection failure:** test was passing because pad audio alone hit the RMS threshold.
The test was not scanning for `[getTrigger]` console errors.

**Fix to test:** added explicit `getTrigger` error detection to `test_strudel_page.py`.

---

## Known Issues (non-blocking)

- **"Can't do arithmetic on control pattern"** — fires ~10 times per play on bare
  `n()` patterns. Strudel 1.3.0 internal. Does not affect audio output.
- **Worklet warmup timeout in headless** — `[debug] worklet warmup timed out`
  appears in test logs. Audio still plays correctly; superdough retries internally.
