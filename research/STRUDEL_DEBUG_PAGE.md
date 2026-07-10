# Strudel Debug Page — Methodology and Debugging Notes

## Purpose

`strudel_debug.html` is a standalone test harness for verifying that Switch Angel's
exact Strudel synthesis code produces the expected audio. It loads only the
three SA custom functions we use (`trancegate`, `rlpf`, `.o()`), then runs her
literal pad/kick patterns from video `GWXCCBsOMSg`. This gives us **ground truth**
for synthesis parameter targets before porting them into the Python generator.

The chain is:

```
SA's Strudel code → strudel_debug.html → Playwright RMS measurement
                                        → parameter targets for trance_stream_v2.py
```

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

### 2026-07-10 — RolandTR909 bank not loaded (third session)

**Symptom:** snippet c2 (pad + kick) produces no kick sound. Console shows repeated:
```
[getTrigger] error: sound RolandTR909_bd not found! Is it loaded?
```

**Diagnosis:** `initStrudel()` loads the Strudel runtime but does NOT pre-load any
sample banks. `bank("RolandTR909")` resolves bank names against a sample index that
must be fetched separately. Without it, every kick trigger silently fails.

**Root cause:** `samples()` must be called with the drum-machines index URL before
any `bank()` call. The correct URL (used by strudel.cc itself) is:
`https://strudel.b-cdn.net/tidal-drum-machines.json`

**Fix:** added `await samples('https://strudel.b-cdn.net/tidal-drum-machines.json')`
to the init sequence, before `SA_FUNCTIONS` evaluation.

**Detection failure:** the automated test was not checking for `getTrigger` errors
in the console. These log as `[log]` type (not `[error]`), so generic error
filtering missed them entirely. The test was passing because c2 still produces
pad audio (the supersaw) even when the kick is silent — maxRMS was > threshold.

**Fix to test:** added explicit `getTrigger` error detection to `test_strudel_page.py`.
These are now caught, deduped, and reported as `MISSING SOUNDS: FAIL`.

**Lesson:** any `[getTrigger] error` in the console means a sound is silently
dropping every scheduler tick. **Always scan the full console output for this
pattern**, not just JS `[error]` type messages.

---

## Automated Test

`tools/test_strudel_audio.py` verifies the page produces audio without human ears.

### Probe strategy

The original approach (ScriptProcessorNode on the first gain node) fails because
superdough's AudioWorklet output bypasses the gain node we tapped.

**Correct approach:** inject an `AnalyserNode` side-tap that connects to
**every** gain node created by the AudioContext. The AnalyserNode does not affect
routing — it reads the signal without breaking the chain.

```
  GainNode → AnalyserNode → destination
  GainNode ↗
  GainNode ↗
```

Poll the analyser every 100 ms via `setInterval` inside the injected patch.

### Verdict criteria

| Condition | Verdict |
|---|---|
| maxRMS > 0.05 AND sustained > 25% | PASS |
| maxRMS > 0.05 but not sustained | PARTIAL — check trancegate density |
| maxRMS ≤ 0.05 | FAIL |

The zeros in the RMS stream are the **trancegate rhythmically closing** — this is
correct behaviour, not silence. A 75% sustained rate is expected at `density=1.5`.

### How to run

```bash
# In one terminal:
python -m http.server 8765 --directory research

# In another:
python tools/test_strudel_audio.py
```

---

## Debugging Sessions Log

### 2026-07-10 — Initial debug session

**Symptom:** page shows "Playing ▶" but no sustained sound; automated test reported
FAIL.

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
   Strudel-internal, not our code.

4. Checked whether SA custom functions were registered after page load:
   ```js
   typeof window.trancegate  // "undefined"
   ```
   They should be `"function"` if the prebake eval registered them. Confirmed
   the prebake was being eval'd correctly but `window.trancegate` is not set by
   `register()` in Strudel 1.x — `register()` adds to Strudel's internal scope,
   not `window`. So the check was wrong, not the registration.

5. Switched probe from ScriptProcessorNode to AnalyserNode side-tap on all gain
   nodes → maxRMS jumped to 0.51, sustained. Confirmed audio was working all along;
   the original probe was on the wrong node.

6. Confirmed the "arithmetic" warning fires on bare `n("0")` with no custom
   functions at all — it is a Strudel 1.3.0 internal issue, not a blocker.

**Root causes:**
- ScriptProcessorNode probe tapped one gain node, missing superdough's worklet
  audio path entirely.
- Full prebake eval launched demo `$:` patterns causing noise in measurements.

**Fixes applied:**
- Replaced probe with AnalyserNode side-tap on every gain node.
- Replaced full prebake eval with three inlined custom function definitions.
- Added superdough-ready warmup polling before declaring page ready.

---

### 2026-07-10 — Real-browser AudioContext suspension (second session)

**Symptom:** pressing Play in a real browser produces nothing. Console shows
`[superdough] ready` then silence. No error in the status div.

**Diagnosis:**
- Playwright test was using `--autoplay-policy=no-user-gesture-required` which
  bypasses the browser's AudioContext autoplay policy. This masked the real failure.
- Removed the flag and re-ran: confirmed `AudioContext.state === 'suspended'` even
  after clicking Play, maxRMS = 0.

**Root cause:** `AudioContext` is created during `initStrudel()` (page load, no
user gesture). Browsers keep it `suspended` until `resume()` is called from
within a user-gesture event handler. `window.evaluate()` does not call `resume()`.

**Fix:** call `getAudioContext().resume()` at the top of `playSnippet()`, which
runs inside the button's `onclick` — a genuine user gesture. After the fix,
AudioContext transitions `suspended → running` on click, maxRMS 0.51.

**Lesson:** never use `--autoplay-policy=no-user-gesture-required` or any other
flag that relaxes browser security policies in Playwright tests. The test must
reflect real browser behaviour or it will miss exactly this class of bug.

---

## Known Issues (non-blocking)

- **"Can't do arithmetic on control pattern"** — fires ~10 times per play on bare
  `n()` patterns. Strudel 1.3.0 internal issue. Does not affect audio output.
- **Worklet warmup timeout in headless** — `[debug] worklet warmup timed out`
  appears in test logs. Audio still plays correctly; superdough retries internally.
  The test correctly reports PASS regardless.
