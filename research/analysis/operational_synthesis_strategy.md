# Operational Synthesis Strategy: From Reference Audio to Cover to Engine

**Date**: 2026-07-10  
**Branch**: `sidequest/pluck-arp-analysis`  
**Status**: Active — drives EXP-001 and beyond  
**Planning rationale**: `docs/decisions/operational_synthesis_strategy_plan.md`

---

## 1. Purpose and Scope

This document is an operations manual, not a literature review. It tells you what to do, in what order, and how to interpret the results. For theory and academic grounding, read `research/analysis/synthesis_parameter_methodology.md`. For experiment tracking, use `research/analysis/experiment_log.md`. This document is what you open when you sit down to work.

It covers three things the existing research does not:
- A step-by-step procedure for reproducing "hey angel" right now, integrating known bugs as prerequisites
- A generalised workflow for reproducing any SA song
- An explicit map from cover-reproduction work to the Death Angel engine

---

## 2. Research Corpus Index

All existing documents, what they contain, and when to read them:

| Document | Contents | Read when |
|---|---|---|
| `research/analysis/synthesis_parameter_methodology.md` | AbS theory, source-filter model, full spectral gap analysis for hey_angel, H1–H4 hypotheses with falsification criteria, measurement-to-parameter mapping, known limitations | Before running any experiment; once, at the start |
| `research/analysis/experiment_log.md` | Append-only record of every synthesis experiment; EXP-000 baseline (all Tier-1 FAIL); EXP-001–004 pre-specified | Every time you change a synthesis parameter |
| `research/analysis/audio_similarity_metrics_litreview.md` | Why LAION-CLAP is the correct Tier-1 metric; why FAD/CDPAM/PESQ are wrong for this use case | If you question why we use CLAP, or need to justify the metric choice |
| `research/analysis/audio_reproduction_gap_analysis.md` | hey_angel parameters confirmed vs still missing; tools that exist vs tools still needed | When starting a new cover or auditing what is and is not measured |
| `research/analysis/sa_parameter_measurement_methodology.md` | Confidence tiers for all SA constants in `song/theory.py`; three active bugs; critical finding that trancegate is probabilistic binary gate, not cosine | Before fixing bugs; before trusting any constant marked `# SA confirmed` |
| `research/analysis/switch_angel_song_structure.md` | SA's 10-stage additive build order (all 5 videos); no breakdown/drop; rlpf slider as primary variation tool | When writing a new cover script or planning arrangement phase |
| `research/analysis/switch_angel_vocabulary.md` | OCR-extracted synthesis parameters from 5 SA YouTube sessions | When looking up SA's specific parameter values (BPM, trancegate, filter arc) |
| `docs/feature-spec.md` | Full product requirements BR-1–BR-6; acceptance test T-002 (listener test); five-voice engine spec; Death Angel ultimate goal | When deciding scope of any feature or evaluating whether the engine is "done" |
| `docs/decisions/compare_audio_redesign.md` | Architectural rationale for the two-tier compare_audio.py redesign | If you need to understand why the tool changed or justify a threshold |
| `docs/testing/AUDIO_SIMILARITY_METHODOLOGY.md` | Full methodology for each Tier-1 and Tier-2 metric, with APA citations | If a metric value looks suspicious or you need to reproduce a calculation |

---

## 3. Goal Hierarchy

There are two levels. Every task belongs to one of them.

### Level 1 — Cover reproduction (current phase)

**Target**: `tools/compare_audio.py` OVERALL PASS  
**Criteria** (all four Tier-1 metrics simultaneously):
- `clap_cosine` ≥ 0.70
- `spectral_centroid_ratio` ∈ [0.70, 1.30]
- `band_energy_cosine` ≥ 0.85
- `mfcc_cosine` ≥ 0.80

**Vehicle**: `hey_angel_cover.py` vs `research/reference_audio/hey_angel_trimmed.wav`

**What it proves**: the synthesis chain can produce a perceptually plausible trance mix when parameters are correctly derived from audio measurements. Specifically: that the source-filter measurement workflow (analyse_timbre.py → filter cutoff target → synthesis parameter) works end-to-end.

**Branch policy**: do NOT merge `sidequest/pluck-arp-analysis` to main until OVERALL PASS is achieved.

