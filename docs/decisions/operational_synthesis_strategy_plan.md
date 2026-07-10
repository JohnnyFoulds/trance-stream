# Plan: Operational Synthesis Strategy Report

## Context

The previous session delivered `research/analysis/synthesis_parameter_methodology.md` — a rigorous academic document establishing the analysis-by-synthesis framework, spectral gap analysis, and four falsifiable hypotheses for closing the hey_angel CLAP gap (currently 0.385 vs target ≥ 0.70). The experiment log `research/analysis/experiment_log.md` records the baseline and pre-specifies EXP-001–004.

**The user's new request**: that work is academically solid but practically incomplete. What is missing is a single document that bridges:

1. **How to reproduce "hey angel" specifically** — using the tools and measurements we now have, what is the step-by-step procedure an engineer would follow *right now*
2. **How to reproduce any other SA song** — the generalised workflow, not just the hey_angel instance
3. **How these tools and methods serve the ultimate goal** — Death Angel, the original trance generator engine (BR-1 through BR-6 in `docs/feature-spec.md`)

The existing methodology doc is the *theory*. This new report is the *operations manual* — concrete, actionable, forward-looking. It must reference the existing research rather than repeat it.

---

## What the existing reports cover (and what they do NOT cover)

### Existing research that IS present

| Document | What it covers |
|---|---|
| `synthesis_parameter_methodology.md` | AbS theory, source-filter model, spectral gap analysis for hey_angel, H1–H4 hypotheses, CLAP/centroid/MFCC measurement framework, limitations |
| `experiment_log.md` | EXP-000 baseline, EXP-001–004 pre-specified, append-only tracking schema |
| `audio_similarity_metrics_litreview.md` | Why CLAP is the right metric, FAD/CDPAM/PESQ rejection reasons |
| `audio_reproduction_gap_analysis.md` | What hey_angel parameters are confirmed vs missing, what tools exist |
| `sa_parameter_measurement_methodology.md` | Confidence tiers for all SA constants, critical bugs (IIR sidechain, trancegate shape, BPM hardcode), trancegate as probabilistic binary gate not cosine |
| `switch_angel_song_structure.md` | SA's 10-stage additive build order, no breakdown/drop, primary variation tool = rlpf slider arc |
| `switch_angel_vocabulary.md` | OCR'd synthesis parameters from 5 YouTube sessions |
| `docs/feature-spec.md` | Full product requirements, acceptance bar BR-1, Death Angel ultimate goal, five voices, arrangement phases |

### What is NOT covered anywhere (the gap this report fills)

1. **A practical "reproduce a cover now" checklist** — what tools to run in what order, how to interpret their output, how to map each output to a specific parameter change, what acceptance condition tells you you're done
2. **A generalised "new song" workflow** — given a new SA WAV you have never seen, what is the exact sequence of steps to arrive at a synthesis parameter set? Which tools, in which order, with what expected outputs?
3. **How the hey_angel EXP-001–004 sequence connects to the v3 trance_stream.py engine** — the hey_angel cover is a parameter-validation vehicle. What knowledge transfers to the generative engine and how? What does "CLAP ≥ 0.70 on hey_angel" actually prove about the engine's capability?
4. **The Death Angel generalisation** — once the synthesis methodology is validated on SA reproductions, how does it inform building an original voice? Which parameters are SA-specific scaffolding (to be replaced) vs general synthesis principles (to be kept)?
5. **Known bugs blocking progress** — `sa_parameter_measurement_methodology.md` documents three active bugs (IIR sidechain, trancegate shape, BPM hardcode) that will limit any reproduction attempt regardless of how well the spectral parameters are tuned. These are not mentioned in `synthesis_parameter_methodology.md` at all. An operations manual must integrate bug status with the experimental protocol.
6. **Tool limitations in plain language** — `analyse_timbre.py` classifies everything as sine due to Demucs blending. `extract_drum_pattern.py` cannot reliably extract kick pattern due to F2 bleed. The new practitioner reading these docs cannot know which tool outputs to trust and which to ignore. A single reference table is needed.
7. **What "done" looks like for the cover, and what "done" looks like for the engine** — two different acceptance criteria, currently defined in scattered documents (experiment_log convergence criterion vs feature-spec BR-1/T-002).

---

## Deliverable

**One new file**: `research/analysis/operational_synthesis_strategy.md`

