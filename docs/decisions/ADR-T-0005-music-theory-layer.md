# ADR-T-0005: Music Theory Layer (`song/theory.py`)

**Status**: Accepted  
**Date**: 2026-07-08

## Context

Previous versions embedded musical constants directly in synthesis code — `LEAD_HIGH=74`, chord progressions as magic integers, filter arcs as hand-tuned equations. When spectral analysis revealed problems (wrong centroid, wrong brightness), there was no way to determine *which* constant was wrong or *why* it had its current value.

The core problem: without an explicit theory layer, every "fix" is a random walk through parameter space. You cannot converge on a target you cannot describe.

## Decision

`song/theory.py` is the music theory knowledge layer. It contains:

1. **Scale definitions** with emotional character documentation  
2. **Chord progressions** with harmonic analysis (not just scale degree numbers)
3. **SA's confirmed synthesis parameters** (rlpf_to_hz formula, filter arc values, gain levels)
4. **Build order timing** with derivation from SA's documented sessions
5. **Helper functions** (`rlpf_to_hz`, `degree_to_midi`, `chord_to_midi`, `samples_per_bar`)

### Source citation requirement

Every value in `theory.py` carries a `# Source:` comment citing a specific section in `docs/music_theory/`. For example:

```python
FILTER_ARC = {
    'full_open': 0.877,  # SA's confirmed value → 12267 Hz
    # Source: docs/music_theory/02_sa_vocabulary_codified.md §5
}
```

This makes two things possible:
1. When a value sounds wrong, you can read the source doc to understand why it was chosen
2. When you want to change a value, you update the doc first — which forces you to articulate the musical reason

### SA's confirmed formula

`rlpf_to_hz(slider) = (slider * 12) ** 4`  

This is SA's exact formula, reverse-engineered from her Strudel code. Key calibration points:
- slider=0.877 → 12267 Hz (SA's "fully open" euphoric release)
- slider=0.593 → 2564 Hz (SA's confirmed lead base filter value)

These values are in theory.py and verified by `song/theory_tests.py`.

### Test coverage

`song/theory_tests.py` contains 21 tests verifying:
- All rlpf_to_hz values match research measurements (±200 Hz)
- All scale degrees are valid (0-11)
- Build order is strictly non-decreasing
- notearp pattern is exactly 16 steps

## Consequences

- `song/theory.py` is the single import point for all musical constants. No instrument file defines its own gain constants, filter values, or timing parameters.
- When SA's actual code differs from what's in theory.py (e.g., new OCR analysis reveals a different rlpf value), the update path is: (1) update the doc in `docs/music_theory/`, (2) update theory.py with new source citation, (3) run theory_tests.py to verify.
- theory.py is deliberately import-free at module level (no scipy, no numpy except for simple math) — it must be loadable without the full synthesis stack installed.
