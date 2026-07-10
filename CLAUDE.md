# Claude Code Instructions — trance-stream

## Documentation and reproducibility: write everything down

**Every non-trivial investigation, fix, or research finding must be documented in a
Markdown file in the repo before the session ends.**

This is not optional. If we ever had to repeat this work from scratch, the doc
should make it possible without re-doing the diagnosis. The standard is:

- **What was the symptom** (exact error messages or test output)
- **How we diagnosed it** (step-by-step: commands run, checks made, what each
  step revealed)
- **Root cause** (precise, not vague)
- **Fix applied** (with the reasoning — why this fix and not alternatives)
- **Known non-blocking issues** (things that still print warnings but don't break
  anything, and why they're harmless)
- **How to reproduce / run** the test or tool again

### Where docs live

| Type | Location |
|---|---|
| Browser/JS tool methodology | `research/<TOOL_NAME>.md` |
| Audio analysis methodology | `research/analysis/<NAME>.md` |
| Architecture decisions | `docs/decisions/` |
| Tool usage / CLI reference | inline in the tool file as module docstring |

### Citation requirement — APA 7th edition

**Any algorithm, model, dataset, or external technique referenced in a research document
must be cited in APA 7th edition format.** This is non-negotiable.

Format for journal articles:
```
Author, A. A., & Author, B. B. (Year). Title of article. Journal Name, Volume(Issue), pages. https://doi.org/xxx
```
Format for conference papers:
```
Author, A. A. (Year). Title of paper. In Proceedings of Conference Name (pp. x–x). Publisher. https://doi.org/xxx
```
Format for software/datasets:
```
Author, A. A. (Year). Name of software (Version x.x) [Software]. Publisher. URL or DOI
```

Required for (non-exhaustive list): PYIN, YIN, Demucs, HTDemucs, librosa, Karplus-Strong,
Krumhansl-Schmuckler, spectral flux, MUSDB18, any neural network model used for analysis.

### Artifacts belong in the repo

Any file referenced in methodology docs must be committed to the repo alongside
the doc. Do not leave essential artifacts in `/tmp`, job scratch dirs, or
`~/.claude/jobs/`. Move them:
- HTML test pages → `research/`
- Python test scripts → `tools/`
- Reference audio clips used for measurement → `research/reference_audio/`

---

## Testing principle: no excuses for untested work

**Never ask the user to test something you can verify yourself first.**

Before reporting a feature as working — especially anything involving audio, visual output, or browser behavior — build an automated test and run it. Only involve the user once you have evidence it works.

This applies universally:
- **Audio output**: use Python `playwright` + a patched `AudioContext` to measure RMS amplitude. Non-zero RMS (> 0.001) confirms sound is being generated. See `tools/test_strudel_audio.py` for the pattern.
- **Synthesis quality**: every perceptual property has a measurable correlate. Spectral centroid, rolloff, RMS envelope, zero-crossing rate, pitch trajectory — measure them with `librosa` or `scipy`. "I can't listen like a human" is not an acceptable reason to skip measurement.
- **Browser UI**: use `playwright` to click buttons, read DOM state, and capture console errors. If the status says "Playing" but RMS is zero, it's broken. **Never** use `--autoplay-policy=no-user-gesture-required` or `--disable-web-security` in Playwright — these bypass AudioContext suspension rules and mask real failures. Tests must run with default Chromium flags.
- **Monitor the full console — all message types.** Strudel logs functional failures as `[log]` type, not `[error]`. Specifically: `[getTrigger] error: sound X not found` means a sample is silently dropping every tick. These will not be caught by filtering on `m.type === 'error'` alone. Every test must scan all console messages for `getTrigger` errors and treat them as FAIL. Add `[strudel-debug]` prefixed log statements to every significant code path in the page so the console tells a complete story of what happened.
- **Waveform shape**: render a short clip, plot the spectrogram or waveform, compare against a reference measurement. If you can't generate the reference, measure the existing output and report the numbers.

**Workflow**:
1. Implement the change.
2. Write and run an automated test that produces a measurable verdict (PASS/FAIL with numbers).
3. If PASS: report to the user with the evidence.
4. If FAIL: iterate — do not ask the user to test a broken thing.

## Synthesis targets

This project synthesises Switch Angel's trance style. All parameters should be traceable to measurements from her YouTube videos or her published code at github.com/switchangel/strudel-scripts.

- `trancegate`, `rlpf`, `.o()` are SA custom functions from `prebake.strudel` — not in standard Strudel.
- `rlpf(x)` maps slider 0–1 to Hz via `(x * 12)^4`. One argument only.
- Pad fundamental: ~48Hz (G1), matching SA's `n("0").add(-14).scale("g:minor")`.
- Kick: TR-909 measurements — 285→50Hz pitch sweep, tau=31ms, decay_s=0.12.

### The strudel debug tool is the authoritative source for parameter targets

**Before setting any synthesis constant in the Python generator, measure it from SA's
actual Strudel code running in `research/strudel_debug.html`.** Do not derive
parameter values from the OCR'd vocabulary doc or the feature spec alone — those are
secondary sources. The debug page runs the real code.

The full workflow (when to use it, how to measure each parameter, how to compare
against the generator's output) is documented in `research/STRUDEL_DEBUG_PAGE.md`.

Priority parameters still to be measured and matched (in order of perceptual impact):
1. Sidechain pump depth — `duckdepth(.6)` → expect duck ratio ~0.40; v2 has 0.08
2. Trancegate breathing — smooth cosine, peak/trough > 5×; v2 uses binary LFSR
3. Filter floor — `rlpf(0.5)` → centroid ~800–1,200 Hz; v2 starts at ~5 kHz
4. Kick pattern — steps `[0,4,8,11,14]`; v2 uses `[0,4,8,12]`
5. lpenv sweep shape — centroid rises over 60 ms per trigger

## No sample playback

We do not use downloaded audio samples as playback assets in the generator. Reference samples (e.g. TR-909 kick WAV) are for measurement and parameter fitting only.