**Current state**: EXP-000 baseline — all four Tier-1 metrics FAIL (CLAP=0.385, centroid_ratio=0.567, band_energy_cosine=0.649, mfcc_cosine=0.661). Root cause documented: `SmoothLead.cutoff_hz=900 Hz` causes 52.5% of mix energy to pile up at 200–500 Hz, swamping all content above 1 kHz. Full spectral gap analysis: `synthesis_parameter_methodology.md §4`.

### Level 2 — Generalised engine (next phase, Death Angel)

**Target**: BR-1 — a trance-familiar listener identifies the output as Switch Angel's style within 15 seconds, without knowing it is procedurally generated (`docs/feature-spec.md §1.1`)

**Vehicle**: `trance_stream.py` / the v3 generative engine (SupersawPad, AcidLead, AcidBass, DrumKit, arrangement state machine)

**What cover reproduction proves toward this**: the measurement-to-parameter workflow is correct. CLAP ≥ 0.70 on hey_angel means the tool is calibrated, the spectral targets are achievable, and the same workflow can be applied to any SA reference clip.

**What cover reproduction does NOT prove**:
- That the generative melody engine is correct (hey_angel uses a hardcoded melody)
- That the CA-gated arrangement system (Intro/Groove/Breakdown/Drop/Build phases) produces coherent structure
- That the trancegate pattern variation sounds right when generated randomly
- That the v3 instrument chain (SupersawPad, AcidLead, AcidBass) reaches the same spectral targets as SmoothLead — they use different synthesis architectures
- That the result generalises beyond one 26-second reference clip

**Ultimate goal**: not a SA clone but an original voice. SA reproduction is the discipline that builds the full stack. See §7 for the transfer path.

---

## 4. Known Bugs: Prerequisites Before Running Any Experiment

Three bugs documented in `research/analysis/sa_parameter_measurement_methodology.md` contaminate experimental results regardless of how well spectral parameters are tuned. Resolve them in this order before interpreting any metric values.

### Bug 1 — Sidechain IIR Perpetual Duck

**Location**: `synth/effects.py:327`  
**Effect**: After the first kick, the IIR filter's residuals are normalised per-block, permanently ducking the pad at approximately 40% of its intended gain. The pad never recovers between kicks.  
**Impact on measurements**: All band energy measurements that include pad contribution (0–200 Hz, 200–500 Hz, 500–1k Hz) are understated after the first kick event. The EXP-000 baseline is therefore partially contaminated — band_energy_cosine may be worse than it would be if the pad were correctly levelled.  
**Fix**: Diagnose the IIR normalisation in `synth/effects.py:327`. The fix is likely resetting the per-block normalisation state between kicks rather than accumulating across the full render.  
**Urgency**: HIGH — fix before running EXP-001. Without this fix, improvements in EXP-001 may be partially masked by the pad suppression, making H1 appear weaker than it is.  
**Test after fix**: run `python tools/compare_audio.py ref.wav ref.wav --bpm 140.0534` — all Tier-1 should be ~1.0. Then re-render EXP-000 and compare against the recorded baseline.

### Bug 2 — Trancegate Shape Mismatch

**Location**: `instruments/pad.py`, `synth/effects.py`  
**Effect**: SA's actual trancegate function (from `research/strudel_debug.html` source):
```javascript
register('trancegate', (density, seed, length, x) => {
  density = reify(density).add(.5);
  return x.struct(rand.mul(density).round().seg(16).rib(seed, length)).fill().clip(.7);
});
```
This is a **probabilistic binary gate** — 16 discrete on/off steps per bar, randomly assigned based on density, clipped at 0.7 (not silenced to zero). The Python implementation uses a smooth raised cosine. These produce fundamentally different timbral envelopes: SA's gate produces hard step-cuts with 70% attenuation; the Python implementation produces smooth amplitude modulation.  
**Impact on measurements**: MFCC cosine and CLAP are sensitive to the timbral envelope character. The trancegate shape mismatch may account for a portion of the MFCC gap (currently 0.661) independently of filter cutoff. Phase 2 MFCC results cannot be cleanly interpreted while this bug is active.  
**Fix**: Replace the raised cosine with a 16-step binary pattern generator matching SA's `rand.mul(density).round()` logic, with `.clip(.7)` (attenuation to 70%, not silence).  
**Urgency**: MEDIUM — can run EXP-001 (spectral shape, Phase 1) while this is outstanding. Must fix before Phase 2 (mfcc_cosine investigation).

