# Playbook: What to do when OPT-002 finishes

Written before the run completes so there's a clear decision tree ready to follow.

---

## Step 1 — Listen first, code second

Render the best params and listen before touching anything:

```bash
python hey_angel_cover.py --bars 16 --wav /tmp/ha_OPT002_best.wav
# then compare side-by-side with the reference
```

Also run the spectrogram comparison for hard numbers:

```bash
python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav /tmp/ha_OPT002_best.wav --bpm 140.0534
```

Write down the single most obvious perceptual difference before doing anything else.
That answer determines every subsequent step.

---

## Step 2 — Decision tree

### If CLAP ≥ 0.70 and it sounds right

Done. Document results in `experiment_log.md` as OPT-002 success, merge to main.

### If CLAP ≥ 0.70 but something still sounds wrong

The metric has passed but the perceptual target hasn't. Go to Step 3 (voice isolation)
to find which voice is the offender, then add that specific architectural parameter
to OPT-003.

### If CLAP < 0.70 but close (0.65–0.69)

Check the bound-hitting parameters first. If `pad_gain`, `kick_decay_s`, or
`lead_cutoff_hz` are still at their limits, widen those bounds and run OPT-003
warm-started from OPT-002 best. This is the cheap fix — try it before touching
the architecture.

### If CLAP < 0.65 or clearly plateaued

The 15-dim parameter space is exhausted. The gap is in oscillator architecture,
not mixer settings. Go to Step 3 (voice isolation) to identify which voice to fix.

---

## Step 3 — Voice isolation (when the numbers alone don't explain the gap)

The reference mix has no clean stems, so use two sources:

**For the kick — Demucs:**
```bash
pip install demucs
python -m demucs --two-stems=drums research/reference_audio/hey_angel_trimmed.wav
# drums stem lands in separated/htdemucs/<trackname>/drums.wav
```
Compare the drums stem against a solo kick render:
```bash
python hey_angel_cover.py --bars 16 --wav /tmp/ha_kick_solo.wav --solo kick
python tools/compare_audio.py separated/htdemucs/.../drums.wav /tmp/ha_kick_solo.wav --bpm 140.0534
```

**For the pad — Strudel debug page (authoritative):**

1. Open `research/strudel_debug.html` in a browser
2. Comment out everything except the pad pattern
3. Record 8 bars of output
4. Compare spectrogram and centroid against a solo pad render:

```bash
python hey_angel_cover.py --bars 8 --wav /tmp/ha_pad_solo.wav --solo pad
python tools/spectrogram.py /tmp/ha_pad_solo.wav --out /tmp/spec_gen.png
python tools/spectrogram.py <strudel_recording.wav> --out /tmp/spec_ref.png
```

Listen for and measure these specific properties:
- Is the pad too dark or too bright? (spectral centroid)
- Does the trancegate breathe the same way? (RMS envelope shape)
- Is the supersaw character similar? (MFCC distance)

---

## Step 4 — Architectural fixes (if voice isolation finds a problem)

| What you hear | Likely cause | Fix |
|---|---|---|
| Pad sounds too thin / too thick | Supersaw voice count or detune spread | Add `saw_count` and `detune_cents` to OPT-003 parameter space |
| Pad filter sounds wrong at rest | Filter floor constant | Measure `rlpf(0.5)` from Strudel debug, update `pad_cutoff_slider` bounds |
| Trancegate sounds mechanical / clicky | Binary gate vs SA's smooth gate | Apply `gate_mode='cosine'` fix from `bad_apple_trancegate_regression.md` |
| Kick too long / short | `kick_decay_s` hitting bounds | Widen bounds; currently AT 0.50 upper limit |
| Mix feels right per-voice but wrong together | Relative gain balance or sidechain shape | Add relative gain ratios to OPT-003; check sidechain IIR time constant |

---

## Step 5 — The uncomfortable case

If individual voices sound correct in isolation but the combined mix still doesn't
match, the gap is not in synthesis. The three possible causes, in order of effort:

1. **Relative levels / masking** — the mix balance is wrong even if each voice is
   right. Solvable: optimize relative gain ratios directly with the full mix as
   the CLAP target.

2. **Timing and groove** — the generator's rhythmic patterns are too mechanical.
   Go back to `research/strudel_debug.html`, measure actual note timings from SA's
   code, and check for swing or micro-timing offsets.

3. **Arrangement arc** — the 26-second energy shape of the reference doesn't match
   what the generator produces over 16 bars. This is structural: the intro stage,
   what enters when, how the filter opens. No parameter optimization will fix this.

If you reach cause 3, declare the synthesis phase complete. The synthesis stack
is validated — the remaining gap is in a different layer. Document the conclusion
in `experiment_log.md` and move toward Death Angel.

---

## Current run state (at time of writing)

- **Evals completed**: ~3,863
- **Best CLAP**: 0.6569 (eval 3317, ~550 evals ago — plateau likely)
- **Centroid penalty working**: score ≈ CLAP throughout (centroid staying in range)
- **Bound-hitting**: `pad_gain` AT 5.00, `kick_decay_s` AT 0.50, `hihat_decay_s` AT 0.005
- **OPT-001 → OPT-002 delta**: +0.022 CLAP (0.6348 → 0.6569)
- **Gap to target**: 0.043 remaining

The run is likely converged. Expect final best to land around 0.657–0.660.
