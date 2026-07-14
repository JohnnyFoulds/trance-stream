# Codebase Orientation

This note captures the current shape of the repository so future sessions can re-enter the codebase without re-reading the whole tree.

## What This Project Is

TranceStream is a deterministic procedural trance generator targeting the sound of Switch Angel's live-coded Strudel sets. The repo keeps the generator fully mathematical and DMCA-safe: no sample playback in the synthesis path, no imported Strudel runtime, and all musical constants trace back to measured reference material.

The long-term direction in the repo is explicit:

- short term: reproduce Switch Angel's style convincingly and measurably
- long term: use that stack to build an original AI trance identity called Death Angel

## Main Runtime Path

The v3 implementation is the active architecture and is the one to understand first:

- `trance_stream_v3.py` is the CLI entry point.
- `song/builder.py` turns seed + mood into a `Song` object.
- `song/theory.py` owns the musical constants, timing values, and style mappings.
- `song/renderer.py` renders bar-by-bar audio and MIDI.
- `song/track.py` binds instruments to activation bars and per-bar parameter arcs.
- `instruments/` contains the actual voice implementations: kick, bass, lead, pad, pluck, pulse, and variants.
- `synth/` contains the reusable DSP primitives such as oscillators, filters, envelopes, and effects.

The data flow is:

seed + mood -> `song/builder.py` -> `Song` -> `song/renderer.py` -> instruments + synth primitives -> stereo audio + MIDI export

The renderer is the important boundary. It is where arrangement state, sidechain, trancegate, kick spill, filter continuity, and MIDI logging all come together.

## What Each Layer Does

### `song/`

This is the musical control layer.

- `song/theory.py` is the source of truth for scales, chord progressions, stage timings, gain values, trancegate settings, and register limits.
- `song/builder.py` decides which chord progression, BPM, root note, notearp pattern, and stage arc to use for a given seed and mood.
- `song/renderer.py` is the per-bar execution engine. It decides which tracks are active, renders each bar, applies sidechain, handles tail spill, and writes WAV/MIDI output.
- `song/track.py` is intentionally tiny: it just packages an instrument with activation metadata and optional arc functions.

### `instruments/`

This is where the sound character is actually made.

- `instruments/drums.py` caches rendered kick, hi-hat, and clap buffers for determinism and performance.
- `instruments/bass.py` renders the acid bass voice with a saw, VCA envelope, acidenv, and low-pass filtering.
- `instruments/lead.py` renders the lead voice with supersaw, optional FM, acidenv, trancegate, and feedback delay.
- `instruments/pad.py` renders the pad with supersaw, slow LP swell, trancegate, FDN reverb, and sidechain interaction.
- `instruments/pluck.py` and `instruments/pulse.py` handle the additional texture voices used by the newer arrangements.

### `synth/`

This is the DSP toolkit used by the instruments.

- `synth/oscillators.py` contains the PolyBLEP saw, supersaw, sine, and brown-noise generators.
- `synth/filters.py` provides stateful filters using `scipy.signal.lfilter` with carried state.
- `synth/envelopes.py` defines the acid envelope, pad envelope, and trancegate pattern generator.
- `synth/effects.py` implements feedback delay, FDN reverb, and related spatial processing.

## Research And Documentation Layer

The repo has a strong measurement-and-documentation loop, and that matters because many constants are not arbitrary.

- `research/README.md` explains the Switch Angel extraction pipeline and how reference code snapshots were gathered.
- `research/strudel_debug.html` is the browser-based measurement tool used to inspect Switch Angel's actual Strudel code.
- `docs/music_theory/` contains the written theory and parameter analysis that feed `song/theory.py`.
- `docs/decisions/` captures architecture decisions and regressions so behavior changes are explained instead of guessed at.

The important practical rule in the repo is that measured values are supposed to come from the research path first, then land in `song/theory.py`, then flow into the instruments and renderer.

## Test Coverage

The test suite is broad and is worth trusting as a guide to intended behavior.

- `tests/test_song.py` checks determinism, output length/dtype, stereo differences, clipping, spectral range, and late-stage behavior.
- `tests/test_instruments.py` checks the kick, hi-hat, clap, lead, bass, pad, and their spectral or dynamic properties in isolation.
- `tests/test_variation.py` verifies that seeds and moods actually change the song structure and rendered audio.
- `tests/test_streaming.py` checks the realtime streaming path against batch rendering and validates WAV output.
- `tests/test_visualiser.py` checks the terminal visualiser logic and indicator states.
- `tests/test_seamless.py` checks bar-boundary continuity, oscillator phase continuity, and tail spill behavior.

That test structure tells you what the repo cares about most: deterministic variation, continuity across bars, and perceptual quality rather than just “it runs”.

## Known Documented Work

The repo is not a blank scaffold. It already has a mostly complete v3 pipeline, a substantial test suite, and explicit documentation for decisions and regressions.

Notable documented items:

- `docs/decisions/bad_apple_trancegate_regression.md` documents the known gate-mode regression in `bad_apple_cover.py` and why a cosine gate is needed there.
- `docs/decisions/ADR-T-0004-v3-architecture.md` explains why the current architecture is split into research, theory, instruments, and DSP layers.
- `CLAUDE.md` and `README.md` both emphasize measurement-driven tuning and the SA -> Death Angel roadmap.

## Practical Takeaway

If you need to understand or change behavior, start with `song/theory.py` for constants, `song/builder.py` for song assembly, and `song/renderer.py` for how the music is synthesized bar by bar. The instrument modules shape the actual timbre, while the `tests/` directory tells you what behavior is currently considered part of the contract.

If you need the deeper origin of a constant, look in `docs/music_theory/` and `research/` before changing code.