### Bug 3 — BPM Hardcoded in SupersawPad

**Location**: `instruments/pad.py:91`  
**Effect**: Trancegate step timing is computed from a literal `140` rather than the song's BPM parameter. At hey_angel's BPM of 140.0534, the drift is ~19 ms over 15 bars — acceptable but not correct.  
**Impact**: Minimal for hey_angel specifically. Becomes a hard blocker when generalising to songs at different BPMs (Workflow B, §6).  
**Fix**: Replace the literal `140` with `self.bpm` or equivalent parameter passed at construction.  
**Urgency**: LOW for hey_angel; HIGH before generalising.

---

## 5. Tool Reference: What to Trust and What Not To

Before using any number from the analysis pipeline, consult this table.

| Tool | Reliable outputs | Known failure modes — do NOT trust these |
|---|---|---|
| `tools/compare_audio.py` | Tier-1 perceptual gates: CLAP cosine, spectral_centroid_ratio, band_energy_cosine, mfcc_cosine; Tier-2: rms_envelope_r, onset_xcorr_peak, chroma_cosine | `kick_phase_err_ms` unreliable on hey_angel (F2 bass at 87Hz bleeds into 50–120Hz kick bandpass); `mfcc_dtw_dist` threshold was never calibrated (typical value 178 vs threshold 0.30 — broken, kept for historical continuity only); CLAP requires `pip install laion-clap` and downloads 150MB checkpoint on first run |
| `tools/spectrogram.py` | Band energy in dB (sub/bass/mid/hi-mid/air relative to sub); brightness % above 2kHz; qualitative spectral shape | Absolute centroid values differ from compare_audio.py due to different hop size and native SR — NOT authoritative for gating; use compare_audio.py values for any threshold comparison |
| `tools/analyse_timbre.py` | Filter cutoff (−18 dB point of spectral envelope) — reliable even in blended Demucs stems; ADSR estimates from onset windows; portamento rate | Oscillator type classification (saw/sine/square/triangle) — unreliable when Demucs filtering suppresses harmonics above 2nd partial; all three stems classify as "sine" on hey_angel regardless of true oscillator; fundamental frequency — unreliable for blended stems (picks lowest spectral peak, not true fundamental of the target voice) |
| `tools/extract_drum_pattern.py` | Hi-hat step pattern at 16 steps per bar (acceptable when alignment error < 20ms); BPM confirmation | Kick step pattern — contaminated by F2 bass (87Hz) bleeding into the 50–120Hz kick bandpass; hey_angel kick alignment error is 34.5ms = unreliable; always verify kick pattern manually against `hey_angel_analysis.md` |
| `tools/stem_separation.py` | Bass stem: fundamental pitch and sub-bass filter cutoff reliable; Drums stem: hi-hat and kick separation reliable for frequency analysis | Synth melody lead → classified as "vocals" (contaminated by high E5 pluck bleed); arpeggiated high pluck → classified as "guitar"; "other" stem is pad + bleed residual from multiple sources |
| `tools/analyse_audio.py` | Key detection, chord progression, BPM confirmation from the full mix | Chord detection unreliable in heavily filtered electronic music with sparse harmonic content |
| `tools/audio_to_midi.py` | Pitch contour extraction from vocals/lead stems (works well on clean monophonic material) | Pitch tracking on blended or highly reverberant material; poly-phonics |
| `research/strudel_debug.html` | Ground-truth parameter values from running SA's actual Strudel code in-browser | Only as authoritative as the OCR extraction accuracy; trancegate shape was previously inferred as "cosine from angle=45" — this is wrong (see Bug 2 above) |
| `song/theory.py` constants | BPM=140.0534 (confirmed from multiple sessions); G natural minor (confirmed); `rlpf_to_hz()` formula (confirmed); FILTER_ARC slider values (OCR confirmed) | `TRANCEGATE_AMOUNT=0.7` — developer override, SA uses 1.0; `GAIN_PAD=1.50` — developer override, SA uses `.pg(.5)=0.5`; `lpenv decay_s=0.80` — no SA source, hand-tuned; any constant annotated `# SA confirmed` that appears only in one OCR session — treat as medium-confidence |