This is NOT another academic literature review. It is a practitioner-oriented strategy document that:
- Opens with the two-level goal hierarchy (cover reproduction → engine)
- References the existing research rather than restating it
- Is structured as a decision tree / workflow that can be followed without reading the underlying academic papers
- Integrates the known bugs as a prerequisite checklist before beginning any spectral parameter iteration
- Explicitly maps from tool output → synthesis parameter change → expected metric movement
- Gives concrete "done" criteria at each level

Length: approximately 400–600 lines. No fluff. No re-derivation of things already in `synthesis_parameter_methodology.md`. Dense and actionable.

---

## Report Structure

### 1. Purpose and Scope (10 lines)
One paragraph. What this document is and is not. Points to `synthesis_parameter_methodology.md` for theory, `experiment_log.md` for tracking.

### 2. Goal Hierarchy
Two levels explicitly defined:

**Level 1 — Cover reproduction** (current phase):
- Target: `tools/compare_audio.py` OVERALL PASS (all four Tier-1 metrics simultaneously: CLAP ≥ 0.70, centroid_ratio ∈ [0.70, 1.30], band_energy_cosine ≥ 0.85, mfcc_cosine ≥ 0.80)
- Vehicle: `hey_angel_cover.py` + `research/reference_audio/hey_angel_trimmed.wav`
- What it proves: that the synthesis chain can produce a perceptually plausible trance mix when parameters are set correctly
- Branch: must NOT merge `sidequest/pluck-arp-analysis` to main until all four Tier-1 gates pass

