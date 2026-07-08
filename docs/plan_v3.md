# Plan: v3 — Full Architecture Rebuild with Music Theory

## Why everything so far has failed

v1 and v2 failed at two levels simultaneously:

**Level 1 — Technical**: Pure-Python synthesis loops cause buffer starvation; level saturation causes clipping; no filters are correctly stateful; drums are non-deterministic. The code cannot produce clean audio even if the musical content is correct.

**Level 2 — Musical**: Even where the synthesis works, the code has no embedded musical knowledge. Constants like `LEAD_HIGH=74`, chord progressions as magic integers, filter arcs as hand-tuned equations — none of these come from an articulated understanding of *why* they should be those values. Switch Angel knows why degree 3→4→5→6 works as a pad progression. She knows why the filter opens at 0.877 creates a euphoric release. She knows why the notearp pattern `< <- - - -> 0 1@2 0 1 0 1>*16` creates forward motion. That knowledge is entirely absent from the codebase.

**The result**: When something sounds wrong, there is no basis for knowing *what* specifically is wrong or *why*. This is why "listen and adjust" has failed — you need musical knowledge to know what you're listening for.

**The fix**: Research spikes that build documented musical knowledge first, then architecture that embeds that knowledge as code, then DSP that implements it correctly, then tests at every layer.

---

## First Principle: There is no excuse for audio blindness

**"I cannot listen to audio like a human" is never an acceptable response in this project.**

Music is mathematics. Sound is physics. Every perceptual quality a human listener evaluates has a precise, measurable, well-researched mathematical correlate. The literature on music information retrieval, psychoacoustics, and signal processing is vast and covers all of it. If something needs to be heard to be evaluated, the correct response is: find the measurement, implement the tool, run the analysis.

### The perceptual→measurable mapping

| What a human hears | What to measure | How |
|---|---|---|
| "This sounds like noise, not music" | Crest factor < 3; spectral flux too high; no tonal peaks in FFT | `analyse_audio.py::analyse_wav()` |
| "The filter isn't opening" | Spectral centroid not increasing over time; brightness_score static | `spectrogram.py::analyse_spectrum()` on 8-bar segments, assert centroid rises |
| "The kick doesn't punch through" | Kick transient masked; crest factor of kick stem < 4; sidechain depth too low | Stem-separate, measure kick stem crest factor independently |
| "The pad sounds wrong / doesn't breathe" | RMS variation per 16th step < 2× (trancegate not working); wrong frequency range for lpenv | `test_pad_trancegate_creates_variation()` |
| "The melody sounds random / doesn't go anywhere" | Interval sequence has no stepwise motion; phrase boundaries irregular; no climax note | `midi_to_analysis()` interval histogram: assert >50% stepwise (±1–2 semitones) |
| "It doesn't sound like trance" | Spectral centroid outside 800–2500 Hz; brightness outside SA's 30–45% reference; kick density < 3.5 hits/bar | Full suite in `test_song.py` |
| "The bass is too loud / too quiet" | Band energy ratio bass/mid outside 0.25–4× SA reference | `test_spectral_match_sa_reference()` |
| "The FM sounds wrong" | Hi-mid band energy not increasing after bar 96; FM arc not applied | `test_lead_fm_broadens_spectrum()` |
| "The kick pattern doesn't pump" | 16th-note onset positions don't match KICK_STEPS_SYNCOPATED; rhythm_similarity < 0.6 | `compare_midi()` against `drums.mid` reference |
| "The two instruments clash harmonically" | >5% out-of-scale notes; interval histogram dominated by tritones/minor-2nds | `analyse_midi()` scale adherence check |
| "Something sounds distorted / clipping" | Peak > 0.99; crest factor < 2 | `analyse_wav()` peak and crest checks |
| "The mix sounds thin / no low end" | Bass band energy below threshold; pad voicing offsets not generating sub-bass content | Per-stem spectrogram comparison |
| "The delay is too washy / too dry" | Delay wet outside 0.5–0.8 range or spectral tail energy ratio wrong | Render with/without delay, compare spectral decay |

### The corollary: every new perceptual concern gets a measurement

If during implementation something sounds wrong in a way not yet covered, the procedure is:
1. Identify the specific perceptual property (e.g. "the hihat sounds too clicky")
2. Find the mathematical correlate (e.g. attack time too short → transient sharpness → high spectral flux at onset)
3. Write a measurement function if one doesn't exist
4. Write a test with a threshold derived from the SA reference audio
5. Commit the analysis tool and the test

**No concern gets closed with "it sounds wrong but I can't measure why."** That is the same failure mode as v1 and v2 — making changes without knowing what effect they have.

### Tools available for any new measurement need

- **Onset detection**: `librosa.onset.onset_detect()` — finds note/hit boundaries
- **Spectral flux**: `librosa.feature.spectral_flux()` — rate of spectral change (high = noisy, low = tonal)
- **Autocorrelation / tempo**: `librosa.beat.tempo()` — confirms BPM is correct
- **Chroma features**: `librosa.feature.chroma_stft()` — which pitch classes dominate (key verification)
- **MFCC distance**: `librosa.feature.mfcc()` + cosine distance — timbre similarity between two instruments
- **Loudness (LUFS)**: `pyloudnorm` — broadcast-standard loudness, matches how streaming platforms measure level
- **Harmonic/percussive separation**: `librosa.effects.hpss()` — split a mix into tonal vs percussive components for isolated analysis
- **Zero-crossing rate**: high ZCR = noise-like; low ZCR = tonal — quick noise detector

These can be added to `tools/analyse_audio.py` as needed. The threshold for "needed" is: any time a test failure or a quality concern cannot be explained by existing measurements.

---

## Architecture: four layers

```
Research & Knowledge
   research/music_theory/       documented trance theory, SA analysis, reference audio targets
   docs/music_theory/           committed knowledge base, reproducible
        ↓
Song Theory Layer               song/theory.py
   Scales, chord progressions, notearp patterns, energy arcs
   — all derived from theory and SA's documented practice —
   — explicit, named, testable —
        ↓
Instrument Layer                instruments/
   Pad, Lead, Kick, HiHat, Clap, Bass, Pulse
   — each instrument encapsulates its signal chain —
   — renderable in isolation —
        ↓
DSP Primitives                  synth/
   oscillators, filters, envelopes, effects
   — numpy-vectorised, scipy filters, no Python loops —
   — unit tested numerically —
```

Each layer is independently testable. The test pyramid goes:
- DSP unit tests: numerical assertions, no audio hardware
- Instrument spectral tests: render 1s, assert FFT properties against reference clips
- Song integration tests: render 8–32 bars, run `analyse_audio.py` + `spectrogram.py`, assert quality thresholds

---

## Phase 0 — Reference audio (prerequisite for all testing)

Extract SA's actual audio from the 5 `.webm` files in `research/videos/`. These are the ground truth.