---

## 6. Workflow A: Reproducing "hey angel" Right Now

Follow these steps in order. For the rationale behind each decision, read `synthesis_parameter_methodology.md`. For tracking, fill in `experiment_log.md` after every step.

### Step 0 — Environment and bug check

```bash
# Verify compare_audio.py is working end-to-end
python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav \
    research/reference_audio/hey_angel_trimmed.wav --bpm 140.0534
```

Expected: CLAP ≥ 0.97, centroid_ratio ≈ 1.000, band_energy ≈ 1.000, mfcc ≈ 1.000, OVERALL PASS.  
If CLAP returns None: `pip install laion-clap torchvision` then re-run (first run downloads ~150MB).  
If any Tier-1 gate fails on a self-comparison: the tool is broken; do not proceed.

Confirm Bug 1 status. If `synth/effects.py:327` IIR sidechain bug is NOT yet fixed:
- You can still run EXP-001, but note in the log that the sidechain bug is active
- Interpret band_energy_cosine improvements as lower bounds (actual improvement may be larger once bug is fixed)
- Fix the bug before running EXP-004 (joint test)

### Step 1 — Confirm baseline (EXP-000)

```bash
python hey_angel_cover.py --bars 15 --wav /tmp/ha_EXP-000.wav
python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav \
    /tmp/ha_EXP-000.wav --bpm 140.0534
```

Expected baseline (from prior measurement): CLAP=0.385, centroid_ratio=0.567, band_energy_cosine=0.649, mfcc_cosine=0.661.  
If your values differ by more than 0.05 from these: the code has changed since baseline was recorded. Record new baseline as EXP-000b before continuing.

### Step 2 — H1: Lead filter cutoff (EXP-001)

**Change**: `instruments/smooth_lead.py` — raise `cutoff_hz` from `900.0` to `2400.0`.

**Why 2400 Hz**: The reference full-mix has 8.3% energy in the 1–2 kHz band; the generated mix has 2.1%. To pass energy through the 1–2 kHz band, the filter cutoff must substantially exceed 1000 Hz. At 2400 Hz, Butterworth harmonics up to the ~10th pass with minimal attenuation. Full derivation: `synthesis_parameter_methodology.md §5.1`.

```bash
# After editing instruments/smooth_lead.py cutoff_hz=2400.0:
python hey_angel_cover.py --bars 15 --wav /tmp/ha_EXP-001.wav
python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav \
    /tmp/ha_EXP-001.wav --bpm 140.0534 > /tmp/EXP-001_compare.txt
```

**Fill in experiment_log.md EXP-001 row with all metric values.**

**Decision**:
- `band_energy_cosine` increased by ≥ 0.05 → H1 supported, continue
- `band_energy_cosine` did NOT increase by ≥ 0.05 → H1 rejected; revert `cutoff_hz` to 900.0, add REJECT row to log, diagnose
- `centroid_ratio` > 1.30 → cutoff overshot; reduce to 1800 Hz and re-run as EXP-001b
- `mfcc_cosine` dropped by > 0.05 → the new timbre diverges from reference character; reduce cutoff to intermediate (e.g. 1800 Hz) as EXP-001b

### Step 3 — H3: Bass harmonic content (EXP-003)

**Change**: `hey_angel_cover.py` — raise bass G1 note's `cutoff_slider` from `0.26` to `0.38`.

**Why**: `cutoff_slider=0.26` → `rlpf_to_hz(0.26) ≈ 83 Hz` — kills the G2 harmonic at 98 Hz. The reference has 49.8% of energy in 0–200 Hz; the generated mix has 25.8%. Raising the slider to 0.38 → `rlpf_to_hz(0.38) ≈ 350 Hz` passes G2 (98 Hz) and G3 (147 Hz), adding warmth to the sub-bass.

```bash
# After editing hey_angel_cover.py bass G1 cutoff_slider=0.38:
python hey_angel_cover.py --bars 15 --wav /tmp/ha_EXP-003.wav
python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav \
    /tmp/ha_EXP-003.wav --bpm 140.0534 > /tmp/EXP-003_compare.txt
```

