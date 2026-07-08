# Diagnostic Tools

Four scripts for understanding what `trance_stream.py` is actually producing and
how it compares against a reference track.  They work on the WAV and MIDI files
that `trance_stream.py` writes with `--wav` and `--out_midi`, so you never need a
running audio stream to diagnose a problem.

---

## Workflow

```
# 1. Render a fixed-length clip offline (fast, no audio hardware needed)
python trance_stream.py --bars 32 --wav /tmp/out.wav -o /tmp/out.mid -s center -m uplifting

# 2. Run the composite health check (7 pass/fail metrics — start here)
python tools/health_check.py /tmp/out.wav

# 3. Get the detailed audio + MIDI report
python tools/analyse_audio.py /tmp/out.wav /tmp/out.mid --seed center --mood uplifting

# 4. Drill into specific bars to see exact notes
python tools/midi_forensic.py /tmp/out.mid --seed center --bars 20 --voice lead

# 5. Compare spectrograms with a reference track (requires librosa)
python tools/spectrogram.py /tmp/switch_angel_ref.wav --out /tmp/ref_spec.png --title "Reference"
python tools/spectrogram.py /tmp/out.wav --out /tmp/gen_spec.png --title "Generated"
open /tmp/ref_spec.png /tmp/gen_spec.png
```

---

## `analyse_audio.py`

**What it does:** Reads a WAV and its companion MIDI and prints a structured
report in two sections.

### WAV section

| Output | What it tells you |
|--------|------------------|
| Peak / RMS level | Whether the mix is too quiet, too hot, or well-balanced |
| Spectral energy by band | Whether bass is drowning mid, or hi-mid is harsh |
| Crest factor | Dynamic range proxy — low = distorted/flat, high = too sparse |

Spectral bands:

| Band | Range | Trance target |
|------|-------|--------------|
| sub | <80 Hz | Should be present but not dominant |
| bass | 80–300 Hz | Strongest band — kick + bass live here |
| mid | 300–2k Hz | Lead and pad fundamentals — should be –5 to –10 dB below bass |
| hi-mid | 2k–8k Hz | Upper harmonics — if dominant, something is too harsh/bright |
| air | >8k Hz | Should be very quiet (no cymbals in this synth) |

Flags printed automatically:
- `← HARSH` if hi-mid or air band is within 3 dB of the loudest band
- `← THIN` if bass or sub is more than 20 dB below the loudest band

### MIDI section

| Output | What it tells you |
|--------|------------------|
| Note counts / range / velocity | Whether voices are active, where they sit in pitch |
| Lead interval distribution | Whether the melody flows or jumps randomly |
| Lead note durations | Whether notes are long enough for the trance gate to pulse on |
| Harmony check | Whether any voice is playing notes outside the root minor scale |
| Bass roots per chord block | Confirms the chord progression is actually being followed |
| Arp pitch-class distribution | Shows which chord tones are being emphasised |
| Voice density | Notes per bar — catches voices that are too busy or too sparse |

Flags printed automatically:
- `⚠ TOO MANY UNISONS` — lead melody is stuck on the same pitch
- `⚠ MEAN INTERVAL TOO LARGE` — melody is jumping rather than flowing
- `⚠ TOO MANY LARGE LEAPS` — erratic, non-melodic lead
- `⚠ LEAD NOTES ALL SHORT` — notes expire before trance gate has time to pulse; will sound like random bursts rather than a sustained melodic line
- `← CLASHING` — more than 5% of notes in a voice fall outside the root minor scale

### Usage

```
python tools/analyse_audio.py [WAV_PATH] [MIDI_PATH] [--seed SEED] [--mood MOOD]

Arguments:
  WAV_PATH    Path to WAV file           (default: /tmp/trance_out.wav)
  MIDI_PATH   Path to MIDI file          (default: /tmp/trance_out.mid)
  --seed      Seed used to generate      (default: center)
  --mood      Mood used to generate      (default: uplifting)
```

The `--seed` and `--mood` arguments are used to reconstruct the expected chord
progression so that out-of-scale notes can be flagged correctly.

### Dependencies

```
pip install numpy mido
```

---

## `midi_forensic.py`

**What it does:** Prints every note event in every voice, bar by bar. Each line
shows the beat position, pitch name, duration in beats, and whether the note is
a chord tone for the current chord block.

This is the tool to reach for when `analyse_audio.py` flags a problem and you
need to see *which notes* are causing it, *when* they fire, and *how long* they
last.

### Example output

```
Seed: 'center'  →  root: G  |  mood: uplifting  |  progression: Gm → D# → A# → F

 BAR  CHORD   VOICE  BEAT   NOTE   DUR (b)  IN CHORD
--------------------------------------------------------
   5  D#      LEAD   0.00   G4      4.00b  yes
              ARP    0.00   G4      0.25b  yes
              BASS   0.00   D#3     0.25b  yes
   ...
```

`DUR (b)` is note duration in beats. A lead note at `4.00b` is a full bar —
that is what you want. Lead notes at `0.25b` mean the lead is firing 16th-note
bursts and sounds random. `NO ⚠` in the last column means a note is not a chord
tone — if it appears often, harmony is broken.

### Usage

```
python tools/midi_forensic.py [MIDI_PATH] [--seed SEED] [--mood MOOD]
                              [--bars N] [--voice VOICE]

Arguments:
  MIDI_PATH   Path to MIDI file           (default: /tmp/trance_out.mid)
  --seed      Seed used to generate       (default: center)
  --mood      Mood (default: uplifting)
  --bars N    Show only first N bars
  --voice     Filter: lead | arp | bass | pad | kick
```

### Dependencies

```
pip install mido
```

---