**Level 2 — Generalised engine** (next phase, Death Angel):
- Target: BR-1 (a trance-familiar listener identifies the output as Switch Angel's style within 15 seconds) and ultimately a distinct original voice
- Vehicle: `trance_stream.py` / the v3 generative engine
- What cover reproduction proves toward this: it validates the source-filter parameter extraction workflow so that new songs can be processed into parameters without manual tuning from scratch
- What cover reproduction does NOT prove: that the generative arrangement engine (phase structure, CA gating, melody generation) is correct — those are separate concerns

### 3. Prerequisites: Known Bugs That Must Be Fixed First
Three bugs documented in `sa_parameter_measurement_methodology.md` that limit reproduction quality regardless of spectral parameter accuracy. Each must be resolved before the EXP series can be interpreted cleanly:

**Bug 1 — Sidechain IIR perpetual duck** (`synth/effects.py:327`)
- Effect: after first kick, pad is permanently ducked ~40% gain; never recovers between kicks
- Impact on experiments: all band energy measurements after the first kick are wrong — the pad's contribution to the 0–200 Hz and 200–500 Hz bands is artificially suppressed
- Fix required before: EXP-000 baseline is arguably contaminated. EXP-001 results for band_energy_cosine cannot be interpreted cleanly while this bug is active.
- Urgency: HIGH — fix before running EXP-001

**Bug 2 — Trancegate shape mismatch** (`instruments/pad.py`, `synth/effects.py`)
- Effect: SA's trancegate is a probabilistic binary gate (`rand.mul(density).round()`); the Python implementation uses a smooth raised cosine. These produce different spectral envelopes.
- Impact on experiments: MFCC cosine and CLAP are sensitive to timbral envelope character. The trancegate shape difference may account for part of the MFCC gap independently of filter cutoff.
- Fix required before: Phase 2 (mfcc_cosine gap investigation). Can run EXP-001 (spectral shape) while this is outstanding, but interpret MFCC results with caution.
- Urgency: MEDIUM — fix before Phase 2

**Bug 3 — BPM hardcoded in SupersawPad** (`instruments/pad.py:91`)
- Effect: trancegate timing drifts if BPM ≠ 140. hey_angel runs at 140.0534, so drift is minimal (~19ms over 15 bars). Not a blocking issue for hey_angel specifically.
- Urgency: LOW for hey_angel; HIGH before generalising to other songs at different BPMs

### 4. Tool Reference: What to Trust and What Not To

A single consolidated table of every analysis tool, what it reliably produces, and its known failure modes. This is the practitioner's quick reference — the thing you read before trusting any number from the pipeline.

| Tool | Reliable outputs | Known failure modes / do not trust |
|---|---|---|
| `tools/compare_audio.py` | Tier-1 perceptual gates (CLAP, centroid_ratio, band_energy_cosine, mfcc_cosine); Tier-2 structural diagnostics | Kick phase error unreliable on hey_angel (F2 bass bleed at 50–120 Hz); MFCC DTW threshold was never calibrated (reports 178 vs threshold 0.30 — broken); CLAP requires laion-clap installed and downloads 150MB on first run |
| `tools/spectrogram.py` | Band energy in dB (sub/bass/mid/hi-mid/air), brightness%, qualitative spectral profile | Absolute centroid values differ from compare_audio.py (different hop/SR); not authoritative for gating |
| `tools/analyse_timbre.py` | Filter cutoff (−18 dB point) reliable even in blended stems; ADSR envelope shape from stems | Oscillator classification (saw/sine/square) unreliable — heavy Demucs filtering makes all sources look like sine; fundamental detection unreliable for blended stems |
| `tools/extract_drum_pattern.py` | Hi-hat pattern at 16 steps (alignment error <20ms acceptable); beat grid BPM confirmation | Kick pattern contaminated by F2 bass bleed at 50–120 Hz; kick alignment error 34.5ms on hey_angel = unreliable |
| `tools/stem_separation.py` | Separates 6 stems; bass and drums stems reliable for their primary frequency ranges | Synth melody lead → "vocals" stem (contamination from high pluck); high pluck arpeggio → "guitar" stem; "other" stem is pad + residual |
| `research/strudel_debug.html` | Ground-truth parameter values from running SA's actual Strudel code | Only as authoritative as the OCR extraction accuracy; some parameters (trancegate shape) were inferred, not measured |
| `song/theory.py` constants | BPM=140, G minor, `rlpf_to_hz()`, FILTER_ARC slider values | `TRANCEGATE_AMOUNT=0.7` is developer override (SA uses 1.0); `GAIN_PAD=1.50` is developer override (SA uses 0.5); several `# SA confirmed` annotations are OCR inputs, not measured outputs |

### 5. Workflow A: Reproducing "hey angel" (Current Task)

A numbered procedure an engineer follows from scratch. References existing docs for rationale; does not repeat it.

```
Step 0 — Environment check
  [ ] Bug 1 (IIR sidechain) resolved? If not, fix synth/effects.py:327 first.
  [ ] compare_audio.py Tier-1 working? Run: python tools/compare_audio.py ref.wav ref.wav
      Expected: all four Tier-1 metrics ≥ 0.97, OVERALL PASS. If CLAP fails: pip install laion-clap

Step 1 — Render baseline (EXP-000)
  python hey_angel_cover.py --bars 15 --wav /tmp/ha_EXP-000.wav
  python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav /tmp/ha_EXP-000.wav --bpm 140.0534
  Record results in experiment_log.md. Current known baseline: CLAP=0.385, centroid=0.567, band_energy=0.649, mfcc=0.661.

Step 2 — Run H1: Lead cutoff (instruments/smooth_lead.py, cutoff_hz 900→2400)
  See EXP-001 in experiment_log.md for exact hypothesis and falsification criterion.
  Predicted: band_energy_cosine increases ≥0.05, centroid_ratio increases.
  Render: python hey_angel_cover.py --bars 15 --wav /tmp/ha_EXP-001.wav
  Compare: python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav /tmp/ha_EXP-001.wav --bpm 140.0534
  Fill in EXP-001 results row in experiment_log.md.
  Decision: if band_energy_cosine < 0.70, H1 is rejected, revert and diagnose.

Step 3 — Run H3: Bass cutoff (hey_angel_cover.py, G1 cutoff_slider 0.26→0.38)
  See EXP-003 in experiment_log.md.
  Predicted: 0–200 Hz band fraction increases ≥5 percentage points.

Step 4 — Run H2: Hi-hat gain (hey_angel_cover.py, _gain_hihat 0.25→target)
  ONLY after H1 is evaluated. Target gain depends on post-H1 percussive/harmonic ratio.
  H2 is NOT about absolute hi-hat loudness — it is about bringing the 4k+ full-mix fraction
  from 0.5% toward reference 9.3% AFTER the harmonic pileup is corrected.

Step 5 — Run H4: Joint (H1+H2+H3 simultaneously)
  See EXP-004. Expected: band_energy_cosine ≥0.85, centroid_ratio ∈ [0.70, 1.30].

Step 6 — Assess mfcc_cosine gap
  After H4: if mfcc_cosine < 0.80, investigate:
  (a) Is Bug 2 (trancegate shape) still active? Fix it and re-measure.
  (b) Run analyse_timbre.py on vocals stem — is the filter Q (resonance) significantly different from 0?
      If yes, add resonance to SmoothLead and re-run.
  (c) Oscillator type: try switching SmoothLead oscillator from sine to filtered saw and re-run.

Step 7 — Assess CLAP gap
  After Phase 1+2: if CLAP < 0.70, the remaining deficit is holistic style.
  Diagnose using Tier-2 diagnostics:
  - onset_xcorr_peak < 0.40: rhythmic feel mismatch → investigate trancegate pattern vs reference
  - rms_envelope_r < 0.70: energy trajectory mismatch → investigate reverb wet level, sidechain recovery
  - chroma_cosine still PASS: harmonic content (key, chord) is correct; the gap is timbral/textural

Step 8 — Convergence
  OVERALL PASS from compare_audio.py (all four Tier-1 simultaneously).
  Then: may merge sidequest/pluck-arp-analysis to main.
```

### 6. Workflow B: Reproducing a New SA Song

The generalised procedure for any SA song not yet covered. Assumes the target WAV exists in `research/reference_audio/`.

```
Phase 0 — Audio preparation
  Trim to the groove section (skip silent intro, cut at fade-out):
    ffmpeg -i source.wav -ss [start] -to [end] -ar 44100 research/reference_audio/[song]_trimmed.wav
  Run HTDemucs stem separation:
    python tools/stem_separation.py research/reference_audio/[song]_trimmed.wav

Phase 1 — Structural analysis
  (a) Beat grid: run extract_drum_pattern.py on drums stem
      → confirms BPM, hi-hat step pattern (trust), kick pattern (verify manually, tool unreliable)
  (b) Key + chord: run analyse_audio.py on reference WAV or bass stem
      → confirms root note, scale (SA always uses G natural minor)
  (c) Melody: run audio_to_midi.py on vocals stem
      → extracts pitch contour; confirm with spectrogram.py
  (d) Song structure: compare against switch_angel_song_structure.md build order
      → all SA songs follow the same 10-stage additive pattern

Phase 2 — Timbre parameter extraction
  For each stem: run analyse_timbre.py
    drums stem → kick parameters (frequency sweep, decay); hi-hat parameters
    bass stem → filter cutoff (trust the −18dB estimate), fundamental pitch (trust)
    vocals stem → melody lead filter cutoff (trust −18dB), ADSR (trust), portamento rate (trust),
                   oscillator type (DO NOT trust — see tool reference §4)
    other stem → pad filter cutoff, centroid
  Record all values. Mark confidence level per §4.

Phase 3 — Baseline measurement
  Create a new cover script (copy hey_angel_cover.py as template, update parameters from Phase 2).
  Run compare_audio.py with new reference. Record as EXP-000 in a new experiment log for that song.
  Target: reach OVERALL PASS through the same EXP series as hey_angel.

Phase 4 — SA vocabulary constants (always the same across songs)
  Per switch_angel_vocabulary.md, these do NOT need to be re-measured for new songs:
  - BPM: 140.0534 (always)
  - Key: G natural minor (always)
  - Kick: steps 0,4,8,11,14 (standard SA pattern; verify against this specific song)
  - Trancegate: density=1.5, seed=45, length=1 (standard SA parameters)
  - rlpf_to_hz: confirmed formula, use FILTER_ARC from song/theory.py as starting point
  What MUST be measured per song: melody pitch contour, bass pattern, any pluck/arp voices
```

### 7. From Cover Reproduction to the Generative Engine

This section explicitly maps what the cover reproduction work proves — and does not prove — about the trance_stream.py engine.

**What is validated by achieving CLAP ≥ 0.70 on hey_angel:**
- The source-filter model correctly maps filter cutoff settings to spectral centroid
- The `tools/compare_audio.py` Tier-1 thresholds are calibrated at the right level
- SmoothLead's instrument chain (oscillator → filter → reverb) can produce timbres perceptually close to SA's
- The measurement-to-parameter workflow (§5 of synthesis_parameter_methodology.md) is correct

**What is NOT validated by hey_angel reproduction:**
- The generative melody engine (it uses a hardcoded melody in the cover)
- The CA-gated arrangement system (phases, Intro/Groove/Breakdown/Drop/Build)
- The trancegate pattern variation (hardcoded in cover, probabilistic in SA)
- Multi-song generalisability (only one reference tested)
- The v3 trance_stream.py instrument chain (SupersawPad, AcidLead, AcidBass — different from hey_angel's SmoothLead)

**Transfer path to the engine** (in order):
1. Validated SmoothLead parameters → inform AcidLead tuning (similar spectral target, different synthesis chain; use same centroid target methodology)
2. Validated bass cutoff methodology → apply to AcidBass's filter LFO arc (FILTER_ARC values in song/theory.py are OCR'd starting points; measure against the reference)
3. Validated compare_audio.py calibration → use same Tier-1 gates to evaluate trance_stream.py renders (same tool, new reference: any SA 90s clip from research/reference_audio/)
4. Bug fixes (IIR sidechain, trancegate shape) → must be fixed in trance_stream.py before its evaluation can be trusted; they are the same bugs in hey_angel_cover.py

**Death Angel specific:**
The ultimate goal is not a SA clone but an original voice (BR-1 says "sounds like SA", not "is SA"). The operational path:
1. Reproduce SA precisely enough to understand *which* parameters create the perceptual identity (trance = kick + sidechain pump + filtered supersaw + trancegate + delay on lead)
2. Identify which parameters are SA-specific vs genre-defining (SA-specific: G minor, 140 BPM, her specific rlpf arc; genre-defining: sidechain depth, trancegate density, supersaw detune range)
3. Vary the genre-defining parameters away from SA's values while keeping the genre-defining architecture — that is how Death Angel gets its own voice
4. Use compare_audio.py against SA reference clips as a floor (score must be perceptually "trance" but not an exact clone); define a separate Death Angel target clip or use a perceptual description

### 8. Immediate Action Items (Prioritised)

What to do next, in order, before running EXP-001:

1. **Fix Bug 1** (IIR sidechain, `synth/effects.py:327`) — HIGH URGENCY. The sidechain perpetual duck contaminates all band energy measurements. Fix before running EXP-001, or EXP-001 results will be confounded. See `sa_parameter_measurement_methodology.md §4` for diagnosis.

2. **Run EXP-001** (H1: SmoothLead cutoff_hz 900→2400) — the highest-leverage single change. See `experiment_log.md` for the exact procedure.

3. **Fix Bug 2** (trancegate shape) — MEDIUM URGENCY. Fix before interpreting mfcc_cosine results in Phase 2. See `sa_parameter_measurement_methodology.md §2`.

4. **Run EXP-002–004** (H2+H3+H4) — after EXP-001 is evaluated and Bug 1 is fixed.

5. **If hey_angel reaches OVERALL PASS**: validate on a second SA reference clip (e.g. `research/reference_audio/-pDO2RhcGhM_90s.wav`) using Workflow B §6. This tests generalisability before attempting the v3 engine.

6. **Apply validated parameters to trance_stream.py**: update AcidLead, AcidBass, DrumKit based on what worked. Then re-run compare_audio.py against the 90s SA clips.

---

## Implementation notes

**Step 0 — Copy plan into repo first**
Before writing the deliverable, copy this plan file into the repo:
```
cp ~/.claude/plans/is-our-tools-fully-wise-book.md \
   docs/decisions/operational_synthesis_strategy_plan.md
```
This preserves the planning rationale alongside the output it produced.

**File to create**: `research/analysis/operational_synthesis_strategy.md`

**Must NOT do**:
- Re-derive the AbS theory (that is in synthesis_parameter_methodology.md)
- Re-state the H/P breakdown tables (reference them, don't copy them)
- Copy the experiment log schema (reference it)

**Must DO**:
- Reference every existing doc by path with a one-line description of what it contains
- Include the tool reference table (§4 above) in full — this does not exist anywhere else
- Include the bug prerequisite checklist (§3 above) in full — not present in synthesis_parameter_methodology.md
- Include the generalised Workflow B (§6) — not present anywhere
- Include the engine transfer path (§7) — not present anywhere
- Be usable standalone as an index into the full research corpus

**APA 7th citations required** per CLAUDE.md: the new document primarily references our own research and tools, so citations will be sparse — but any new algorithm or model referenced must be cited. The bug diagnosis section may need no external citations (it references our own measurement findings). The Death Angel generalization section may cite Grey (1977) (perceptual identity = spectral centroid is most salient dimension) if the argument requires it.

---

## Verification

After writing:
1. Confirm all cross-references in the new doc point to files that actually exist at the stated paths
2. Confirm no content in the new doc contradicts the existing experiment_log.md numbers (EXP-000 baseline values)
3. Confirm the tool reference table matches what the tools actually do (check instruments/smooth_lead.py to confirm cutoff_hz is a direct parameter, not slider-based)