**Fill in EXP-003 row.**

**Decision**: 0–200 Hz band fraction increased by ≥ 5 percentage points → H3 supported. If `rms_envelope_r` drops significantly (bass harmonics clashing with kick sub-bass), reduce cutoff_slider to 0.32 as EXP-003b.

### Step 4 — H2: Hi-hat gain (EXP-002)

**Must run AFTER EXP-001 is evaluated.** The correct hi-hat gain target depends on the post-H1 harmonic/percussive ratio.

**Context**: The 4k+ percussive fraction (20.3%) already matches the reference (21.0%). The full-mix 4k+ deficit (0.5% vs reference 9.3%) is because harmonic pileup swamps the percussive content at lower bands. Once H1 reduces the 200–500 Hz pileup, the percussive content's share of the total mix will rise automatically. H2 is fine-tuning, not the primary fix.

**Target**: After H1, measure the post-EXP-001 4k+ band fraction. The gap between that value and 9.3% is what H2 must close. Typical gain multiplier: 1.5–3× from current 0.25 effective value.

```bash
# After determining target gain from EXP-001 band measurements:
# Edit hey_angel_cover.py: _gain_hihat = [target value]
python hey_angel_cover.py --bars 15 --wav /tmp/ha_EXP-002.wav
python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav \
    /tmp/ha_EXP-002.wav --bpm 140.0534 > /tmp/EXP-002_compare.txt
```

**Fill in EXP-002 row.**

### Step 5 — H4: Joint Phase 1 (EXP-004)

Apply H1 + H2 + H3 simultaneously (all three changes active in the same render):

```bash
python hey_angel_cover.py --bars 15 --wav /tmp/ha_EXP-004.wav
python tools/compare_audio.py research/reference_audio/hey_angel_trimmed.wav \
    /tmp/ha_EXP-004.wav --bpm 140.0534 > /tmp/EXP-004_compare.txt
```

**Expected**: `band_energy_cosine` ≥ 0.85, `spectral_centroid_ratio` ∈ [0.70, 1.30].  
If both pass → Phase 1 complete. Proceed to Phase 2.  
If one or both fail → Phase 2 investigation begins early; the spectral shape alone is not sufficient.

### Step 6 — Phase 2: MFCC gap (if mfcc_cosine < 0.80 after EXP-004)

MFCC cosine measures the timbral fingerprint — the characteristic spectral envelope shape. After fixing the filter cutoff (Phase 1), MFCC should improve automatically because MFCC is a spectral envelope representation. If it does not:

**(a) Is Bug 2 (trancegate shape) still active?**  
The probabilistic binary gate vs smooth cosine produces different timbral envelopes. Fix Bug 2 (§4 above) and re-run. Add new EXP row.

**(b) Is the filter resonance (Q) significantly non-zero in the reference?**  
Run `tools/analyse_timbre.py` on the vocals stem from `research/reference_audio/stems/htdemucs_6s/hey_angel/vocals.wav`. If the reported resonance Q is > 0.3, the reference lead has a resonance peak not present in SmoothLead. Add resonance parameter to SmoothLead, set to measured value, re-run.

**(c) Is oscillator type the cause?**  
Despite `analyse_timbre.py` classifying the vocals stem as "sine" (unreliable — see §5), you can test oscillator type empirically: switch SmoothLead from sine to filtered sawtooth oscillator, re-run compare_audio.py. If mfcc_cosine improves, the reference likely uses a filtered saw. If it does not improve, oscillator type is not the gap.

### Step 7 — Phase 3: CLAP gap (if clap_cosine < 0.70 after Phases 1+2)

CLAP captures holistic style: genre feel, timbral character, rhythmic texture, spatial character — all jointly. If centroid_ratio and band_energy_cosine are passing but CLAP is still below 0.70, the remaining deficit is in dimensions that spectral shape alone does not address.

**Diagnose using Tier-2 structural metrics:**