## `spectrogram.py`

**What it does:** Generates a mel spectrogram PNG and prints a text spectral report
for a WAV file — spectral energy by band, spectral centroid over time, and a
brightness score (fraction of energy above 2 kHz).

Use this to compare the generated output against a reference track visually.  Two
spectrograms side by side immediately show frequency balance differences that are
hard to read from the band-energy table alone.

### Example output

```
File:        /tmp/switch_angel_ref.wav
Duration:    277.8 s  (44100 Hz, 2 ch)

Spectral energy by band (relative to loudest):
  sub         ██████████████████████████████  +0.0 dB
  bass        ██████████████                  -6.5 dB
  mid         ████                            -17.3 dB
  hi-mid      █                               -25.4 dB
  air                                         -39.0 dB

Spectral centroid: mean=809 Hz  (trance target: 800-2500 Hz)
Brightness score:  3.88% of energy above 2 kHz
```

### Usage

```
python tools/spectrogram.py [WAV_PATH] [--out PNG_PATH] [--title TITLE]

Arguments:
  WAV_PATH   Path to WAV file  (default: /tmp/trance_out.wav)
  --out      Output PNG path   (default: <wav>.png)
  --title    Title shown on spectrogram
```

### Dependencies

```
pip install numpy matplotlib librosa
```

---

## `health_check.py`

**What it does:** Runs 7 (optionally 8) pass/fail checks derived from
`docs/trance-reference.md` Section 4, and prints a summary table.  Start here
when evaluating a new render — it gives a single objective score and flags which
dimension needs attention.

### Checks

| Check | Target | What it catches |
|---|---|---|
| BPM | ~140 (±5) | Clock drift if BPM ever changes |
| Beat autocorr | > 0.40 | Missing or irregular kick pattern |
| Centroid mean | 800–3500 Hz | Mix too dark or too harsh |
| Centroid std (LFO) | > 200 Hz | Filter LFO not audible |
| LFO rate | 0.01–0.50 Hz | LFO too fast or too slow |
| Chroma entropy | 1.5–3.5 | Melody stuck on one or two notes |
| Band balance | bass ≥ −6 dB, hi-mid ≤ −10 dB | Imbalanced mix |
| MFCC similarity | > 0.70 | Timbre distance from reference WAV |

### Example output

```
Health check: /tmp/trance_out.wav

  Duration: 61.6 s  (22050 Hz mono)

============================================================
CHECK                   STATUS  DETAIL
------------------------------------------------------------
  BPM                   PASS  143.6  (target: ~140, librosa ±5)
  Beat autocorr         PASS  0.511  (target: >0.40)
  Centroid mean         PASS  1807 Hz  (target: 800–3500 Hz)
  Centroid std (LFO)    PASS  1269 Hz  (target: >200 Hz)
  LFO rate              PASS  0.016 Hz  (target: 0.01–0.50 Hz)
  Chroma entropy        PASS  3.43  (target: 1.5–3.5)
  Band balance          PASS  sub: -7.8dB  bass: +0.0dB  mid: -9.2dB  hi-mid: -21.6dB
  MFCC similarity       FAIL  0.3238  (target: >0.70)
============================================================

  7/8 checks passed  (0 skipped)
```

### Usage

```
python tools/health_check.py [WAV_PATH] [--ref REF_WAV]

Arguments:
  WAV_PATH   Path to WAV file             (default: /tmp/trance_out.wav)
  --ref      Reference WAV for MFCC test  (default: /tmp/switch_angel_ref.wav)
```

### Dependencies

```
pip install librosa scipy numpy
```

---

## How these tools were used during development

These tools were written to diagnose specific problems heard in the audio output.
The process:

1. **Hear something wrong** (e.g. "random piercing notes over everything")
2. **Render offline** with `--wav` and `--out_midi` — no need to sit through the
   full stream
3. **Run `analyse_audio.py`** to get quantified confirmation of what is wrong:
   - First run showed bass band at +0 dB, hi-mid at –26 dB (bass was 4× too
     loud due to rolling notes with `steps_remaining=4` causing 4 overlapping
     bass notes at all times)
   - Lead interval distribution showed 33% unison intervals — `chord_to_register`
     was returning only 3 candidate notes (one per chord tone, not the full
     register pool), so the lead kept landing on the same pitch
4. **Run `midi_forensic.py`** to see the exact notes:
   - Lead notes confirmed at 0.25–1.00 beat duration with 4–6 changes per bar —
     identified that the trance gate had no sustained note to work with; the lead
     was acting as a fast arpeggiator rather than a melody line
   - Lead pitch range crept from A#4 to G5/A#5 within 20 bars — identified the
     upward drift bug in `select_lead_note`
5. **Fix the code**, re-render, re-run the tools to confirm the fix

The final correct state for the lead voice:
- One note per bar (`DUR = 4.00b`)
- Mean interval ≤ 5 semitones (conjunct motion)
- Pitch range capped at D4–D5 (warm mid register, not piercing)
- 0% out-of-scale notes

**Switch Angel reference analysis (July 2026):** obtained her actual Strudel source
code and reference WAV.  Key findings that informed generator changes:

- Her "lead" is a **3-voice supersaw chord stack** (+7 / 0 / -7 semitones) — not
  a single-note melody.  Trance gate pulses this chord; the melodic movement comes
  from the slow root-note change once per bar.
- Lead filter is **almost fully open** (~15 kHz), not a warm mid filter.
- Arp voice does not exist in her setup — rhythmic movement is entirely from the
  trance gate.  The generator's separate arp voice was cluttering the mix.
- Pad voicing is **wide-spread** (root −14 and −21 semitones below), not
  close-position.  The lower notes supply the bass body.
