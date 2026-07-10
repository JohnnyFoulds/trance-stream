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

## No sample playback

We do not use downloaded audio samples as playback assets in the generator. Reference samples (e.g. TR-909 kick WAV) are for measurement and parameter fitting only.