```bash
# Extract 60 seconds of musical content from each session (skip first 90s of setup talk)
for VIDEO in research/videos/*.webm; do
  ID=$(basename "$VIDEO" | cut -d_ -f1)
  ffmpeg -i "$VIDEO" -vn -acodec pcm_s16le -ar 44100 \
    -ss 90 -t 60 "research/reference_audio/${ID}_90s.wav"
done

# Also download SA's pad samples (public domain, The Unlicense)
for N in 10 11 12 13 14; do
  curl -L "https://raw.githubusercontent.com/switchangel/pad/main/switch_angel_pad${N}.wav" \
    -o "research/reference_audio/pads/pad${N}.wav"
done
```

Run the existing `tools/spectrogram.py` on each extracted clip. Commit spectrograms and write `research/reference_audio/targets.json` with the measured spectral values. These targets are the machine-readable acceptance criteria the synthesiser must match.

Create `tools/extract_reference_audio.py` to automate the above.

---

## Phase 0b — Source separation and MIDI extraction pipeline

This phase creates the deepest analysis tool we have: take SA's actual audio, split it into stems, convert each stem to MIDI, and produce structured multi-track MIDI files we can directly compare against our generated output.

This is called **music information retrieval (MIR)**. The techniques are mature and widely used for exactly this purpose.

### Tools

**Stem separation — Demucs (Meta AI)**
The best open-source neural separator. The `htdemucs_6s` model separates into 6 stems: `drums`, `bass`, `vocals`, `guitar`, `piano`, `other`. For trance (no vocals, no guitar):
- `drums` → kick, hihat, clap as a combined stem
- `bass` → bass line
- `other` → pads + lead + pulse mixed together

```bash
pip install demucs
python -m demucs -n htdemucs_6s research/reference_audio/3fpx7Scysw4_90s.wav \
  -o research/reference_audio/stems/
```

**Audio-to-MIDI — basic-pitch (Spotify)**
Polyphonic pitch detection with onset/offset tracking. Outputs MIDI with one note per detected pitch. Best open-source tool for this; uses a small neural net trained on diverse audio.

```bash
pip install basic-pitch
basic-pitch --output-directory research/reference_audio/midi/ \
  research/reference_audio/stems/htdemucs_6s/3fpx7Scysw4_90s/bass.wav
```

**Multi-track MIDI assembly — mido**
Assembles per-stem MIDI files into a single `.mid` with named tracks:

```python
import mido
mid = mido.MidiFile()
for stem_name, midi_path in stems.items():
    track = mido.MidiFile(midi_path).tracks[0]
    track.name = stem_name
    mid.tracks.append(track)
mid.save('research/reference_audio/midi/3fpx7Scysw4_full.mid')
```

### Create `tools/reverse_engineer.py`

Orchestrates the full pipeline end-to-end:

```
Input:  research/reference_audio/<video_id>_90s.wav
Output:
  research/reference_audio/stems/<video_id>/
    drums.wav      — kick + hihat + clap combined
    bass.wav       — bass line
    other.wav      — pad + lead + pulse mixed
  research/reference_audio/midi/<video_id>/
    drums.mid
    bass.mid
    other.mid
  research/reference_audio/midi/<video_id>_full.mid   ← multi-track MIDI
  research/reference_audio/midi/<video_id>_analysis.md ← automated structure analysis
```

Usage:
```bash
python tools/reverse_engineer.py research/reference_audio/3fpx7Scysw4_90s.wav
python tools/reverse_engineer.py --all   # process all 5 reference clips
```

### `tools/stem_separation.py`
```python
def separate_stems(wav_path: str, out_dir: str, model='htdemucs_6s') -> dict[str, str]:
    """Returns {stem_name: wav_path} for each separated stem."""
```

### `tools/audio_to_midi.py`
```python
def audio_to_midi(wav_path: str, out_path: str,
                  onset_threshold=0.5, frame_threshold=0.3,
                  minimum_note_length=58) -> str:
    """Convert audio to MIDI using basic-pitch. Returns path to .mid file."""

def midi_to_analysis(midi_path: str) -> dict:
    """
    Returns:
    - note_histogram: {pitch: count}
    - rhythm_grid: which 16th-note positions have onsets
    - interval_sequence: list of semitone intervals between consecutive notes
    - phrase_lengths: detected phrase boundaries in bars
    """
```

### `tools/midi_compare.py`
Compares our generated MIDI against SA's extracted MIDI:

```python
def compare_midi(generated_path: str, reference_path: str) -> dict:
    """
    Returns:
    - note_overlap_pct: % of generated notes in reference histogram
    - rhythm_similarity: how closely 16th-note hit positions match (0.0–1.0)
    - interval_similarity: cosine similarity of interval distributions
    - key_match: does the generated track use the same pitch classes?
    - warnings: list of specific mismatches
    """
```

### Known limitations (documented in `research/reference_audio/stems/README.md`)

Demucs was designed for acoustic music. In trance:
- `drums` stem is reliable for kick/hihat pattern extraction
- `bass` stem is usable for bass note patterns
- `other` contains all synths mixed; cannot separate pad from lead
- basic-pitch on `other` gives approximate chord/melody shapes, not exact notes
- Use drum rhythm grid as high-confidence reference; confirm note data against OCR'd code

### What this unlocks

1. **Kick pattern verification**: `drums.mid` confirms `KICK_STEPS_SYNCOPATED = [0,4,8,11,14]` against real extracted audio rather than just OCR'd code.
2. **Bass note analysis**: `bass.mid` shows which MIDI notes SA's bass plays — confirms scale degrees.
3. **Per-stem spectral targets**: Run `spectrogram.py` on each stem separately — gives us precise spectral targets for drums, bass, and pad+lead individually.
4. **MIDI comparison in integration tests**: `tests/test_song.py` can call `compare_midi(generated, reference)` and assert `rhythm_similarity > 0.6` — a quantitative musical correctness check.
5. **Instrument isolation for A/B testing**: Load SA's `bass.wav` stem and play it alongside our synthesised bass — direct comparison of character, not just spectral averages.

### Dependencies

**`requirements-dev.txt`** (lightweight, always-needed dev tools):
```
pytest
scipy
mido            # pure-Python MIDI I/O, no native deps
```

**`requirements-ml.txt`** (ML tools, large download, separate so CI can skip):
```
demucs          # installs PyTorch (~2GB on first pip install) + ~1GB model on first run
basic-pitch     # also requires PyTorch; ~50MB model on first run
```

Install both:
```bash
pip install -r requirements-dev.txt
pip install -r requirements-ml.txt   # only needed for Phase 0b pipeline
```

The ML requirements are separate because PyTorch is ~2GB and CI/lightweight environments should not be required to download it just to run DSP unit tests or song integration tests. The stem separation pipeline is run once offline to produce committed MIDI outputs; after that only `requirements-dev.txt` is needed.

---

## Phase 1 — Research spikes (before writing any synthesis code)

