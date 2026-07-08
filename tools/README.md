# Diagnostic Tools

Two scripts for understanding what `trance_stream.py` is actually producing.
They work on the WAV and MIDI files that `trance_stream.py` writes with `--wav`
and `--out_midi`, so you never need a running audio stream to diagnose a problem.

---

## Workflow

```
# 1. Render a fixed-length clip offline (fast, no audio hardware needed)
python trance_stream.py --bars 32 --wav /tmp/out.wav -o /tmp/out.mid -s center -m uplifting

# 2. Get the high-level audio + MIDI report
python tools/analyse_audio.py /tmp/out.wav /tmp/out.mid --seed center --mood uplifting

# 3. Drill into specific bars to see exact notes
python tools/midi_forensic.py /tmp/out.mid --seed center --bars 20 --voice lead
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
