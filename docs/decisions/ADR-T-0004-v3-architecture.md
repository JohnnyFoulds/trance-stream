# ADR-T-0004: v3 Four-Layer Architecture

**Status**: Accepted  
**Date**: 2026-07-08  
**Supersedes**: ADR-T-0001, ADR-T-0002

## Context

v1 and v2 both failed at the same two levels simultaneously:

**Level 1 — Technical**: Pure-Python synthesis loops cause buffer starvation at 44100 samples/s. Stateless filter calls (no `zi=` continuity) cause audible clicks at buffer boundaries. Non-deterministic drums (missing seed) make debugging impossible.

**Level 2 — Musical**: All musical constants were magic numbers with no documented rationale. When something sounded wrong, there was no basis for knowing *what* was wrong or *why*. "Listen and adjust" failed because there was no articulated musical knowledge to adjust *toward*.

## Decision

v3 introduces a strict four-layer architecture where each layer is independently testable:

```
Research & Knowledge
   docs/music_theory/       documented trance theory, SA reference analysis
        ↓
Song Theory Layer            song/theory.py
   All musical constants with source citations
        ↓
Instrument Layer             instruments/
   Each instrument encapsulates its full signal chain
        ↓
DSP Primitives               synth/
   numpy-vectorised oscillators, filters, envelopes, effects
```

### Layer responsibilities

**`song/theory.py`**: The single source of truth for all musical constants. Every value carries a `# Source:` comment citing a doc in `docs/music_theory/`. No constant may exist in instrument or DSP code without a theory.py reference.

**`instruments/`**: Each instrument is a class with `render(midi_notes, n_samples, **kwargs) → (buf_l, buf_r)`. Instruments own their internal state (oscillator phases, FDN state, delay buffer). They call DSP primitives but contain no raw numpy audio math.

**`synth/`**: Pure DSP functions. All inner loops numpy-vectorised — no `for i in range(n_samples)`. All filters use `scipy.signal.lfilter` with `zi=` state carried across calls for continuity. All generators return `float32` arrays.

### What changed from v2

| Issue | v2 | v3 |
|---|---|---|
| Synthesis speed | Python loops → unusable | numpy-vectorised → 6× realtime |
| Filter continuity | Stateless, clicks at boundaries | `zi=` state threads through all filters |
| Drum determinism | `random.seed` per-call | `np.random.default_rng(seed)` at init |
| Musical knowledge | Magic constants | Every value cites `docs/music_theory/` |
| Testability | Must run `main()` | Each layer independently testable |
| Why a value is X | Unknown | Source doc with derivation |

## Consequences

- All new musical constants must be added to `song/theory.py` with a source citation first, before being used anywhere else.
- Any change to a theory value requires updating the source doc first.
- DSP functions must not contain musical knowledge (e.g., no `GAIN_PAD = 0.5` in `synth/`).
- Instrument files may not import from other instrument files.