Each spike produces a committed markdown document in `docs/music_theory/`. These documents are not READMEs — they are knowledge bases that directly inform `song/theory.py`. The code cites them.

### Spike 1: Trance harmony and energy theory

**Questions to answer:**
- What scales are used in trance and what emotional character does each create? (natural minor = tension/euphoria; dorian = bittersweet/forward; major = pure uplift)
- What are the canonical trance chord progressions and what emotional function do they serve? The "Andalusian cadence" (i-VII-VI-VII, e.g. Am-G-F-G) vs the "euphoric progression" (i-VI-III-VII) vs the "dark progression" (i-iv-i-viidim)
- Why do degrees 3→4→5→6 (SA's confirmed pad progression) work musically? What harmonic motion does this create?
- What makes a chord voicing sound "trance" vs generic? (The add(-14,-21) doublings, specific intervals in the supersaw stack)
- How does tension and release work in trance over a 6-minute session — what creates the "journey" feeling?
- What is the role of the trance gate rhythmically — why does gating a pad at 1.5× the bar rate create groove?

**Output**: `docs/music_theory/01_trance_harmony.md`
```
Sections:
- Scales and their emotional character (with examples in SA's key of G minor)
- Canonical chord progressions with scale-degree notation
- Voicing theory: why -14/-21 doublings work in the mix
- Tension/release mechanics in a 6-minute trance arc
- How the filter arc maps to emotional energy (closed = dark/tense, open = euphoric)
```

### Spike 2: SA's musical vocabulary, codified

**Questions to answer** (from OCR analysis and `switch_angel_song_structure.md`):
- SA's confirmed pad chord progression `<3@3 4 5 @3 6>*2` — what key-relative harmony is this? Strudel uses **0-indexed** scale degrees. In G natural minor: 0=G, 1=A, 2=Bb, 3=C, 4=D, 5=Eb, 6=F. So SA's degrees 3→4→5→6 produce **C→D→Eb→F**. What progression does this imply? What makes it specifically "trance" rather than generic minor?
- SA's confirmed lead note patterns: `"@@2 <-7 [-5 -2]>@3 <0 -3 2 1>@3"` — what melodic motion does this encode? The `@@2` rest creates space, `-7` to `[-5,-2]` is a rising figure, `0 -3 2 1` is a falling figure. What is the overall arc?
- SA's notearp pattern `< <- - - -> 0 1@2 0 1 0 1>*16` — what rhythmic density does this produce? Where are the active notes? What forward motion does the pattern create?
- The `.add "<5 [4] 0 <0 2>>"` voicing shift — why do offsets of 5, 4, 0, 0/2 semitones across bars create musical variety without harmonic dissonance?
- The filter arc values (start 0.4–0.5, dip to 0.3, open to 0.88) mapped to Hz via `(x*12)^4` — what specific frequencies are these cutoff points? What musical effect does opening from 2800 Hz to 9400 Hz have on a supersaw?
- The 11-stage build order timing — why do these specific intervals create a sense of arrival?

**Output**: `docs/music_theory/02_sa_vocabulary_codified.md`
```
Sections:
- Pad chord progression: harmonic analysis in G minor
- Lead melodic patterns: interval analysis and tension/release structure
- Notearp pattern: rhythmic analysis (which 16th positions are active, what accent pattern emerges)
- Voicing shifts: why the .add "<5 [4] 0 <0 2>>" technique works
- Filter arc mapped to Hz: what the listener actually hears at each stage
- Build order timing: why 11 stages at these intervals creates a coherent arc
```

### Spike 3: Trance rhythm theory

**Questions to answer:**
- Why does SA's kick pattern `beat("0,4,8,11,14", 16)` create the trance pump feeling? Steps 0,4,8 = beats 1,2,3; step 11 = "e" of beat 3; step 14 = "+" of beat 4. What is the rhythmic name for this? (The step 11 and 14 kicks are an anticipation pattern — they hit *before* beat 4 and before the bar, creating forward momentum. This is called "pre-beat" or "kick anticipation".)
- What is the rhythmic function of the hihat's `tri.fast(4).range(0.05, 0.12)` decay modulation? (Varying decay at 4x bar rate creates a triplet-feel accent pattern against the 16th-note grid — this is a groove technique)
- What is the clap backbeat `struct("~ 1 ~ 1")` (beats 2 and 4) doing harmonically and rhythmically to the mix?
- Why does the trancegate at 1.5× bar rate create groove rather than chaos? (1.5 cycles/bar = a 3/2 polyrhythm against the 4/4 kick — creates tension that the kick resolves every 2 bars)
- What is the rhythmic role of `.seg 16` on the pad? (Forces re-trigger every 16th note, creating a rhythmic stepped feel vs legato)

**Output**: `docs/music_theory/03_trance_rhythm.md`
```
Sections:
- Kick pattern analysis: why steps 0,4,8,11,14 create the trance pump
- Hihat groove: the tri-LFO decay as an accent generator
- Polyrhythm: the trancegate at 1.5x as a 3/2 relationship to 4/4
- Sidechain psychology: why a kick ducking a pad at 0.7 depth creates energy
- seg 16 vs continuous: why retriggering creates groove
```

### Spike 4: Generative melody in trance

**Questions to answer:**
- What makes a trance melody "work"? Specifically: which intervals are permitted, what range is appropriate, what phrase lengths create recognition vs boredom?
- What is the difference between a melody that sounds "procedurally generated" and one that sounds "composed"? (Primarily: stepwise motion with occasional purposeful leaps, consistent phrase lengths, a climax note per phrase)
- How does SA's lead melody work as a sequence of intervals? Map `"@@2 <-7 [-5 -2]>@3 <0 -3 2 1>@3"` to actual intervals: what is the ascending/descending shape?
- What does the notearp function actually do rhythmically and melodically? (It selects indices from a chord — so "0 1 2" across a [0,7] chord = alternating between chord tone 0 and chord tone 7, creating an arpeggio that tracks harmonic changes automatically)
- How do you generate a melody that feels like it has direction rather than wandering?

**Output**: `docs/music_theory/04_generative_melody.md`
```
Sections:
- Trance melody characteristics (range C4-C6, stepwise with purposeful leaps)
- Phrase structure (4-bar and 8-bar phrases, climax note placement)
- Interval rules (what intervals are permitted consecutively and why)
- How notearp creates apparent melody from chord indices
- Generative rules derived from SA's patterns
```

### How research spikes are executed

Each spike is a focused research session using:
1. The existing `research/analysis/` documents (primary source)
2. The `research/2026-07-08_authentic_strudel_chat.md` (confirmed SA function implementations)
3. The extracted reference audio (spectral evidence)
4. Standard music theory references (not SA-specific)

Spikes produce markdown documents committed to `docs/music_theory/`. These documents contain specific, citable values — not vague descriptions. For example: "SA's pad progression degrees 3→4→5→6 in G minor produces Bb→C→D→Eb, which is a IV→V→VI (relative to Eb major) progression moving from subdominant to dominant to relative major — this creates the characteristic trance 'lifting' feeling."

---

## Phase 2 — Refactor analysis tools to be importable

**`tools/analyse_audio.py`** — extract (keep CLI):
```python
def analyse_wav(wav_path: str) -> dict:     # peak, rms, crest_factor, band_energy
def analyse_midi(midi_path: str, seed: str = 'center') -> dict:  # notes, intervals, density, warnings
def quality_warnings(wav_stats, midi_stats) -> list[str]:
```

**`tools/spectrogram.py`** — extract (keep CLI):
```python
def analyse_spectrum(wav_path: str) -> dict:   # band_energy, mean_centroid_hz, brightness_score
```

---

## Phase 3 — Song theory layer (`trance-stream/song/theory.py`)

This is the critical missing layer. It embeds the knowledge from the research spikes as code. Every value is documented with a `# Source:` comment citing the relevant doc.

```python
# song/theory.py
# All values sourced from docs/music_theory/ — do not change without updating the docs.

# ── Scales ────────────────────────────────────────────────────────────────────
# Source: docs/music_theory/01_trance_harmony.md §1
SCALES = {
    'natural_minor': [0, 2, 3, 5, 7, 8, 10],   # Aeolian — tension, drama, euphoria
    'dorian':        [0, 2, 3, 5, 7, 9, 10],    # Bittersweet, forward-moving
    'major':         [0, 2, 4, 5, 7, 9, 11],    # Pure uplift
}

# ── Chord progressions (scale degrees) ───────────────────────────────────────
# Source: docs/music_theory/01_trance_harmony.md §2
PROGRESSIONS = {
    'uplifting':    [[0], [5], [2], [4]],   # i - VI - III - v  (euphoric arc)
    'dark':         [[0], [3], [0], [6]],   # i - iv - i - viidim (tension)
    'acid':         [[0], [2], [3], [2]],   # i - III - iv - III (hypnotic)
    'progressive':  [[0], [3], [4], [1]],   # I - IV - V - ii (bright, major)
    'sa_canonical': [[3], [4], [5], [6]],   # SA's confirmed pad degrees in GWXCCBsOMSg
    # Strudel 0-indexed degrees in G natural minor: 0=G,1=A,2=Bb,3=C,4=D,5=Eb,6=F
    # So degrees 3→4→5→6 = C→D→Eb→F
    # Harmonic analysis: to be refined in Spike 2 once research doc is written
    # Source: docs/music_theory/02_sa_vocabulary_codified.md §1
}

# ── Pad voicing ───────────────────────────────────────────────────────────────
# Source: docs/music_theory/02_sa_vocabulary_codified.md §1
# SA's exact confirmed voicing: add("-14,-21") = sub-bass doublings
PAD_VOICING_OFFSETS = [0, -14, -21]   # root, one octave below, an octave + a fifth below

# ── Notearp patterns (active 16th-note positions per bar) ────────────────────
# Source: docs/music_theory/02_sa_vocabulary_codified.md §3, §4_generative_melody.md
# SA's confirmed pattern from 3fpx7Scysw4 (128 snapshots, never changed):
# "< <- - - -> 0 1@2 0 1 0 1>*16"
# Active positions: 0, 4, 5, 6, 8, 10, 11, 12, 13, 14 (approx — needs SA source analysis)
# The pattern creates: silence on beats 1-3, activation cluster on beats 3e-4+
# This is a "back-loaded" rhythm — it leads into the next bar, creating forward momentum
SA_NOTEARP_PATTERN = [-1, -1, -1, -1, 0, -1, -1, -1, 0, 1, 1, 0, 1, 0, 1, 0]
# -1 = rest, 0 = root chord tone, 1 = second chord tone

# ── Parameter arcs ────────────────────────────────────────────────────────────
# Source: docs/music_theory/02_sa_vocabulary_codified.md §5
# All arc values are rlpf slider positions (0.0–1.0) → Hz via (x*12)^4
# Confirmed measurement points from GWXCCBsOMSg and 3fpx7Scysw4 OCR data:
FILTER_ARC = {
    'start':      0.45,   # ~3,800 Hz — moderately open
    'mid':        0.60,   # ~6,000 Hz — warming up
    'pullback':   0.35,   # ~1,800 Hz — deliberate dark moment
    'full_open':  0.877,  # ~9,400 Hz — euphoric release
    'lead_base':  0.593,  # ~5,400 Hz — SA's confirmed lead base value
}

# Filter arc timing (bars at 140 BPM, 1 cycle = 1 bar)
FILTER_ARC_TIMING = {
    'start_to_mid_bars':  40,   # gradual open over first 40 bars
    'pullback_duration':   8,   # 8-bar pullback at seed-determined position
    'final_open_bar':     96,   # fully open by bar 96
}

# FM arc: 0 until bar ~96, then ramp to 0.5-0.65
# Source: docs/music_theory/02_sa_vocabulary_codified.md §5
FM_ARC_ONSET_BAR = 96
FM_ARC_TARGET = 0.55

# ── Drum patterns ─────────────────────────────────────────────────────────────
# Source: docs/music_theory/03_trance_rhythm.md §1
# SA's confirmed kick: FOUR-ON-FLOOR (simple, as confirmed from real demo transcript)
KICK_STEPS_BASIC = [0, 4, 8, 12]
# SA's syncopated kick (added mid-session in GWXCCBsOMSg at t=5:20)
KICK_STEPS_SYNCOPATED = [0, 4, 8, 11, 14]
# SA's confirmed clap: syncopated on same positions, or backbeat struct("~ 1 ~ 1")
CLAP_STEPS_SYNCOPATED = [0, 4, 8, 11, 14]  # from GWXCCBsOMSg t=4:31
CLAP_STEPS_BACKBEAT = [4, 12]               # from 3fpx7Scysw4

# ── Build order (bars) ────────────────────────────────────────────────────────
# Source: docs/music_theory/02_sa_vocabulary_codified.md §6
# Derived from GWXCCBsOMSg timing (clearest documented session)
# Converted from cycles at 140 BPM (35 cycles/min):
STAGE_BARS_DEFAULT = {
    'kick_on':         0,    # kick first, always
    'pad_root_on':     2,    # pad enters as single root note
    'lead_root_on':    8,    # lead enters as single root note
    'lead_melody_on':  24,   # lead gets full notearp melody + delay
    'pad_chord_on':    40,   # pad gets moving chord pattern + seg 16
    'lead_voicing_on': 48,   # lead gets .add voicing shift
    'clap_on':         72,   # clap added (backbeat)
    'fm_on':           96,   # FM modulation on lead
    'pulse_on':        108,  # pulse texture layer
    'hihat_on':        112,  # hi-hat added
    'kick_syncopated': 116,  # kick upgrades to syncopated pattern
}

# ── Gain levels (from SA's confirmed mix values) ──────────────────────────────
# Source: docs/music_theory/02_sa_vocabulary_codified.md §1
# SA's actual gain calls from OCR: kick .gain(1), pad .pg(.5), lead .pg(.7),
# hihat .gain(.5), clap .pg(.7), pulse (no explicit gain, treated as 0.12)
GAIN_KICK  = 1.00
GAIN_PAD   = 0.50
GAIN_LEAD  = 0.70   # SA's confirmed .pg(.7) on lead; previously wrong at 0.45
GAIN_BASS  = 0.55
GAIN_HIHAT = 0.50   # SA's confirmed .gain(.5)
GAIN_CLAP  = 0.70   # SA's confirmed .pg(.7)
GAIN_PULSE = 0.12
```

Every value has a source citation. When something sounds wrong, you look up the source doc and understand why the value was chosen. When you want to change it, you update the doc first.

### `song/theory_tests.py` — tests that the theory is self-consistent

```python
def test_all_scale_degrees_in_range():
    for scale in SCALES.values():
        assert all(0 <= d <= 11 for d in scale)

def test_filter_arc_values_produce_valid_hz():
    for name, slider in FILTER_ARC.items():
        hz = rlpf_to_hz(slider)
        assert 20 <= hz <= 20000, f"{name}: {slider} → {hz:.0f} Hz out of range"

def test_sa_full_open_filter_matches_research():
    # SA's confirmed value 0.877 → ~9400 Hz (from switch_angel_vocabulary.md)
    hz = rlpf_to_hz(FILTER_ARC['full_open'])
    assert 9000 <= hz <= 9800, f"full_open filter {hz:.0f} Hz deviates from SA's 9400 Hz"

def test_sa_lead_base_filter_matches_research():
    # SA's confirmed value 0.593 → ~5400 Hz
    hz = rlpf_to_hz(FILTER_ARC['lead_base'])
    assert 5000 <= hz <= 5800

def test_pad_voicing_offsets_are_below_root():
    # Sub-bass doublings should be below the root
    for offset in PAD_VOICING_OFFSETS[1:]:
        assert offset < 0

def test_notearp_pattern_length():
    assert len(SA_NOTEARP_PATTERN) == 16  # one bar of 16th notes

def test_kick_steps_in_range():
    for step in KICK_STEPS_SYNCOPATED:
        assert 0 <= step <= 15
```

---

## Phase 4 — DSP primitives (`synth/`)

All inner loops must be numpy-vectorised. No `for i in range(n_samples)`. Use `scipy.signal.lfilter` for filters.

`requirements-dev.txt`: `pytest scipy`

### `synth/oscillators.py`
- `sawtooth(freq_hz, n_samples, sr, phase=0.0) → (samples, phase)` — vectorised phase accumulation
- `supersaw(midi_note, n_samples, sr, saw_count=5, detune_cents=60.0, pan=0.0, osc_phases=None) → (buf_l, buf_r, osc_phases)` — `(saw_count, n_samples)` phase matrix, no Python loops. Based on v1's approach (`trance_stream.py:923–999`)
- `sine(freq_hz, n_samples, sr, phase=0.0) → (samples, phase)`
- `brown_noise(n_samples, rng) → ndarray` — `np.cumsum(rng.standard_normal(n))`, normalised

### `synth/filters.py`
- `lpf(signal, cutoff_hz, sr, zi=None) → (output, zi)` — `scipy.signal.lfilter`, state persisted
- `hpf(signal, cutoff_hz, sr, zi=None) → (output, zi)`
- `lpf2(signal, cutoff_hz, q, sr, zi=None) → (output, zi)` — 2-pole Butterworth
- `rlpf_to_hz(slider: float) → float` — `(slider * 12) ** 4`, SA's exact formula

### `synth/envelopes.py`
- `acidenv(n_samples, sr, amount=0.55) → ndarray` — SA's exact params: 3ms attack, tau=`0.08*(0.3+amount*1.4)`, from `prebake.strudel` line confirmed in research chat
- `lpenv(n_samples, sr, base_hz, start_hz=1200.0, ramp_ms=60.0) → ndarray`
- `trancegate(n_samples, sr, bar_pos, samples_per_bar, speed=1.5, duty=0.5) → ndarray` — smooth cosine, no hard clicks. Source: v2's `trancegate_envelope` (already vectorised)

### `synth/effects.py`
- `FeedbackDelay` — circular buffer, vectorised processing, no Python sample loop
- `SimpleFDN` — 4-line feedback delay network, vectorised
- `Sidechain` — SA's `.duck().duckattack(.16).duckdepth(.6)`: detects kick envelope, applies gain reduction to pad/lead at `depth=0.6`, `attack_s=0.16`. Vectorised: compute kick envelope first (rectify + LP filter), then multiply target signal by `1 - depth * kick_env`. This is the source of the "trance pump" feeling — the pad briefly ducks on every kick hit.

### `synth/drums.py`
All seeded: `rng = np.random.default_rng(seed)`. Fixes v2's non-deterministic drums.
- `kick(sr=44100, seed=42) → (buf_l, buf_r)`
- `hihat(sr=44100, decay_s=0.08, seed=42) → (buf_l, buf_r)`
- `clap(sr=44100, seed=42) → (buf_l, buf_r)`
- `pulse_texture(step, total_steps, n_samples, sr=44100) → (buf_l, buf_r)`

---

## Phase 5 — DSP unit tests (`tests/test_synth/`)

Numerical assertions only. No audio hardware. Runs in < 3 seconds total.

**`test_oscillators.py`**: range [-1,1]; zero-crossing frequency accuracy; phase continuity across calls; supersaw has exactly N peaks per harmonic in FFT; renders 44100 samples in < 50ms.

**`test_filters.py`**: attenuation at 10×cutoff > 12dB; passthrough at cutoff/10 < 1dB; state continuity; `rlpf_to_hz(0.877)` within 100Hz of 9400Hz; `rlpf_to_hz(0.593)` within 100Hz of 5400Hz; 44100 samples filtered in < 10ms.

**`test_envelopes.py`**: acidenv peak at 3ms mark; decay rate matches `e^-2` at `2*tau`; trancegate in [0,1], no adjacent delta > 0.05, exactly 1.5 cycles per bar.

**`test_effects.py`**: delay wet=0 equals dry; echo at correct sample; FDN silence in/out; FDN impulse < -40dB within 3s; FDN L≠R; 44100 samples < 100ms.

**`test_drums.py`**: all deterministic with same seed; kick peak > 0.7; hihat energy above 1kHz > below; clap deterministic.

**`test_performance.py`**: full bar (all voices) renders in < 100ms.

---

## Phase 6 — Instrument layer (`instruments/`)

Each instrument: `__init__(config)`, `render(...) → (buf_l, buf_r)`, own state.

### `instruments/pad.py — SupersawPad`
Models SA's exact chain: `supersaw(saw_count=5, detune=0.6)` → `lpenv(2)` → `trancegate(speed=1.5)` → `SimpleFDN` → voicing offsets `[0, -14, -21]`. Parameters from `song/theory.py::GAIN_PAD`, `FILTER_ARC`.

Note: SA's pad uses `.lpenv(2)` (slow LP filter sweep per trigger), **not** acidenv. Acidenv is for bass and lead only — it creates the fast acid character. Applying acidenv to the pad would give it an acid-bass-line character rather than the smooth lush pad swell SA uses.

Sidechain: the pad's output buffer is passed through `Sidechain` before mixing, using the kick buffer as the keying signal. This is how SA's `.duck("3:4:5")` works — orbit 3 (pad) ducks on the kick.

### `instruments/lead.py — AcidLead`
Chain: `supersaw(saw_count=3, detune=0.3)` + brown noise FM → `lpenv` → `acidenv` → `trancegate(speed=1.5)` → `FeedbackDelay(wet=0.7, fb=0.8)` → `pan(rand)`. Parameters from `song/theory.py`.

### `instruments/drums.py — DrumKit`
Pre-renders all drum buffers at init. `render_kick(gain)`, `render_hihat(decay_s, gain)`, `render_clap(gain)`.

### `instruments/bass.py — AcidBass`
`sawtooth` + `acidenv` + `lpf`. Note already transposed -14 semitones by caller.

### `instruments/pulse.py — PulseTexture`
SA's exact confirmed idiom: `pulse!16, dec(.1), fm(time).fmh(time)`.

---

## Phase 7 — Instrument spectral tests (`tests/test_instruments.py`)

These tests render each instrument in isolation and assert spectral properties against the reference audio targets in `research/reference_audio/targets.json`.

```python
from tools.spectrogram import analyse_spectrum

def test_pad_centroid_range():
    # Pad at mid-session filter (slider=0.65) should be in music range
    stats = render_and_analyse(SupersawPad(), cutoff_slider=0.65)
    assert 400 <= stats['mean_centroid_hz'] <= 3000

def test_pad_filter_arc_opens():
    # Closed filter produces lower centroid than open filter
    closed = render_and_analyse(SupersawPad(), cutoff_slider=0.40)
    open_  = render_and_analyse(SupersawPad(), cutoff_slider=0.877)
    assert open_['mean_centroid_hz'] > closed['mean_centroid_hz'] * 1.5

def test_pad_trancegate_creates_variation():
    # At 140 BPM: 1 bar = 60/140*4 s = 1.714s; 1 16th = 1.714/16 = 0.107s = 4725 samples
    SIXTEENTH_SAMPLES = int(44100 * 60 / (140 * 4))  # = 4725 at 140 BPM
    buf_l, _ = SupersawPad().render([60], n_samples=44100*2, sr=44100,
                                     cutoff_slider=0.65, gain=0.5)
    n_steps = len(buf_l) // SIXTEENTH_SAMPLES
    rms_per_16th = [rms(buf_l[i*SIXTEENTH_SAMPLES:(i+1)*SIXTEENTH_SAMPLES])
                    for i in range(n_steps)]
    # Trancegate should cause RMS variation — ratio > 2x between loud and quiet steps
    assert max(rms_per_16th) / (min(rms_per_16th) + 1e-9) > 2.0

def test_lead_fm_broadens_spectrum():
    no_fm  = render_and_analyse(AcidLead(), fm_depth=0.0)
    with_fm = render_and_analyse(AcidLead(), fm_depth=0.5)
    assert with_fm['band_energy']['hi_mid'] > no_fm['band_energy']['hi_mid']

def test_kick_is_bass_dominant():
    stats = render_kick_and_analyse(DrumKit())
    assert stats['band_energy']['bass'] > stats['band_energy']['hi_mid']

def test_hihat_is_air_dominant():
    stats = render_hihat_and_analyse(DrumKit())
    assert stats['band_energy']['air'] > stats['band_energy']['bass'] * 2
```

---

## Phase 8 — Song layer (`song/`)

### `song/pattern.py`
```python
@dataclass
class StepPattern:
    steps: list[int]      # which 16th-note positions fire (0–15)
    notes: list[int]      # MIDI note or scale degree per active step

# Pre-built from theory.py constants:
KICK_BASIC = StepPattern(steps=[0,4,8,12], ...)
CLAP_SYNCOPATED = StepPattern(steps=[0,4,8,11,14], ...)
```

### `song/arcs.py`
Parameter evolution functions, moved from v2 but sourced from `song/theory.py` constants:
- `filter_cutoff_arc(bar, pullback_bars) → float`
- `fm_depth_arc(bar, fm_on_bar=FM_ARC_ONSET_BAR) → float`
- `delay_wet_arc(bar, lead_on_bar) → float`
- `acidenv_arc(bar) → float`

### `song/track.py`
```python
@dataclass
class Track:
    instrument: Any
    pattern: StepPattern
    active_from_bar: int
    gain_target: float
    arc_fn: Optional[Callable] = None   # optional per-bar parameter evolution
```

### `song/song.py`
```python
@dataclass
class Song:
    bpm: float
    root_midi: int
    scale: list[int]           # semitone offsets from theory.py::SCALES
    chord_prog: list[list[int]] # from theory.py::PROGRESSIONS
    notearp_pattern: list[int]  # from theory.py::SA_NOTEARP_PATTERN
    tracks: list[Track]
    stage_bars: dict[str, int]  # from theory.py::STAGE_BARS_DEFAULT + seed jitter
    filter_pb_bars: tuple[int, int]  # seed-determined pullback positions
```

### `song/builder.py`
```python
def build_song(seed: str, mood: str = 'uplifting') -> Song:
    # All musical choices derived from theory.py
    root_midi = 48 + (md5(seed) % 12)
    scale = SCALES[MOOD_TO_SCALE[mood]]
    chord_prog = PROGRESSIONS[MOOD_TO_PROGRESSION[mood]]
    notearp = SA_NOTEARP_PATTERN  # SA's confirmed pattern, seeded variant
    stage_bars = jitter(STAGE_BARS_DEFAULT, seed_rng, max_jitter=4)
    # ... assembles all instruments with parameters from theory.py
```

### `song/renderer.py — SongRenderer`

This is the missing piece that connects the `Song` data structure to actual audio output. Without it Phase 10 has no implementation target.

```python
class SongRenderer:
    def __init__(self, song: Song, sr: int = 44100):
        self.song = song
        self.sr = sr
        self.bar = 0
        # Pre-instantiate all instruments
        self.instruments = {t.instrument_type: t.instrument for t in song.tracks}
        self.sidechain = Sidechain(depth=0.6, attack_s=0.16)
        self.midi_log: dict[str, list] = {}   # voice_name → list of (bar, step, midi_note)

    def render_bar(self) -> tuple[np.ndarray, np.ndarray]:
        """Render one bar. Advances self.bar. Returns (buf_l, buf_r)."""
        # 1. For each active track, determine which steps fire this bar
        #    (using pattern + notearp + scale quantisation from theory.py)
        # 2. Render each instrument's buffer for this bar
        # 3. Apply sidechain: kick buffer keys pad + lead reduction
        # 4. Log MIDI events for any active notes
        # 5. Mix all buffers, apply master gain
        # 6. Increment self.bar
        ...

    def write_midi(self, path: str):
        """Write per-voice MIDI tracks to a multi-track .mid file using mido."""
        # Each voice (kick, pad, lead, bass, hihat, clap, pulse) gets its own track
        # This is what test_song.py expects at /tmp/v3_kick.mid etc.
        ...

    def notearp_to_midi(self, bar: int, chord_degrees: list[int]) -> list[int]:
        """Apply SA_NOTEARP_PATTERN to current chord, return list of MIDI notes for this bar."""
        ...
```

The notearp→trancegate interaction is resolved here: notearp determines **which bars have notes** (the melodic/rhythmic pattern); trancegate modulates the **amplitude envelope** of those notes (the breathing shape). They operate at different time scales — notearp at the bar/beat level, trancegate at the sub-beat level — so they compose cleanly without conflict.

---

## Phase 9 — Song integration tests (`tests/test_song.py`)

Uses the importable `analyse_audio.py` and `spectrogram.py` functions. Renders 8–32 bars and asserts against the SA reference targets.

```python
def test_no_noise_crest_factor():
    render_bars(16)
    assert 3.0 <= analyse_wav('/tmp/v3.wav')['crest_factor'] <= 8.0

def test_spectral_centroid_in_trance_range():
    assert 800 <= analyse_spectrum('/tmp/v3.wav')['mean_centroid_hz'] <= 2500

def test_brightness_in_sa_range():
    # SA reference clips measured at 30–45%
    assert 0.20 <= analyse_spectrum('/tmp/v3_32bar.wav')['brightness_score'] <= 0.55

def test_no_hard_quality_failures():
    warnings = quality_warnings(analyse_wav('/tmp/v3.wav'), analyse_midi('/tmp/v3.mid'))
    hard = ['CLIPPING', 'THIN (bass', 'CLASHING']
    for w in warnings:
        assert not any(f in w for f in hard), f"Hard failure: {w}"

def test_filter_arc_increases_centroid():
    # Centroid in bars 24–32 must be higher than bars 0–8 (filter opening)
    early = analyse_spectrum(trim('/tmp/v3_32bar.wav', 0, 8))
    late  = analyse_spectrum(trim('/tmp/v3_32bar.wav', 24, 8))
    assert late['mean_centroid_hz'] > early['mean_centroid_hz']

def test_determinism():
    render_bars(8, seed='sunrise')
    a = open('/tmp/v3.wav','rb').read()
    render_bars(8, seed='sunrise')
    b = open('/tmp/v3.wav','rb').read()
    assert a == b

def test_kick_density():
    assert analyse_midi('/tmp/v3.mid')['voice_density']['kick'] >= 3.5

def test_spectral_match_sa_reference():
    # Compare band energy ratios to measured SA reference targets
    targets = json.load(open('research/reference_audio/targets.json'))
    gen = analyse_spectrum('/tmp/v3_32bar.wav')
    ref = targets['3fpx7Scysw4']  # use Coding Trance IV as primary reference
    gen_ratio = gen['band_energy']['bass'] / gen['band_energy']['mid']
    ref_ratio = ref['band_energy']['bass'] / ref['band_energy']['mid']
    assert 0.25 < gen_ratio / ref_ratio < 4.0, "Bass/mid balance too far from SA reference"

def test_kick_rhythm_matches_sa_reference():
    from tools.midi_compare import compare_midi
    render_bars(16, seed='sunrise')  # also writes /tmp/v3_kick.mid
    result = compare_midi('/tmp/v3_kick.mid',
                          'research/reference_audio/midi/3fpx7Scysw4/drums.mid')
    assert result['rhythm_similarity'] >= 0.6, \
        f"Kick rhythm similarity {result['rhythm_similarity']:.2f} < 0.60 vs SA reference"

def test_bass_key_matches_sa_reference():
    from tools.midi_compare import compare_midi
    render_bars(16, seed='sunrise')
    result = compare_midi('/tmp/v3_bass.mid',
                          'research/reference_audio/midi/3fpx7Scysw4/bass.mid')
    assert result['key_match'], f"Bass key mismatch: {result['warnings']}"
```

---

## Phase 10 — CLI and real-time playback (`trance_stream_v3.py`)

Wire `build_song` → `SongRenderer` into the existing CLI interface. All flags preserved: `--mood, --bpm, --seed, --volume, --out_midi, --bars, --wav`.

---

## Documentation committed to the repo

Reproducibility is a first-class requirement. Every decision, research finding, and plan must be committed to the repo so the project can be understood, resumed, or handed to someone else from scratch.

### The plan itself

This plan document must be committed to the repo immediately, before any implementation begins:

```
docs/
  plan_v3.md   ← this document, committed verbatim
```

It should be updated whenever the plan changes — not just kept in the Claude internal plans folder. `docs/plan_v3.md` is the authoritative record of why v3 was built the way it was.

### Full committed documentation tree

```
docs/
  plan_v3.md                      — this document (committed before implementation)
  architecture.md                 — three-layer design rationale with diagrams
  music_theory/
    01_trance_harmony.md          — scales, chord progressions, tension/release theory
    02_sa_vocabulary_codified.md  — SA's specific patterns, analytically decoded
    03_trance_rhythm.md           — kick patterns, groove theory, polyrhythm
    04_generative_melody.md       — what makes a trance melody work
research/
  reference_audio/
    3fpx7Scysw4_90s.wav           — extracted reference clips (5 total)
    ...
    pads/pad10.wav ... pad14.wav  — SA's public pad samples (Unlicense)
    targets.json                  — machine-readable spectral targets
    3fpx7Scysw4_90s.png           — spectrogram images (visual reference)
    stems/
      README.md                   — Demucs limitations and stem quality notes
      <video_id>/drums.wav        — separated stems (gitignored if >50MB, paths in README)
      <video_id>/bass.wav
      <video_id>/other.wav
    midi/
      <video_id>_full.mid         — multi-track MIDI (drums + bass + other)
      <video_id>_analysis.md      — automated analysis output (committed)
tools/
  extract_reference_audio.py      — automates Phase 0
  reverse_engineer.py             — end-to-end source separation + MIDI pipeline
  stem_separation.py              — Demucs wrapper
  audio_to_midi.py                — basic-pitch wrapper + MIDI analysis
  midi_compare.py                 — generated vs reference comparison
  README.md                       — tool usage docs
```

### What gets committed vs gitignored

| Item | Decision | Reason |
|------|----------|--------|
| `research/videos/*.webm` | `.gitignore` | 158MB, too large |
| `research/reference_audio/*.wav` | Commit if <10MB each; gitignore + document URL otherwise | Reference ground truth |
| `research/reference_audio/stems/*.wav` | `.gitignore` + document in README | Demucs outputs are large and re-derivable |
| `research/reference_audio/midi/*.mid` | **Commit** | Small, high-value, not re-derivable easily |
| `research/reference_audio/midi/*_analysis.md` | **Commit** | Human-readable analysis, must be versioned |
| `research/reference_audio/targets.json` | **Commit** | Machine-readable acceptance criteria |
| `docs/music_theory/*.md` | **Commit** | The knowledge base |
| `docs/plan_v3.md` | **Commit before implementation** | Reproducibility |

### `.gitignore` additions
```
research/videos/
research/reference_audio/stems/*/
# but NOT research/reference_audio/midi/ — those are committed
```

### `research/reference_audio/README.md`
Documents how to regenerate everything that is gitignored:
```markdown
# Regenerating reference audio and stems

The raw video files and Demucs stem outputs are not committed (too large).
To regenerate:

1. The 5 .webm source videos must be present in research/videos/.
   They are not committed to git. Download them with the existing script:
     python tools/download_videos.py

2. Extract WAV clips (skips first 90s of setup talk):
   python tools/extract_reference_audio.py

3. Run stem separation + MIDI extraction:
   pip install -r requirements-ml.txt   # downloads ~2GB PyTorch + models first run
   python tools/reverse_engineer.py --all

All MIDI outputs and analysis docs in midi/ ARE committed and do not need regeneration.
```

All research spikes produce committed markdown. All MIDI analysis outputs are committed. All spectral targets are committed JSON. If the project is abandoned and resumed a year later, a new engineer reads `docs/plan_v3.md`, then `docs/music_theory/`, then `research/reference_audio/midi/*_analysis.md` — and has complete context without re-running anything.

---

## Execution order

```
Step 0     BEFORE ANYTHING ELSE: copy this plan to docs/plan_v3.md in the repo and commit it.
           This is the reproducibility anchor — all subsequent commits reference it.

Phase 0    Extract reference audio (ffmpeg + curl) + download SA pad samples
Phase 0b   Source separation (Demucs) + audio→MIDI (basic-pitch) on all 5 clips
           → produces per-stem WAVs, per-stem MIDIs, multi-track full MIDIs
           → run midi_to_analysis on each to produce structure docs
Phase 1    Research spikes → docs/music_theory/ (4 documents)
           → informed by Phase 0b analysis, not just OCR
Phase 2    Refactor tools/analyse_audio.py + tools/spectrogram.py
Phase 3    Write song/theory.py + theory_tests.py  ← musical knowledge in code
Phase 4    Write synth/ library
Phase 5    All DSP unit tests pass
Phase 6    Write instruments/ layer
Phase 7    Instrument spectral tests pass
Phase 8    Write song/ layer (uses theory.py throughout)
           song/renderer.py — SongRenderer renders Song dataclass to audio + per-voice MIDI
Phase 9    Write tests/test_song.py — initially fails
Phase 10   Build trance_stream_v3.py — iterate until all song tests pass
Final      Spectrogram visual comparison: generated vs SA reference
```

---

## File map

| File | Action |
|---|---|
| `tools/extract_reference_audio.py` | Create |
| `tools/reverse_engineer.py` | Create — end-to-end pipeline orchestrator |
| `tools/stem_separation.py` | Create — Demucs wrapper |
| `tools/audio_to_midi.py` | Create — basic-pitch wrapper + MIDI analysis |
| `tools/midi_compare.py` | Create — generated vs reference MIDI comparison |
| `research/reference_audio/stems/<id>/*.wav` | Create (Phase 0b) |
| `research/reference_audio/midi/<id>_full.mid` | Create (Phase 0b) — multi-track |
| `research/reference_audio/midi/<id>_analysis.md` | Create (Phase 0b) |
| `research/reference_audio/stems/README.md` | Create — Demucs limitations doc |
| `tools/analyse_audio.py` | Refactor (importable) |
| `tools/spectrogram.py` | Refactor (importable) |
| `research/reference_audio/*.wav` | Create (Phase 0) |
| `research/reference_audio/targets.json` | Create (Phase 0) |
| `docs/music_theory/01_trance_harmony.md` | Create (Spike 1) |
| `docs/music_theory/02_sa_vocabulary_codified.md` | Create (Spike 2) |
| `docs/music_theory/03_trance_rhythm.md` | Create (Spike 3) |
| `docs/music_theory/04_generative_melody.md` | Create (Spike 4) |
| `requirements-dev.txt` | Create |
| `requirements-ml.txt` | Create — ML deps (PyTorch/demucs/basic-pitch), separate from dev |
| `docs/architecture.md` | Create — three-layer design with ASCII diagram |
| `docs/decisions/ADR-T-0004-v3-architecture.md` | Create — ADR explaining why v3 replaces v2's monolithic model |
| `docs/decisions/ADR-T-0005-music-theory-layer.md` | Create — ADR documenting the theory.py approach |
| `tools/README.md` | Update — add Phase 0b tools to existing README |
| `synth/__init__.py` | Create |
| `synth/oscillators.py` | Create |
| `synth/filters.py` | Create |
| `synth/envelopes.py` | Create |
| `synth/effects.py` | Create |
| `synth/drums.py` | Create |
| `instruments/__init__.py` | Create |
| `instruments/pad.py` | Create |
| `instruments/lead.py` | Create |
| `instruments/drums.py` | Create |
| `instruments/bass.py` | Create |
| `instruments/pulse.py` | Create |
| `song/__init__.py` | Create |
| `song/theory.py` | Create |
| `song/pattern.py` | Create |
| `song/arcs.py` | Create |
| `song/track.py` | Create |
| `song/song.py` | Create |
| `song/builder.py` | Create |
| `song/renderer.py` | Create — `SongRenderer` class (renders `Song` to audio + MIDI) |
| `tests/__init__.py` | Create |
| `tests/test_synth/__init__.py` | Create |
| `tests/test_synth/` | Create (5 files) |
| `tests/test_instruments.py` | Create |
| `tests/test_song.py` | Create |
| `trance_stream_v3.py` | Create (Phase 10) |
| `trance_stream_v2.py` | Leave untouched |

---

## What makes this categorically different from v1 and v2

| Problem | v1/v2 | v3 |
|---|---|---|
| Musical knowledge | Implicit in magic constants | Explicit in `song/theory.py`, sourced from `docs/music_theory/` |
| DSP correctness | Python loops → buffer starvation | numpy-vectorised + scipy |
| Level saturation | PAD_LEVEL=1.40 × DRIVE=1.4 | SA's confirmed gain values, no DRIVE |
| Architecture | Monolithic main() loop | 4 layers: Research → Theory → Instruments → DSP |
| Testability | Must run main() to test anything | Each layer independently testable |
| Why does a value have this setting? | Unknown (was in the code) | Every value cites its source doc |
| How do you know it sounds right? | Listen and guess | Assert against reference audio from SA's own sessions |
| Reproducibility | Cannot reconstruct reasoning | All research committed, all decisions documented |
