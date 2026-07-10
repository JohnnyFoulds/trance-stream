# Claude Code Instructions — trance-stream

## Testing principle: no excuses for untested work

**Never ask the user to test something you can verify yourself first.**

Before reporting a feature as working — especially anything involving audio, visual output, or browser behavior — build an automated test and run it. Only involve the user once you have evidence it works.

This applies universally:
- **Audio output**: use Python `playwright` + a patched `AudioContext` to measure RMS amplitude. Non-zero RMS (> 0.001) confirms sound is being generated. See `tools/test_strudel_audio.py` for the pattern.
- **Synthesis quality**: every perceptual property has a measurable correlate. Spectral centroid, rolloff, RMS envelope, zero-crossing rate, pitch trajectory — measure them with `librosa` or `scipy`. "I can't listen like a human" is not an acceptable reason to skip measurement.
- **Browser UI**: use `playwright` to click buttons, read DOM state, and capture console errors. If the status says "Playing" but RMS is zero, it's broken.
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
