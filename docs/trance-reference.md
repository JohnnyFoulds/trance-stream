# Trance Music Generator: Technical and Musical Reference

**Project:** `trance_stream.py` — a procedural trance music generator targeting the sound of Switch Angel  
**Last updated:** 2026-07-08  
**Audience:** Software engineers learning music production

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Procedural Music Generation: Academic Foundations](#2-procedural-music-generation-academic-foundations)
3. [Trance Music Vocabulary](#3-trance-music-vocabulary)
4. [Audio Analysis Tools for Style Matching](#4-audio-analysis-tools-for-style-matching)
5. [Reverb and Mixing: Implementation Guide](#5-reverb-and-mixing-implementation-guide)
6. [Switch Angel Specific Analysis](#6-switch-angel-specific-analysis)
7. [Actionable Next Steps](#7-actionable-next-steps)

---

## 1. Executive Summary

`trance_stream.py` is a fully implemented, self-contained procedural trance music generator. It synthesises five independent voices — kick, bass, lead, arp, and pad — entirely from mathematics, streams stereo audio in real time, and exports MIDI on exit. The composition engine uses a cellular automaton (Wolfram Rule 30) to drive rhythmic gating and an arrangement state machine to cycle through Intro → Groove → Breakdown → Build-up → Drop phases automatically.

The acoustic target is the live-coded trance output of Switch Angel, a Strudel-based artist. Her sets define a specific sound fingerprint: detuned supersaw leads, gated pads, four-on-the-floor kick with sidechain pumping, slow harmonic rhythm (one chord per four bars), and a clear Breakdown-to-Drop emotional arc. The generator is architecturally sound and fully runnable. The gap between current output and the target sound is a set of specific tuning mismatches — register assignments, filter cutoff values, and missing reverb — documented in Section 6 and addressed in Section 7.

### Why this research matters

Building a convincing trance generator requires fluency in three distinct domains simultaneously:

- **Music production vocabulary** — to understand what "sidechain pumping" or "supersaw detuning" means acoustically and numerically
- **Procedural generation algorithms** — to understand which algorithmic choices produce musical vs mechanical output
- **Audio measurement tools** — to objectively verify that a code change moved the output closer to the target sound

The four research areas compiled here address all three domains. The procedural generation literature provides both algorithm validation (the approach used here matches state-of-the-art methods) and quality metrics (21 measurable melodic features from M6(GPT)3). The trance vocabulary provides specific numerical targets for every production parameter. The audio feature measurement guide connects those targets to computable numbers. The reverb/mixing reference provides implementation code for the missing acoustic layer.

---

## 2. Procedural Music Generation: Academic Foundations

### 2.1 The Approach Landscape

Academic procedural music generation divides into four main algorithmic families, ordered by how much control they give versus how much data they require:

**Markov Chains.** The simplest stochastic approach. A transition matrix `P[note_i][note_j]` encodes the probability that note `j` follows note `i`. First-order Markov chains are memory-less; second-order condition on the last two states. Advantages: trivially seeded, fast, no training data needed. Disadvantages: poor long-range coherence; rhythmic inconsistency emerges over sequences longer than 8 bars (Hsu and Greer 2023). Practical limit is first or second order before the matrix becomes too sparse.

`trance_stream.py` uses a Markov-adjacent approach for the Markov-like drum fills. The bass patterns (`rolling`, `offbeat`, `tb303`) are deterministic rule tables — a degenerate first-order Markov chain where transition probabilities are 0 or 1.

**Cellular Automata.** A 1D CA (Rule 30, width 32) provides the aperiodic, non-repeating bit pattern that gates the lead and arp voices. Rule 30 was selected because it is chaotic — its output is not periodic at any small period — which prevents the mechanical repetition that makes procedurally generated music sound like a drum machine. The CA advances one step per 16th-note, so a 32-wide row produces 32 independent binary signals per step, of which four named positions (`LEAD_GATE`, `ARP_GATE`, `PHRASE_BIT`, `ARP_DIR_BIT`) are used. A 2025 paper (Lugo and Alatriste-Contreras) demonstrates that 2D CAs governed by music-theory interval rules can produce large-scale organised patterns from random initial conditions — the same principle at work here, applied to a 1D case with external harmonic constraints.

**Rule-based systems with genetic algorithms.** The most technically detailed procedural algorithm in the current literature is M6(GPT)3 (Pocwiardowski et al. 2025), which uses a genetic algorithm with 11 musically motivated mutation operators to generate melodies. The fitness function evaluates 21 melodic features (see Section 2.3 below). The key insight is that musical quality can be decomposed into measurable scalar features and optimised directly. `trance_stream.py` does not run a genetic algorithm — it selects notes greedily at each step using voice-leading rules — but the 21 features provide an excellent checklist for diagnosing melodic quality without running an optimiser.

**Neural / LLM approaches.** MusicVAE (Roberts et al. 2018) and GPT-based systems operate on large datasets and produce musically sophisticated output, but they require training data, cannot run in real time on a laptop, and are not deterministically seedable in the same way. They are not suitable for this project's constraints (NFR-1: numpy + sounddevice only). The LLM-structure approach in M6(GPT)3 uses GPT-4 to produce a JSON composition specification (BPM, scale, chord progressions, valence-arousal coordinates), which then drives rule-based generators — a clean separation that is architecturally similar to what `trance_stream.py` does via its `MOODS` dictionary.

### 2.2 Application to Real-Time Trance Generation

The 4/4 bias of the Groove dataset (98.96% of loops in 4/4 time, per M6(GPT)3's analysis) means all deep learning percussion models are calibrated to the trance grid. This is a feature for this project: any standard kick pattern algorithm will naturally produce four-on-the-floor patterns without modification.

The valence-arousal model (M6(GPT)3, based on Russell 1980) maps directly onto trance's tension-and-release arc:

| Phase | Valence | Arousal | Musical effect |
|---|---|---|---|
| Intro | 0 (neutral) | 0.3 (low) | Sparse, filtered, anticipatory |
| Groove | 0.5 (positive) | 0.8 (high) | Full energy, all voices, dense |
| Breakdown | -0.2 (bittersweet) | 0.2 (low) | Emotional, sparse, reverberant |
| Build-up | 0 (tense) | 0.6–0.9 (rising) | Tension building, snare roll, riser |
| Drop | 0.7 (euphoric) | 1.0 (maximum) | Everything on, maximum impact |

The current arrangement state machine (`PHASE_TARGET_GAINS`) implements this implicitly through per-voice gain scalars.

### 2.3 Quality Metrics from the Literature

M6(GPT)3 evaluates melodic quality with 21 features normalised to (0,1). The subset most relevant to diagnosing the current generator:

| Feature | What it measures | Good trance value |
|---|---|---|
| % unique notes per measure | Melodic diversity | 0.3–0.6 (not stuck on one note) |
| % notes in scale | Tonality | >0.90 (stay in minor scale) |
| % notes in current chord | Harmonic alignment | 0.5–0.8 |
| Tonal (pitch) range | Register span | 12–24 semitones (1–2 octaves) |
| % rests in sequence | Breathing room | 0.10–0.20 |
| Melodic contour | Phrase shape | Non-monotone (arc or wave) |
| Repeated fragment length | Motivic coherence | 4–8 steps (short motif) |
| Count of consecutive stepwise intervals | Conjunct motion | High (trance leads move by step) |
| Off-beat notes | Syncopation | Low for trance (grid-aligned) |

Inter-track dissonance (M6(GPT)3 §4.1): intervals modulo 12; perfect fifth (7 semitones) between voices scores +15; thirds and sixths score +8; tritone (6 semitones) receives penalty -30. The current three-voice lead stack (base, +7, -7 semitones) scores well — two perfect fifths — but should be validated against the bass note to ensure the combination does not create tritones.

Subjective quality benchmarks (M6(GPT)3 Table 5, 23-listener test, 1–5 scale): the system scored 3.29 ± 0.09 on Richness and Diversity, 3.20 ± 0.09 on Memorability. A target of >3.0 on a similar informal test ("does this sound like trance?") is a reasonable threshold for T-002 (the listener genre-identification acceptance test).

**Groove pattern similarity** (Hsu and Greer 2023): measures rhythmic consistency of generated sequences against training data patterns. Equivalent to asking: "does the kick pattern stay on the four-on-the-floor grid?" RNN models outperformed Markov chains on this metric — but for trance, a deterministic rule (kick on every beat-4-position) trivially achieves maximum groove pattern similarity. This metric is not a diagnostic concern for this project.

**Pitch class histogram entropy** (Hsu and Greer 2023): measures tonal stability. For trance in a minor key, the five most-used pitch classes should dominate (entropy ≈ 2.0–2.6 out of max 3.58). An entropy below 1.5 means the melody is stuck on one or two notes; above 3.4 means it is chromatic noise.

### 2.4 Key Papers

| Citation | Relevance |
|---|---|
| Pocwiardowski et al. (2025) arXiv:2409.12638 | M6(GPT)3: genetic algorithm with 21 melodic quality metrics; most detailed procedural system available |
| Tokui (2020) arXiv:2011.13062 | GAN with Genre Ambiguity Loss for EDM rhythms; only paper targeting EDM rhythm generation specifically |
| Roberts et al. (2018) arXiv:1803.05428 | MusicVAE: hierarchical VAE for latent-space interpolation of musical phrases |
| Briot, Hadjeres, Pachet (2017) arXiv:1709.01620 | Survey: five-dimension taxonomy (objective/representation/architecture/challenge/strategy) |
| Hsu and Greer (2023) arXiv:2309.08027 | Markov vs RNN for jazz blues; RNN outperforms Markov on groove and pitch entropy |
| Lugo and Alatriste-Contreras (2025) arXiv:2411.19844 | 2D cellular automaton for music; music-theory rules produce organised patterns from random CA initial states |

---

## 3. Trance Music Vocabulary

### 3.1 Synthesis Vocabulary

**Supersaw.** A composite oscillator built from multiple detuned sawtooth waves. Originates from the Roland JP-8000 (1996), which stacked 7 sawtooth waves in one oscillator. The standard for trance synthesis. Each oscillator generates a bipolar sawtooth wave: `output = 2 * (phase % 1.0) - 1`. Multiple detuned copies beat against each other, producing the characteristic moving, chorus-like width.

Key parameters:
- Voices per note: 7 (industry standard; N=3 is thin; N=11 gives diminishing returns)
- Detune spread (uplifting trance): 10–25 cents total spread across all voices
- Detune spread (dark/harder trance): 25–35 cents total spread
- Too little (< 5 cents): sounds thin, indistinguishable from a single oscillator
- Too much (> 35 cents): sounds out-of-tune rather than chorus-like; beating frequency becomes audible as pitch instability

In `trance_stream.py`: `SAW_COUNT_LEAD = 7`, `DETUNE_CENTS_LEAD = 50.0` (see Section 6 — this is too wide).

**IIR Low-pass Filter.** A first-order one-pole filter applied to the supersaw output to remove harsh high-frequency content and enable filter sweeps. Transfer function:
```
y[n] = (1 - a) * y[n-1] + a * x[n]
a = (2π × f_c) / (2π × f_c + SAMPLE_RATE)
```
At `f_c = 12000 Hz` (current `LEAD_CUTOFF_BASE`): `a ≈ 0.945`. Almost all signal passes through; the filter has virtually no effect. At `f_c = 2000 Hz`: `a ≈ 0.222`. Strong low-pass effect; harmonics above 2 kHz are significantly attenuated. At `f_c = 500 Hz`: the oscillator sounds like a warm sine wave with first harmonic present.

**Filter LFO.** A low-frequency oscillator (< 1 Hz) that modulates the filter cutoff frequency over time, producing the sweeping "wah" movement characteristic of trance leads. The LFO uses a sine wave: `cutoff(t) = base + sweep * sin(2π * lfo_phase)`. The perceptual effect requires that the sweep covers a musically meaningful range of the filter's response — which means the base cutoff must be in a frequency range where the filter audibly acts on the signal (500–4000 Hz for the lead).

**Trance Gate.** A step-sequenced binary amplitude pattern that chops pad and lead voices on a 16th-note grid, creating the pulsing, rhythmic stutter texture. Each of 16 steps per bar is either open (full amplitude) or closed (near-silence). Derived from Switch Angel's `.mask()` and `tgate` functions in Strudel. Critical implementation detail: gate transitions use a short ramp (1–8 ms) to prevent clicks at step boundaries.

Switch Angel's implementation uses `.clip(.7)`, which means closed slots sustain at 70% amplitude before cutting off — a softer chop than a hard gate. `trance_stream.py` models this by sustaining to 70% of the step duration then applying a cosine fade-out when the following step is closed (`apply_tgate` lines 1126–1137).

**Sidechain Compression.** Volume of bass and pad dips on every kick hit and recovers between hits, creating the "pumping" forward motion essential to trance. Parameters (at 140 BPM):
- Duck depth: volume drops to 5–30% of normal level (0.05–0.30 gain multiplier)
- Recovery: over 8–12 steps (~0.34–0.51 seconds at 140 BPM), returning to 1.0
- The lead and arp are NOT sidechained — they cut through the pump

Current implementation: `SIDECHAIN_DEPTH = 0.05` (drops to 5% — near silence, aggressive pump), `SIDECHAIN_RELEASE = 12` steps (~0.51 seconds recovery). The depth is appropriate for a pronounced pump. Recovery over 12 steps means the bass/pad are fully restored by the next kick hit — correct for four-on-the-floor at 140 BPM.

**Kick Synthesis.** A sine wave swept from ~160 Hz down to ~50 Hz with an exponential amplitude envelope. No additional harmonics needed. The pitch sweep creates the transient "thud" character. Sub content at ~50 Hz provides chest impact; the 100–160 Hz range provides the audible "punch". Formula:
```python
freq = KICK_F0 * (KICK_F1 / KICK_F0) ** (t / KICK_DECAY_S)  # geometric sweep
amp  = math.exp(-t / KICK_ENV_TAU)
sample = math.sin(2.0 * math.pi * phase) * amp
```
Current values: `KICK_F0 = 160 Hz`, `KICK_F1 = 50 Hz`, `KICK_DECAY_S = 0.10 s`, `KICK_ENV_TAU = 0.035 s`. These are within the typical range; fine-tuning by ear is appropriate.

**Stereo Panning of Supersaw Voices.** The N oscillators are spread across the stereo field using constant-power panning. For oscillator k out of N: `pan = (k / (N-1)) * 2 - 1` (range −1 to +1). Left channel weight: `cos((pan + 1) * π/4)`. Right channel weight: `sin((pan + 1) * π/4)`. This keeps total power constant regardless of pan position, preventing the mix from sounding louder in the centre than at the edges.

### 3.2 Harmonic Vocabulary

**Minor key dominance.** Trance overwhelmingly uses minor keys. The bittersweet quality of minor tonality supports the emotional arc from melancholic tension (Breakdown) to euphoric release (Drop). Common choices in real sets: A minor, F# minor, E minor, B minor. The generator derives a root deterministically from the seed string using MD5: `root = 48 + (md5_integer % 12)`, placing the root in the C3–B3 octave (MIDI 48–59).

**Core progressions** (Roman numeral notation, lowercase = minor, uppercase = major):

| Mood | Progression | Roman numerals | Character |
|---|---|---|---|
| `uplifting` | Am → F → C → G | i → VI → III → VII | Euphoric, soaring |
| `dark` | Am → Dm → Em → Am | i → iv → v → i | Intense, driving |
| `acid` | Am → G → F → G | i → VII → VI → VII | Hypnotic, circular |
| `progressive` | Am → Dm → A → G | i → iv → I → VII | Groovy, modal |
| `ambient` | Amaj7 → Gmaj7 → Fmaj7 → Gmaj7 | Imaj7 → VIImaj7 → VImaj7 → VIImaj7 | Floating |

**Scale degree roots** (semitones above tonic): i/I = 0, III/bIII = 3, iv/IV = 5, v/V = 7, VI/bVI = 8, VII/bVII = 10.

**Harmonic rhythm.** One chord per 4 bars is the trance standard. At 140 BPM with 16 bars per chord cycle, the full 4-chord progression repeats every ~27.4 seconds. Faster harmonic rhythm (every 2 bars) creates more movement; slower (every 8 bars) adds grandeur in breakdowns.

**Natural minor scale.** The seven pitch classes of the natural minor scale in semitones above the tonic: {0, 2, 3, 5, 7, 8, 10}. All melody, arp, and bass notes should come from this set (or the chord tones, which are a subset). Out-of-scale notes above 5% of total notes are flagged by `analyse_audio.py` as harmonic clashes.

**Chord voicings.** Standard trance uses additional intervals stacked above the root to create wider, more epic sounds:
- Big Room Add9: `[0, 2, 4, 7]`
- Epic Trance Stack: `[0, 4, 7, 11, 14]` (root + major third + fifth + major seventh + ninth)
- Anthem Lead Stack: `[0, 7, 11, 14]`

The current generator uses `chord_wide_voicing()` which returns `[mid-3, mid, mid+7]` — a minor third below, root, and perfect fifth above. This is harmonically stable but narrower than typical trance pad voicings.

**Suspended chords.** Sus2 and sus4 chords remove the third, replacing it with the second or fourth. Used at phrase endings and in build-ups to delay resolution. A sus4 before a resolving chord is idiomatic trance. Not currently implemented in the generator.

### 3.3 Rhythmic Vocabulary at 140 BPM

At 140 BPM with 16th-note resolution:
- One beat = 429 ms
- One 16th note (one step) = 107 ms
- One bar (16 steps) = 1714 ms

**Four-on-the-floor kick.** Fires on steps 0, 4, 8, 12 of each 16-step bar. This is the rhythmic foundation of all trance subgenres. In `trance_stream.py`: `step_in_bar % 4 == 0` triggers the kick in Groove, Drop, and Intro phases.

**Build-up half-time kick.** Fires only on steps 0 and 8 — beats 1 and 3 only. Creates tension by breaking the four-on-the-floor pattern without fully removing the kick.

**Rolling offbeat bassline** (`uplifting` mood): bass fires on every 16th note step (steps 0–15 inclusive), but each note has `steps_remaining = 1` so it does not overlap with the next note. Combined with sidechain compression, the bass pulses on each 16th note between and around the kick hits, creating the continuous 16th-note heartbeat pulse of trance.

**Offbeat bass** (`dark` mood): bass fires on beat 1 (step 0) and one additional syncopated hit at step 10. Creates a driving, slightly off-kilter feel.

**TB-303 pattern** (`acid` mood): root on steps 0, 3, 9; chromatic approach notes (+1 or −1 semitone) on steps 6 and 12. Simulates the acid bass slide pattern.

**Broken octave** (`progressive` mood): root on step 0, octave on step 7, root on step 9, fifth on step 13. Creates a bouncing, melodic bass line.

**Arp patterns.** A cycling arpeggio through the current chord tones across the full register (MIDI 60–96 for the ideal arp voice). Direction: ascending (`up`), descending (`down`), or alternating (`updown`). Rest probability: 10% per step. The arp reverses direction at phrase boundaries.

**Hi-hat synthesis.** Not currently implemented as a separate voice. Could be added as high-passed white noise with very short decay (5–20 ms) on steps 0–15 (constant 16th-note pulse) or on even-numbered steps (8th-note offbeats for lighter texture.

**Snare roll.** Not currently implemented. In the Build-up phase, a snare or clap on beats 2 and 4 (steps 4, 12), accelerating to 8th notes then 16th notes as the Drop approaches. This is a standard trance tension-building technique.

### 3.4 Arrangement Vocabulary

The arrangement structure implements the genre's standard emotional arc:

| Phase | Duration | Function | Voice activity |
|---|---|---|---|
| Intro | 4 bars (shortened) | DJ mix entry; establish tempo and key | Kick 0.4 (filtered), Pad 0.6 (filtered), others off |
| Groove | 16 bars | Establish the hook; full energy | All voices at full gain |
| Breakdown | 16 bars | Emotional heart; remove drive, add space | Kick off, Bass off, Lead 0.7 (with delay), Arp on, Pad on |
| Build-up | 16 bars | Tension building toward Drop | Kick half-time, Bass off, Lead off, Arp on, Pad on, Noise riser |
| Drop | 16 bars | Impact; full arrangement returns | All voices at full gain |

**Breakdown silence.** A single beat (4 steps) of complete silence at the end of the Build-up, immediately before the Drop. Maximises the perceived impact of the Drop re-entry. Currently not implemented in `trance_stream.py` — the Drop begins immediately after the Build-up reaches its last step.

**Phase transitions.** Voice gains ramp over `PHASE_TRANSITION_BARS = 2` bars at each phase boundary rather than switching abruptly. Implemented via `transition_step` counter and exponential approach: `cur += (target - cur) / remaining_steps`.

**Noise riser.** White noise that rises in amplitude throughout the Build-up phase, capped 4 bars before the Drop. High-pass filtered (the full noise spectrum would be muddy). Implemented at a fixed `0.04` amplitude scale — very quiet. May need to be louder or more prominently high-pass filtered to be audible over the pads.

### 3.5 Melodic Vocabulary

**Conjunct motion (the lead rule).** Consecutive notes within a phrase must be no more than `MAX_LEAD_INTERVAL = 7` semitones (a perfect fifth) apart. This produces the flowing, singing quality of trance leads. The current `select_lead_note()` function enforces this by selecting the nearest chord tone in the preferred direction.

**One note per bar.** The lead fires exactly once per bar (at `step_in_bar == 0`) and holds for the full bar. The trance gate applied downstream creates all rhythmic texture. This is a deliberate design choice: the lead is a slow melodic line, not a 16th-note sequence. With the current register of D4–D5 (12 semitones, one octave), only 2–3 distinct chord tones are available per chord, making the melody very static.

**Lead register.** Specified in the feature spec as MIDI 60–84 (C4–C6, 24 semitones). The current code uses MIDI 62–74 (D4–D5, 12 semitones) — half the intended range. This is the most significant melodic quality deficit in the current implementation.

**Phrase structure.** Short phrase: 64 steps (4 bars); long phrase: 128 steps (8 bars). `PHRASE_BIT` in the CA triggers a phrase reset when `phrase_step >= MIN_PHRASE_BARS * STEPS_PER_BAR`. At phrase reset, `prev_lead_note = None` so the melody can restart from a new position. `phrase_high_note` is halved (soft reset) to prevent the phrase peak from compounding upward indefinitely.

**Velocity model.** Three-layer model: structural accent by beat position (beat 1 = velocity 95, other beats = 80, off-beats = 65), phrase-shape climax boost (+15 when note equals phrase peak), and ±8 random variation for organic feel.

**Arp voice.** Cycles through chord tones across `[ARP_LOW, ARP_HIGH]` by incrementing/decrementing an index. Bounces at the pool boundaries. Current register: MIDI 48–62 (C3–D4), which places the arp BELOW the lead register (62–74). This is inverted from the typical trance arrangement where the arp soars above the lead.

### 3.6 Production Vocabulary

**Gain staging.** Per-channel amplitude levels before mixing:
- Kick: loudest element; dominates the sub-100 Hz range
- Bass: `BASS_LEVEL = 0.35` — second loudest; should be clearly audible under the kick
- Lead: `LEAD_LEVEL = 0.55` applied over 3 voices × (1/3 each) — sits above pads
- Pad: `PAD_LEVEL = 0.20` — atmospheric texture; should not compete with lead

**Soft-clip limiter.** Applied via `tanh(x * DRIVE) / DRIVE` with `DRIVE = 0.8`. Light saturation that prevents hard clipping at peaks. The `DRIVE` value determines how aggressively signals above 1/DRIVE are compressed. At 0.8, the saturation is audible at moderate levels. At 1.5 (earlier value), it crushed the kick transients.

**Delay.** The lead voice has a feedback delay with `_DELAY_MIX = 0.40` (40% wet) and `_DELAY_FEEDBACK = 0.35`, with delay time set to `0.4 × beat_samples`. At 140 BPM, one beat = 18,900 samples; the delay is 7,560 samples ≈ 171 ms. The standard trance delay is a dotted-eighth note (3/16 of a bar = 321 ms at 140 BPM). The current delay at 171 ms is shorter — approximately a triplet-eighth note — which gives a faster echo rhythm.

**Reverb.** Not currently implemented as a dedicated algorithm. The delay provides some spatial depth on the lead, but the Breakdown phase needs significant reverb (2–4 second decay on the lead, 3–6 second decay on pads) to create the characteristic spacious breakdown sound. This is the most perceptually significant missing element for the Breakdown-to-Drop arc.

**High-pass filtering.** All melodic voices should be high-passed to avoid competing with the kick and bass in the sub-bass region. The current first-order IIR acts as a low-pass filter (for tonal shaping), not as a high-pass. No explicit high-pass is applied to any voice except through the cutoff structure of the LPF.

---

## 4. Audio Analysis Tools for Style Matching

The `tools/analyse_audio.py` script covers MIDI-domain analysis (note counts, harmony check, voice density, interval distribution). The librosa-based features below cover the audio domain and diagnose issues that MIDI analysis cannot reach: actual spectral brightness, LFO activity, and the acoustic signature of the supersaw synthesis.

### 4.1 The 7 Priority Features

| Priority | Feature | What it catches |
|---|---|---|
| 1 | BPM | Wrong tempo ruins everything |
| 2 | Onset flux periodicity | Detects four-on-the-floor vs random onsets |
| 3 | Spectral centroid trajectory | Filter LFO sweep; supersaw brightness |
| 4 | Crest factor | Sidechain pumping quality |
| 5 | MFCC statistics | Timbre fingerprint: supersaw vs sine |
| 6 | Band energy ratios | Sub/bass balance; mix spectral character |
| 7 | Chroma entropy | Minor-key content; harmonic variety |

### 4.2 BPM

```python
import librosa
import scipy.stats

y, sr = librosa.load('render.wav', sr=22050)
y_p = librosa.effects.percussive(y, margin=3)

# Supply prior so tracker is not confused by 70 BPM half-time
prior = scipy.stats.uniform(130, 20)  # uniform over 130-150
tempo, beat_frames = librosa.beat.beat_track(
    y=y_p, sr=sr, hop_length=512, prior=prior
)
print(f"Estimated BPM: {float(tempo):.1f}")
```

**Target:** 139–141 (allow ±1% from beat tracker noise around the 140 BPM default). If the tracker returns 70, the four-on-the-floor kick is firing at half the expected rate (Build-up half-time mode accidentally active during Groove).

### 4.3 Onset Flux Periodicity (Four-on-the-Floor Test)

```python
hop_length = 512
onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop_length)

ac = librosa.autocorrelate(onset_env, max_size=sr // hop_length * 4)
ac = ac / (ac[0] + 1e-9)

beat_period_s = 60.0 / 140.0           # 0.4286 s at 140 BPM
beat_period_frames = int(beat_period_s * sr / hop_length)  # ~37 frames

beat_strength = float(ac[beat_period_frames])
print(f"Beat-period autocorrelation: {beat_strength:.3f}")
# Target in Groove/Drop: > 0.5
# Target in Breakdown: will drop toward 0.0 (kick is muted — correct)
```

**Target:** above 0.5 in Groove and Drop phases. A flat autocorrelation during Groove means the kick is not synthesising. A strong peak at `beat_period_frames / 2` means kick is doubling at 280 BPM.

### 4.4 Spectral Centroid Trajectory (Filter LFO Test)

```python
centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=512)[0]

import numpy as np
print(f"Centroid: mean={centroid.mean():.0f} Hz  std={centroid.std():.0f} Hz")

# LFO verification: check for peak near 0.15 Hz in centroid FFT
frames_per_sec = sr // 512
c_chunked = [centroid[i:i+frames_per_sec].mean()
             for i in range(0, len(centroid) - frames_per_sec, frames_per_sec)]
lfo_spectrum = np.abs(np.fft.rfft(c_chunked - np.mean(c_chunked)))
lfo_freqs = np.fft.rfftfreq(len(c_chunked), d=1.0)
peak_lfo = lfo_freqs[np.argmax(lfo_spectrum)]
print(f"Dominant LFO rate: {peak_lfo:.3f} Hz  (target: 0.05–0.20 Hz)")
```

**Target values:**

| Statistic | Target | Failure signal |
|---|---|---|
| Mean centroid | 1800–3500 Hz | < 800 Hz = too dull; > 5000 Hz = harsh |
| Std deviation | > 300 Hz | < 100 Hz = LFO not modulating |
| LFO rate | 0.05–0.20 Hz | 0.0 Hz = filter not moving |

With the current `LEAD_CUTOFF_BASE = 12000 Hz`, the first-order IIR coefficient `a ≈ 0.945` at 44100 Hz sample rate. This passes nearly everything; the filter barely moves. The centroid will track whatever the raw supersaw content is (~2000–4000 Hz for a detuned sawtooth), but the LFO will be invisible in the centroid trajectory. **This confirms the filter cutoff is set too high to have audible effect.**

### 4.5 Crest Factor (Sidechain Pumping)

The `analyse_audio.py` tool already computes this. Target: 3–8.

```
Crest factor = peak / RMS per second.
```

- Crest < 2: heavily compressed or clipping — `tanh` soft-clip in `mix_and_limit` is overdriving
- Crest > 12: very sparse — only kick transient carries energy
- Sidechain signature: crest should oscillate with beat period (kick fires, sidechain dips, recovers)

```python
import wave, math

def crest_factors(wav_path):
    with wave.open(wav_path, 'rb') as wf:
        sr = wf.getframerate()
        raw = wf.readframes(wf.getnframes())
    pcm = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    mono = pcm.reshape(-1, 2).mean(axis=1) if pcm.ndim > 1 else pcm
    crests = []
    for i in range(int(len(mono) / sr)):
        seg = mono[i*sr:(i+1)*sr]
        rms = math.sqrt(float((seg**2).mean()) + 1e-12)
        crests.append(float(abs(seg).max()) / rms)
    return crests
```

### 4.6 Chroma Entropy (Harmonic Motion)

```python
y_h = librosa.effects.harmonic(y, margin=8)
chroma = librosa.feature.chroma_cens(y=y_h, sr=sr, hop_length=512)

chroma_mean = chroma.mean(axis=1)
chroma_mean /= chroma_mean.sum() + 1e-9

entropy = -float(np.sum(chroma_mean * np.log2(chroma_mean + 1e-9)))
print(f"Chroma entropy: {entropy:.2f} (max: {math.log2(12):.2f})")
```

**Targets:**

| Value | Meaning |
|---|---|
| < 1.5 | Melody stuck on one or two notes |
| 1.5–2.5 | Normal trance: minor scale with 5–7 active pitch classes |
| 2.5–3.2 | Healthy variation across the full scale |
| > 3.4 | Chromatic noise or out-of-scale notes |

With `LEAD_LOW = 62` (D4) and `LEAD_HIGH = 74` (D5), the lead can access only 2–3 distinct chord tones per chord, likely producing chroma entropy near 1.5 — flagged as "stuck".

### 4.7 Band Energy Ratios

```python
S = np.abs(librosa.stft(y, n_fft=2048, hop_length=512))
freqs = librosa.fft_frequencies(sr=sr, n_fft=2048)

BANDS = {'sub': (0, 80), 'bass': (80, 300), 'mid': (300, 2000), 'himid': (2000, 8000)}

band_rms = {}
for name, (lo, hi) in BANDS.items():
    mask = (freqs >= lo) & (freqs < hi)
    band_rms[name] = float(np.sqrt((S[mask]**2).mean()))

peak = max(band_rms.values()) or 1e-9
for name, v in band_rms.items():
    db = 20 * math.log10(v / peak + 1e-9)
    print(f"  {name:6s}: {db:+.1f} dB")
```

**Targets:**

| Band | Target dB (relative to loudest band) | Failure |
|---|---|---|
| Sub (< 80 Hz) | −10 to −3 dB | < −20 dB = no sub thump |
| Bass (80–300 Hz) | −6 to 0 dB (typically loudest) | < −20 dB = thin mix |
| Mid (300–2000 Hz) | −6 to −3 dB | > 0 dB = mid-forward |
| Hi-mid (2–8 kHz) | −12 to −6 dB | > −3 dB = harsh aliasing |

### 4.8 Measuring "Closeness to Switch Angel"

The single most diagnostic combination: **centroid mean 2000–2800 Hz + centroid std > 400 Hz + chroma entropy 2.0–2.6**. This combination identifies: bright supersaw, active filter LFO, and minor-key melodic motion with harmonic variety — the three perceptually dominant features of uplifting trance.

To compare two renders:
```python
from scipy.spatial.distance import cosine

def mfcc_vector(path):
    y, sr = librosa.load(path, sr=22050)
    return librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13).mean(axis=1)

v1 = mfcc_vector('render_v1.wav')
v2 = mfcc_vector('render_v2.wav')
print(f"MFCC cosine similarity: {1 - cosine(v1, v2):.4f}")
# > 0.98 = same timbre; 0.90–0.98 = noticeable change; < 0.90 = major change
```

If you have a WAV export of Switch Angel's actual Strudel output, computing this similarity gives an objective "closeness" score.

---

## 5. Reverb and Mixing: Implementation Guide

### 5.1 Freeverb for Real-Time Python Synthesis

Freeverb is the standard open-source reverb algorithm (Will Pirkle / Michael Dahl). It is computationally efficient and produces high-quality results. Architecture: 8 parallel lowpass-feedback comb filters (LBCF) → 4 series allpass diffusers → stereo output mixing matrix.

**Tuning constants at 44100 Hz** (scale by `sr / 44100` for other rates):

| | Left delay (samples) | Right delay (L + 23) |
|---|---|---|
| Comb 1 | 1116 | 1139 |
| Comb 2 | 1188 | 1211 |
| Comb 3 | 1277 | 1300 |
| Comb 4 | 1356 | 1379 |
| Comb 5 | 1422 | 1445 |
| Comb 6 | 1491 | 1514 |
| Comb 7 | 1557 | 1580 |
| Comb 8 | 1617 | 1640 |
| Allpass 1 | 556 | 579 |
| Allpass 2 | 441 | 464 |
| Allpass 3 | 341 | 364 |
| Allpass 4 | 225 | 248 |

**Key constants:**
```
fixedgain  = 0.015   (input scaling)
allpass g  = 0.5     (fixed for all 4 allpass sections)
initialroom = 0.5  → feedback f = 0.5 × 0.28 + 0.7 = 0.84
initialdamp = 0.5  → damping d = 0.5 × 0.4 = 0.20
```

**LBCF Python implementation:**
```python
class LBCF:
    def __init__(self, delay_samples, feedback=0.84, damp=0.20):
        self.buf = np.zeros(delay_samples)
        self.pos = 0
        self.feedback = feedback
        self.damp = damp
        self.filterstore = 0.0

    def process_sample(self, x):
        output = self.buf[self.pos]
        self.filterstore = (output * (1.0 - self.damp)
                            + self.filterstore * self.damp)
        self.buf[self.pos] = x + self.filterstore * self.feedback
        self.pos = (self.pos + 1) % len(self.buf)
        return output
```

**Trance reverb settings:**

| Voice | Room size | Damp | Wet mix | Pre-delay | High-cut on return |
|---|---|---|---|---|---|
| Lead (Groove) | 0.70 | 0.30 | 0.20 | 25 ms | 600 Hz |
| Lead (Breakdown) | 0.85 | 0.20 | 0.35 | 30 ms | 400 Hz |
| Pad (Groove) | 0.75 | 0.25 | 0.25 | 20 ms | 500 Hz |
| Pad (Breakdown) | 0.90 | 0.15 | 0.40 | 15 ms | 400 Hz |

Pre-delay (20–30 ms) separates the dry signal from the reverb onset, preventing muddiness. The high-cut on the reverb return keeps reverb tails dark and behind the dry signal — reverb at 8 kHz sounds harsh in trance.

For a minimal implementation without full Freeverb, a simple feedback delay network (FDN) with 4 channels works well:
```python
# Minimal 4-channel FDN reverb
REVERB_DELAYS = [1847, 1699, 2053, 2251]  # prime-number delays (samples)
REVERB_FEEDBACK = 0.82

class SimpleFDN:
    def __init__(self):
        self.bufs = [np.zeros(d) for d in REVERB_DELAYS]
        self.pos = [0] * 4

    def process(self, x, wet=0.25):
        outputs = [self.bufs[i][self.pos[i]] for i in range(4)]
        mixed = sum(outputs) * 0.5  # Hadamard-style mixing
        for i in range(4):
            self.bufs[i][self.pos[i]] = x * 0.015 + mixed * REVERB_FEEDBACK
            self.pos[i] = (self.pos[i] + 1) % REVERB_DELAYS[i]
        return x * (1 - wet) + mixed * wet
```

### 5.2 Gain Staging Targets

**Per-channel RMS targets (pre-fader):**

| Layer | Peak target | RMS target |
|---|---|---|
| Kick | −6 to −3 dBFS | −12 to −9 dBFS |
| Bass | −12 to −6 dBFS | −18 to −14 dBFS |
| Supersaw pad | −18 to −12 dBFS | −24 to −18 dBFS |
| Lead synth | −12 to −9 dBFS | −18 to −12 dBFS |
| Reverb return | −24 to −20 dBFS | (wet-only return) |

**Mix bus (pre-limiter):** peaks −6 to −3 dBFS, RMS −12 to −9 dBFS.

The current normalisation utility:
```python
def normalize_rms(signal, target_rms_db=-18.0):
    current_rms = np.sqrt(np.mean(signal**2))
    if current_rms < 1e-10:
        return signal
    target_linear = 10 ** (target_rms_db / 20.0)
    return signal * (target_linear / current_rms)
```

### 5.3 Sidechain Compression Parameters

**Tempo-synced release:**
```python
def sidechain_release_ms(bpm, fraction=0.5):
    """At 140 BPM: beat=429ms, release≈214ms (recovers before next kick)."""
    beat_ms = 60000.0 / bpm
    return beat_ms * fraction
```

At 140 BPM: beat = 429 ms, release = 214 ms. With `SIDECHAIN_RELEASE = 12` steps at 140 BPM: 12 × 107 ms = 1284 ms — about 3× a beat. The bass/pad recover to full level well before the next kick hit, which means the pump is present but may not feel as tight as professional trance production. A value of 8 steps (855 ms ≈ 2 beats) or even 6 steps (642 ms ≈ 1.5 beats) would give a tighter pump.

**Per-voice parameters:**

| Parameter | Pad | Bass |
|---|---|---|
| Duck depth (`SIDECHAIN_DEPTH`) | 0.05–0.15 gain | 0.15–0.30 gain |
| Recovery (`SIDECHAIN_RELEASE`) | 6–8 steps | 4–6 steps |

Current settings (`SIDECHAIN_DEPTH = 0.05`, `SIDECHAIN_RELEASE = 12`) apply the same extreme depth and slow recovery to both bass and pad. Bass and pad could use different depths: deeper for pads (more dramatic pump), shallower for bass (retain some bass body under the kick).

### 5.4 Frequency Separation

**Critical separations:**

| Rule | Frequency | Action |
|---|---|---|
| Kick sub occupies | < 80 Hz | All other voices HP'd above 80 Hz |
| Bass fundamental | 60–120 Hz | HP bass above 40 Hz; cut sub-sub |
| Pad low-end | − | HP pad above 200–300 Hz |
| Lead clears bass | − | HP lead above 250–500 Hz |
| Reverb return on pad | − | HP reverb return above 200 Hz |
| Reverb return on lead | − | HP reverb return above 500 Hz |

In `trance_stream.py`, the only explicit frequency control is the IIR LPF applied to the lead, bass, and pad. There are no explicit high-pass filters. Adding a first-order high-pass to each voice would prevent low-frequency accumulation:

```python
def apply_highpass_step(sample, state, cutoff_hz, sr=44100):
    """One-pole IIR high-pass (per sample)."""
    a = (2 * math.pi * cutoff_hz) / (2 * math.pi * cutoff_hz + sr)
    new_state = a * (state + sample - state)  # simplification
    return new_state, new_state

# For lead (HP at 250 Hz), pad (HP at 200 Hz), bass (HP at 50 Hz)
```

**Scipy Butterworth for offline processing or analysis:**
```python
from scipy.signal import butter, sosfilt

def highpass(signal, cutoff_hz, sr, order=4):
    sos = butter(order, cutoff_hz / (sr / 2), btype='high', output='sos')
    return sosfilt(sos, signal)
```

---

## 6. Switch Angel Specific Analysis

### 6.1 What We Know from Her Strudel Source

The reference is Switch Angel's `prebake.strudel` (github.com/switchangel/strudel-scripts) and her "Coding Trance Music from Scratch" video. Key Strudel constructs translated to the Python implementation:

| Strudel construct | Python equivalent | Notes |
|---|---|---|
| `s("supersaw").detune(0.2).unison(7)` | `render_supersaw_step` with `SAW_COUNT_LEAD=7`, `DETUNE_CENTS_LEAD` | `.detune(0.2)` in Strudel is normalized 0–1; ≈20 cents per voice = 140 cents total for 7 voices. Current 50 cents total is much narrower. |
| `.mask("...")` patterns | `PHASE_TARGET_GAINS` + gain ramps | Strudel uses text patterns; Python uses state machine |
| `tgate(seed)` | `tgate_pattern(seed)` + `apply_tgate` | LFSR-based pattern from curated seed table |
| `.delay(0.4)` | `_DELAY_FEEDBACK`, `_DELAY_MIX`, `_delay_samples = beat × 0.4` | 40% delay mix with 35% feedback |
| `.add("7,-7")` on lead orbit | Three-voice lead stack: base + 7 + (-7) | Stacks a fifth above and below |
| `.add("-14,-21")` on pad orbit | `chord_wide_voicing` → `[mid-3, mid, mid+7]` | Strudel adds 14 and 21 semitones below (two bass octaves). Python uses a different voicing to avoid bass clash |
| `.clip(.7)` on gated voices | Cosine fade-out at 70% of step | Current implementation: sustain to 70% then cosine fade |

**The `.detune(0.2)` discrepancy:** In Strudel's supersaw, `detune(0.2)` sets the detuning spread as a fraction of an octave: 0.2 × 1200 cents = 240 cents across 7 oscillators. At 140 cents total spread across 7 oscillators, each adjacent oscillator pair is separated by ~23 cents. `trance_stream.py`'s `DETUNE_CENTS_LEAD = 50.0` means 50 cents total across 7 oscillators, or ~8 cents per adjacent pair. This is actually narrower than Switch Angel's supersaw, not wider. The perceptual effect is that the current supersaw is less lush/wide than the reference. This is one of the key tuning mismatches.

### 6.2 How Her Vocabulary Maps to General Trance Vocabulary

| Switch Angel term | General trance term | Current generator status |
|---|---|---|
| supersaw + detune | Supersaw oscillator bank | Implemented; detune value may be narrower than reference |
| tgate | Trance gate | Implemented; LFSR generates patterns from curated seeds |
| .mask() | Arrangement phase muting | Implemented via gain scalars and state machine |
| trancearp | Arpeggiator | Implemented; register is inverted (below lead) |
| breakdown kick mute | Breakdown structure | Implemented; kick gain = 0 in Breakdown |
| sidechain pump | Sidechain compression | Implemented; depth and release tunable |
| filter LFO | Filter LFO | Implemented; but cutoff base is too high for audible effect |
| noise riser | Build-up riser | Implemented; may be too quiet at 0.04 scale |
| reverb on breakdown | Reverb | NOT IMPLEMENTED |

### 6.3 Current Generator vs Target Sound

**What is working correctly:**

1. Four-on-the-floor kick at correct tempo with sidechain triggering
2. Arrangement state machine cycles through phases correctly
3. Trance gate with cosine fade-out modelling Switch Angel's `.clip(.7)`
4. Three-voice lead stack matching her `.add("7,-7")`
5. Feedback delay on the lead
6. Bass downbeat rule (always fires on step 0)
7. Chord progression structure with per-mood harmonic character
8. CA-gated non-repeating patterns from Rule 30

**What needs fixing (see Section 7 for specifics):**

1. **Lead register too narrow.** D4–D5 (12 semitones) vs target C4–C6 (24 semitones). With one note per bar, this means the lead bounces between the same 2–3 notes indefinitely. Chroma entropy will be near 1.5 (stuck).

2. **Arp register inverted.** C3–D4 (48–62) sits BELOW the lead (62–74). Trance arps should soar ABOVE the lead, covering C4–C7 (60–96) or higher. The current setup makes the arp sound like a bass counter-melody rather than the bright, sweeping element characteristic of Switch Angel's arrangements.

3. **Lead filter cutoff too high.** `LEAD_CUTOFF_BASE = 12000 Hz` with IIR coefficient `a ≈ 0.945`. The filter passes ~95% of the signal at every frequency. No audible filter movement even with the LFO active. Target: 2000 Hz base with ±1500 Hz sweep (spec values), or even 4000 Hz base with ±2000 Hz sweep for a brighter-but-moving sound.

4. **No reverb.** The Breakdown phase sounds bare without reverb. This is perceptually the most significant missing element. The breakdown-to-drop arc relies on the contrast between the spacious, reverberant breakdown and the dry, punchy drop. Without reverb, the breakdown and the groove sound almost identical in spatial character.

5. **DETUNE_CENTS_LEAD may be narrower than reference.** 50 cents total across 7 oscillators corresponds to ~8 cents per adjacent pair. Switch Angel's `.detune(0.2)` implies ~240 cents total — about 5× wider. Increasing to 150–200 cents total would produce the characteristic wide, chorusing supersaw sound. (But note: very wide detune at low registers can sound out-of-tune; test by ear.)

6. **Pad filter cutoff too high.** `PAD_CUTOFF_BASE = 1200 Hz` vs spec's 600 Hz. The pad should be warmly filtered; at 1200 Hz it sounds brighter than a typical trance pad.

7. **SIDECHAIN_RELEASE = 12 steps is long.** At 140 BPM, 12 steps = 1.28 seconds — three full beats. The pump recovery should complete within one beat (8 steps ≈ 855 ms, ideally 6 steps = 643 ms). The current long release means the sidechain dip is very gradual; the pump effect is present but not pronounced.

---

## 7. Actionable Next Steps

Ordered by expected perceptual impact. Each item includes the specific code change and the metric it will move.

---

### Item 1: Expand lead register to C4–C6

**Why:** Lead range of D4–D5 (12 semitones) limits melodic motion to 2–3 chord tones per chord. Expanding to C4–C6 doubles the range, allows genuine melodic arcs, and fixes chroma entropy.

**Change:** In `trance_stream.py` constants section:
```python
# Before:
LEAD_LOW: int = 62    # D4
LEAD_HIGH: int = 74   # D5

# After:
LEAD_LOW: int = 60    # C4
LEAD_HIGH: int = 84   # C6
```

**Metrics that will improve:** chroma entropy (1.5 → 2.0–2.6), % unique notes per measure, melodic contour variety.

**Expected impact:** Very high. This is the most structurally limiting bug in the current implementation.

---

### Item 2: Move arp register above the lead

**Why:** The arp at C3–D4 (48–62) sits below the lead at D4–D5 (62–74). Trance arps are the bright, high, sweeping element. Placing it below the lead inverts the harmonic hierarchy.

**Change:** After fixing the lead register (Item 1):
```python
# Before:
ARP_LOW: int = 48     # C3  — arp lives below the lead
ARP_HIGH: int = 62    # D4

# After:
ARP_LOW: int = 72     # C5  — arp soars above the lead
ARP_HIGH: int = 96    # C7
```

**Metrics that will improve:** spectral centroid mean (the high arp adds brightness), perceptual separation between arp and bass voices.

**Expected impact:** High. Changes the entire timbral character of the mix.

---

### Item 3: Fix lead filter cutoff

**Why:** `LEAD_CUTOFF_BASE = 12000 Hz` means the LPF has virtually no effect. The filter LFO produces no audible movement. This removes the defining "breathing" quality of trance leads.

**Change:**
```python
# Before:
LEAD_CUTOFF_BASE: float = 12000.0
LEAD_CUTOFF_SWEEP: float = 4000.0

# After:
LEAD_CUTOFF_BASE: float = 3500.0    # sits in the bright-but-controlled range
LEAD_CUTOFF_SWEEP: float = 2000.0   # sweeps from 1500 to 5500 Hz
```

**Metric verification:** centroid mean should shift to 2000–3500 Hz; centroid std should exceed 300 Hz; LFO rate peak in centroid FFT should appear near 0.15 Hz.

**Expected impact:** Very high. The filter LFO is one of the three most characteristic elements of Switch Angel's sound (per the audio analysis guide).

---

### Item 4: Fix pad filter cutoff

**Why:** `PAD_CUTOFF_BASE = 1200 Hz` produces a brighter pad than the warm, muffled texture typical of trance. The pad should sit behind the lead in the mix.

**Change:**
```python
# Before:
PAD_CUTOFF_BASE: float = 1200.0
PAD_CUTOFF_SWEEP: float = 600.0

# After:
PAD_CUTOFF_BASE: float = 600.0
PAD_CUTOFF_SWEEP: float = 300.0
```

**Expected impact:** Medium. Improves mix balance; pad will feel warmer and less competitive with the lead.

---

### Item 5: Tighten sidechain release

**Why:** 12 steps (1.28 seconds) is three beats — the pump recovery is so slow it barely registers as pumping. Trance sidechain should recover within one beat.

**Change:**
```python
# Before:
SIDECHAIN_RELEASE: int = 12    # recover over ~0.75 beats

# After:
SIDECHAIN_RELEASE: int = 7     # recover within ~0.5 beats at 140 BPM
```

At 140 BPM with 16th-note steps: 7 steps = 7 × 107 ms = 749 ms ≈ 1.75 beats. Tighter than before; pump will be audible. For a more pronounced pump, try 4–5 steps (428–535 ms ≈ 1–1.25 beats).

**Metric verification:** per-second crest factor should oscillate with beat period; crest mean should remain in 3–8 range.

**Expected impact:** Medium-high. Pump is perceptually fundamental to trance.

---

### Item 6: Add reverb for Breakdown phase

**Why:** The Breakdown is the emotional core of trance. Without reverb, the breakdown and groove have the same spatial character; the breakdown does not feel spacious or "open". This eliminates the contrast that makes the Drop land with impact.

**Implementation approach** (minimal addition to the main loop):

1. Add a simple `SimpleFDN` instance (from Section 5.1) for the lead and pad voices.
2. Modify the render pipeline in the Breakdown phase to send more signal to the reverb:

```python
# In the main loop, after rendering lead and pad buffers:
if state.phase in ("Breakdown",):
    reverb_wet = 0.35
    lead_l = lead_reverb.process(lead_l, wet=reverb_wet)
    lead_r = lead_reverb.process(lead_r, wet=reverb_wet)
    pad_l = pad_reverb.process(pad_l, wet=reverb_wet)
    pad_r = pad_reverb.process(pad_r, wet=reverb_wet)
elif state.phase in ("Groove", "Drop"):
    # Light reverb on lead only
    lead_l = lead_reverb.process(lead_l, wet=0.15)
    lead_r = lead_reverb.process(lead_r, wet=0.15)
```

**Expected impact:** Very high. Adds the most perceptually significant missing element. The Breakdown-to-Drop arc requires this spatial contrast.

---

### Item 7: Increase lead detune toward Switch Angel reference

**Why:** `DETUNE_CENTS_LEAD = 50.0` is approximately 8 cents per adjacent oscillator pair. Switch Angel's `.detune(0.2)` in Strudel corresponds to roughly 5× wider. The characteristic "chorus-width" of supersaw leads requires at least 15–25 cents per oscillator pair.

**Change:**
```python
# Before:
DETUNE_CENTS_LEAD: float = 50.0

# After (start here, tune by ear):
DETUNE_CENTS_LEAD: float = 120.0   # ~20 cents per pair for 7 oscillators
```

**Note:** At very wide detune (> 200 cents total), the oscillators can sound genuinely out of tune in higher registers. Test specifically in the lead register C4–C6 after Item 1 is applied.

**Metric verification:** MFCC cosine similarity between renders with different detune values; wider detune should produce a more distinctive MFCC-1 signature (more negative, confirming brighter harmonic content).

**Expected impact:** Medium. Affects timbre richness; most noticeable when the track plays in isolation rather than in a mix context.

---

### Item 8: Add snare roll in Build-up

**Why:** The Build-up phase currently has only a half-time kick and the noise riser. Real trance build-ups use an accelerating snare or clap roll to build tension. Without it, the Build-up feels flat.

**Implementation:** Add a clap/snare synthesiser (band-passed noise burst, 50–200 ms decay) that fires on:
- Steps 4 and 12 (quarter-note backbeat) for the first 4 bars of Build-up
- All 8th-note positions (steps 2, 4, 6, 8, 10, 12, 14) for bars 5–12
- All 16th-note positions (steps 0–15) for bars 13–16

This is a new voice requiring a new accumulator list but uses the same `ArpNote` / `_render_arp_accumulator` pattern already in the code.

**Expected impact:** Medium. Adds an important genre-specific structural element.

---

### Item 9: Add Build-up silence beat before Drop

**Why:** Trance builds up to a single beat of complete silence before the Drop re-entry. This one-beat gap maximises the perceived impact. Without it, the Drop feels like a continuation rather than an event.

**Implementation:** In the arrangement state machine, detect the final 4 steps of the Build-up phase (`phase_bar == PHASE_BARS - 1` and `step_in_bar >= 12`) and set all voice gains to 0.0, bypassing the transition ramp.

**Expected impact:** Medium. Perceptually small (one beat = 429 ms) but disproportionately important for the Drop impact.

---

### Quick Reference: What to Run to Verify Each Change

```bash
# Render 32 bars with uplifting mood
python /Users/johannes/switch-angel/trance-stream/trance_stream.py \
    --bars 32 --wav /tmp/trance_out.wav -o /tmp/trance_out.mid \
    -s center --mood uplifting

# MIDI domain analysis
python /Users/johannes/switch-angel/trance-stream/tools/analyse_audio.py \
    /tmp/trance_out.wav /tmp/trance_out.mid --seed center --mood uplifting

# Audio domain analysis (run the librosa script from Section 4)
python -c "
import librosa, numpy as np, math, scipy.stats
y, sr = librosa.load('/tmp/trance_out.wav', sr=22050)
y_p = librosa.effects.percussive(y, margin=3)
prior = scipy.stats.uniform(130, 20)
tempo, _ = librosa.beat.beat_track(y=y_p, sr=sr, hop_length=512, prior=prior)
centroid = librosa.feature.spectral_centroid(y=y, sr=sr, hop_length=512)[0]
y_h = librosa.effects.harmonic(y, margin=8)
chroma = librosa.feature.chroma_cens(y=y_h, sr=sr, hop_length=512)
cm = chroma.mean(axis=1); cm /= cm.sum() + 1e-9
entropy = -float(np.sum(cm * np.log2(cm + 1e-9)))
print(f'BPM: {float(tempo):.1f}  (target: 139-141)')
print(f'Centroid mean: {centroid.mean():.0f} Hz  (target: 1800-3500)')
print(f'Centroid std: {centroid.std():.0f} Hz  (target: >300)')
print(f'Chroma entropy: {entropy:.2f}  (target: 1.5-3.2)')
"
```

**Pass/fail targets for the full implementation:**

| Metric | Current (estimated) | Target after fixes |
|---|---|---|
| BPM | 140 (correct) | 139–141 |
| Beat autocorr (Groove) | > 0.5 (correct) | > 0.5 |
| Centroid mean | ~3000 Hz (raw saw, unfiltered) | 2000–3000 Hz (filtered) |
| Centroid std | < 100 Hz (LFO invisible) | > 400 Hz |
| Chroma entropy | ~1.5 (stuck, narrow range) | 2.0–2.6 |
| Bass band dB | TBD | −10 to 0 dB |
| MFCC cosine similarity to reference | Baseline unknown | > 0.90 vs Switch Angel WAV |
| Crest factor mean | TBD | 3–8 |