- `onset_xcorr_peak` < 0.40 (currently 0.488 — PASS, so not a blocker today): rhythmic event timing is off. Investigate trancegate pattern match vs reference, kick/hihat timing.
- `rms_envelope_r` < 0.70 (currently 0.818 — PASS): energy trajectory over time is wrong. The sidechain pump character or reverb decay shape is diverging. Investigate `SchroederReverb` wet level (currently `wet=0.15`), sidechain `attack_s` (currently 0.16s).
- `chroma_cosine` < 0.80 (currently 0.906 — PASS): harmonic content or key is wrong. Unlikely given key is confirmed G minor, but worth checking if it drops after Phase 1–2 changes.

**If Tier-2 diagnostics are all PASS but CLAP is still low**: the gap is in timbral texture that CLAP detects but our Tier-2 metrics do not. The most likely remaining causes: reverb character, delay feedback pattern on the lead voice (currently `FeedbackDelay` is absent from hey_angel_cover.py's SmoothLead — verify), or arrangement density (number of simultaneous layers).

### Step 8 — Convergence

OVERALL PASS from `tools/compare_audio.py` with all four Tier-1 metrics passing simultaneously. Document in `experiment_log.md`. Then:
- Branch `sidequest/pluck-arp-analysis` may be merged to main
- Proceed to Workflow B (§7) to validate on a second SA reference clip before touching the v3 engine

---

## 7. Workflow B: Reproducing a New SA Song

Given any SA YouTube clip as a WAV file, this is the complete workflow to arrive at a synthesised cover that passes `compare_audio.py`.

### Phase 0 — Audio preparation

```bash
# Trim to the groove section (skip silence, cut at fade-out)
# Typically: find where the kick first enters and where the fade begins
ffmpeg -i source.wav -ss [start_seconds] -to [end_seconds] \
    -ar 44100 research/reference_audio/[song]_trimmed.wav

# HTDemucs 6-stem separation
python tools/stem_separation.py research/reference_audio/[song]_trimmed.wav
# Output: research/reference_audio/stems/htdemucs_6s/[song]/{bass,drums,vocals,guitar,other,piano}.wav
```

### Phase 1 — Structural analysis

**(a) Beat grid and drum pattern**
```bash
python tools/extract_drum_pattern.py \
    research/reference_audio/stems/htdemucs_6s/[song]/drums.wav
```
→ Confirms BPM (SA always uses 140.0534 — verify matches)  
→ Hi-hat step pattern: trust if alignment error < 20ms  
→ Kick pattern: do NOT trust the extracted pattern; cross-reference against `hey_angel_analysis.md` and `switch_angel_vocabulary.md` (SA's canonical kick is steps 0,4,8,11,14 — may vary per song)

**(b) Key and harmony**
```bash
python tools/analyse_audio.py research/reference_audio/[song]_trimmed.wav
```
→ SA always uses G natural minor — confirm, but do not be surprised if confirmed  
→ Chord progression: SA uses static root or slow-moving chords; cross-reference with `switch_angel_vocabulary.md`

**(c) Melody pitch contour**
```bash
python tools/audio_to_midi.py \
    research/reference_audio/stems/htdemucs_6s/[song]/vocals.wav
```
→ Extracts pitch sequence from the melody lead stem  
→ Confirm with `tools/spectrogram.py` on the vocals stem (visual confirmation)

**(d) Song structure**
Compare the identified voices against `research/analysis/switch_angel_song_structure.md`. SA's build order is consistent across all 5 observed sessions:
1. Kick → 2. Pad (root) → 3. Lead (root) → 4. Lead melody → 5. Pad chord movement → 6. Lead chord → 7. Clap → 8. FM on lead → 9. Pulse texture → 10. Hi-hat/scrub

No breakdown-drop-rebuild. The rlpf slider arc is the primary dynamic variation tool.

### Phase 2 — Timbre parameter extraction

Run `tools/analyse_timbre.py` on each stem. Record results with confidence level from §5 (Tool Reference).

```bash
for stem in bass drums vocals other; do
    python tools/analyse_timbre.py \
        research/reference_audio/stems/htdemucs_6s/[song]/${stem}.wav
done
```

**From the results — what to trust and what to use:**

| Stem | Trust and use | Note and verify before using |
|---|---|---|
| `bass.wav` | Filter cutoff (−18dB point) → set bass `cutoff_slider` or `cutoff_hz`; fundamental pitch → confirm root note | Oscillator type (likely to show sine regardless of truth) |
| `drums.wav` | Kick: fundamental frequency, decay time; Hi-hat: HPF cutoff estimate, decay time | Kick alignment error → verify manually if > 20ms |
| `vocals.wav` | Filter cutoff (−18dB point) → starting point for lead `cutoff_hz` (will need upward adjustment for pluck contamination, as in hey_angel); ADSR attack/decay; portamento rate | Oscillator type (unreliable); centroid (contaminated by pluck bleed); fundamental (unreliable) |
| `other.wav` | Centroid and cutoff for pad layer | Everything else (blended residual from multiple sources) |

### Phase 3 — SA vocabulary constants (do not re-measure these)

From `research/analysis/switch_angel_vocabulary.md` and confirmed across all 5 sessions — these are always the same. Copy directly from `hey_angel_cover.py`:

- BPM: 140.0534
- Key: G natural minor, root G1 (MIDI 43)
- Trancegate: density=1.5, seed=45, length=1 (once Bug 2 is fixed, these drive the probabilistic binary gate)
- rlpf_to_hz formula: `(slider × 12)^4` (from `song/theory.py`)
- Filter arc starting points: `FILTER_ARC` in `song/theory.py` (mid-groove slider ≈ 0.5–0.6)
- Sidechain: depth=0.721, attack_s=0.16 (from hey_angel measurement; applicable to SA generally)
- Reverb: `SchroederReverb(room_size=0.45, wet=0.15)` (starting point; may need per-song tuning)

**Per-song measurements that MUST be taken** (not constant across songs):
- Melody pitch contour (Step 1c above)
- Bass step pattern and portamento rate
- Any pluck or arp voices present (not all SA songs have the E5 high pluck)
- Section-specific filter slider positions (if the target clip has a distinctive filter arc)

### Phase 4 — Build the cover script and establish baseline

Copy `hey_angel_cover.py` as the template. Update parameters from Phase 2 measurements. Run `compare_audio.py` to establish EXP-000 for the new song. Then follow Workflow A (§6) — the same H1–H4 experimental sequence applies to any SA song because the root cause of spectral mismatch (lead filter cutoff too low, bass harmonic content insufficient) is likely to recur.

---

## 8. From Cover Reproduction to the Generative Engine

### What CLAP ≥ 0.70 on hey_angel actually proves

- The source-filter measurement workflow works: `analyse_timbre.py` → filter cutoff estimate → synthesis parameter → measurable spectral improvement
- `tools/compare_audio.py` Tier-1 thresholds are correctly calibrated for SA-style trance
- The SmoothLead instrument chain can produce timbres perceptually indistinguishable from the reference at the CLAP level
- The experimental protocol (hypothesis → falsification → measure → decide) correctly attributes spectral changes to parameter changes

### What it does NOT prove about `trance_stream.py`

| Unproven | Why | How to validate it |
|---|---|---|
| AcidLead timbre | Different synthesis architecture (supersaw + FM, not filtered sine); different parameter space | Run compare_audio.py on trance_stream.py renders vs SA 90s clips from `research/reference_audio/` |
| AcidBass cutoff arc | FILTER_ARC values in `song/theory.py` are OCR starting points; not measured from audio | Apply same analyse_timbre.py workflow to bass stem of any SA 90s reference clip |
| SupersawPad character | Supersaw (5 saws, detune=0.6) with lpenv(2) + trancegate — much more complex than SmoothLead | Separate evaluation: compare SupersawPad-only render vs SA pad stem |
| Generative melody correctness | hey_angel uses a hardcoded C4→F#3 glide; the engine generates melody from scale + rules | Listener test (BR-1 acceptance criterion, `docs/feature-spec.md §1.1`) |
| Arrangement phase coherence | hey_angel has no phase transitions; engine has Intro/Groove/Breakdown/Build/Drop | Full engine render evaluation; compare phase transitions against switch_angel_song_structure.md |

### Transfer path from cover to engine (in order)

**1. Fix the bugs in the engine too.**  
The IIR sidechain bug (Bug 1) and trancegate shape mismatch (Bug 2) exist in `synth/effects.py` and `instruments/pad.py`. These are shared by both hey_angel_cover.py and trance_stream.py. Fix them once, in the shared location. Bug 3 (BPM hardcoded) only matters for the engine if it runs at BPMs other than 140.

**2. Use the validated cutoff target methodology for AcidLead.**  
The hey_angel work proves the methodology: measure vocals stem −18dB point from any SA reference clip, adjust upward for pluck contamination, target the 1–2 kHz band energy. Apply this to AcidLead by running analyse_timbre.py on any SA 90s reference clip's vocals stem and targeting the same band energy ratios.

**3. Use compare_audio.py against the 90s reference clips for engine evaluation.**  
Files: `research/reference_audio/-pDO2RhcGhM_90s.wav`, `3fpx7Scysw4_90s.wav`, `GWXCCBsOMSg_90s.wav`, `iu5rnQkfO6M_90s.wav`, `vn9VDbacUgQ_90s.wav`. These are ground-truth SA full-engine renders. Once the cover passes, evaluate `trance_stream.py` renders against these same clips using the same Tier-1 thresholds.

**4. Address arrangement and melody separately.**  
Spectral parameter validation (cover reproduction) and arrangement/melody correctness (generative engine) are independent. Do not conflate them. The CLAP score on a static clip does not tell you whether the arrangement is structurally coherent. BR-1 (listener test) is the correct evaluation for the arrangement.

### Death Angel: the transition from SA clone to original voice

The SA reproduction work is not an end in itself. `docs/feature-spec.md` BR-1 says "sounds like Switch Angel's style" — not "is a SA clone." The path from "validated SA reproduction" to "Death Angel original voice":

**Step 1 — Identify the SA-specific parameters vs the genre-defining parameters.**  
SA-specific (swap these for Death Angel's identity): G minor tonality and root, 140 BPM, her specific rlpf filter arc trajectory, her specific kick step pattern (0,4,8,11,14), her G1 bass root.  
Genre-defining (keep these as the architecture): sidechain pump depth (~0.72), trancegate density (~1.5), supersaw detune range, kick + bass + lead + pad + arp five-voice structure, delay on lead, additive build order.

**Step 2 — Vary the SA-specific parameters while measuring that the genre-defining perceptual identity remains.**  
Use compare_audio.py against the SA 90s clips as a *floor* (must remain recognisably trance, score must stay above ~0.50) rather than a *ceiling*. Death Angel should score 0.50–0.65 against SA clips — perceptually in the same genre, but not an exact clone.

**Step 3 — Define a Death Angel target.**  
Either: (a) an SA clip running through Death Angel's parameter variations (different key, different BPM, different filter arc), or (b) a conceptual perceptual description ("darker, more industrial, slower sidechain recovery"). Option (a) is more measurable.

This step is not yet scoped. It belongs to the session after hey_angel and at least one other SA cover reach OVERALL PASS.

---

## 9. Immediate Action Items (Priority Order)

What to do in the next work session, before touching any synthesis parameters:

1. **Fix Bug 1** (`synth/effects.py:327`, IIR sidechain perpetual duck) — HIGH. Without this fix, band_energy_cosine improvements in EXP-001 will be understated. See `research/analysis/sa_parameter_measurement_methodology.md §4` for the diagnosis; fix the IIR normalisation reset.

2. **Confirm EXP-000 baseline after Bug 1 fix** — Re-render and re-measure. Record as EXP-000b in experiment_log.md if values differ from the recorded baseline by > 0.05.

3. **Run EXP-001** (H1: SmoothLead `cutoff_hz` 900 → 2400) — the single highest-leverage change. Full procedure: Workflow A §6, Step 2. Fill in experiment_log.md.

4. **Fix Bug 2** (`instruments/pad.py` trancegate shape) — MEDIUM. Fix before Phase 2 MFCC investigation. See `sa_parameter_measurement_methodology.md §2` for SA's actual function source.

5. **Run EXP-002, EXP-003** (hi-hat gain and bass cutoff) — after EXP-001 is evaluated. These are smaller changes; run both, then run EXP-004 (joint).

6. **If OVERALL PASS on hey_angel**: run Workflow B on `research/reference_audio/-pDO2RhcGhM_90s.wav` to validate generalisability before touching `trance_stream.py`.

7. **Apply to `trance_stream.py`**: update AcidLead filter target, fix shared bugs, re-evaluate against 90s SA reference clips with compare_audio.py.
