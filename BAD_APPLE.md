# Bad Apple!! Trance Cover

A side-quest script that reproduces the Bad Apple!! instrumental (Alstroemeria Records
arrangement, 138 BPM) using the switch-angel synthesis infrastructure.  
It reads a committed MIDI reference file and drives the same instrument classes used by
`trance_stream_v3.py` — no modifications to that script.

---

## Quick Start

```bash
# Real-time playback with ASCII video in the terminal
python bad_apple_cover.py --stream --viz

# Render to WAV file (no audio device needed)
python bad_apple_cover.py --wav bad_apple.wav

# First 32 bars only (quick listen test)
python bad_apple_cover.py --bars 32 --stream

# First 8 bars to WAV (fastest smoke test)
python bad_apple_cover.py --bars 8 --wav /tmp/ba_test.wav
```

---

## Reproducibility

The MIDI source file is committed at:
```
research/reference_audio/midi/bad_apple.mid
```

To re-fetch it from the original source:
```bash
python tools/fetch_bad_apple_midi.py
```

**Determinism guarantee:** same MIDI file + same `--bpm` = byte-identical WAV output.
The only RNG in the signal path is seeded with a constant (`DrumKit(seed=42)`,
`AcidLead._rng = np.random.default_rng(42)`).

**MIDI source:** [github.com/Handhule90/badapple-midi](https://github.com/Handhule90/badapple-midi)  
Author: Handhule90 (PGFLIMSXD/nlexsctex/handhule90). 11 tracks, 138 BPM, ~124 bars.

---

## Instrument Mapping

| MIDI Track        | Role          | Instrument Class          |
|-------------------|---------------|---------------------------|
| Drums             | drums         | `DrumKit` (from synth)    |
| Sub bass          | bass          | `AcidBass`                |
| Bass / Bass2      | bass (merged) | `AcidBass`                |
| Synth1 / Arp / Guitar | lead melody | `AcidLead` (smooth)    |
| Synth2            | ignored       | absorbed into hard-coded pad chords |
| Vocals            | ignored       | cannot synthesise vocals  |
| Perc1 / Perc2     | hi-hat texture | `DrumKit.render_hihat()` |

Multiple bass tracks at the same step → lowest pitch wins (sub bass priority).  
Multiple melody tracks at the same step → highest pitch wins (melody sits on top).

---

## Chord Table

Bad Apple!! uses a simple 4-chord loop in **A natural minor**:

| Bars (within 16-bar cycle) | Chord | Scale degrees |
|----------------------------|-------|---------------|
| 0–3                        | Am    | [0, 4]        |
| 4–7                        | F     | [5, 2]        |
| 8–11                       | C     | [2, 6]        |
| 12–15                      | G     | [6, 3]        |

The progression is hard-coded in `BAD_APPLE_CHORDS` — not extracted from the MIDI —
because the melody tracks contain the melodic line, not block chords.

---

## Section Structure

| Bar range | Section  | Kick | Pad | Bass | Lead |
|-----------|----------|------|-----|------|------|
| 0–5       | intro    | —    | ✓   | —    | —    |
| 6–21      | verse 1  | ✓    | ✓   | ✓    | ✓    |
| 22–37     | chorus 1 | ✓    | ✓   | ✓    | ✓    |
| 38–53     | verse 2  | ✓    | ✓   | ✓    | ✓    |
| 54–69     | chorus 2 | ✓    | ✓   | ✓    | ✓    |
| 70–79     | bridge   | ✓    | ✓   | —    | —    |
| 80–96     | final    | ✓    | ✓   | ✓    | ✓    |
| 97+       | outro    | ✓    | ✓   | ✓    | —    |

---

## CLI Reference

| Flag        | Default                                      | Description                              |
|-------------|----------------------------------------------|------------------------------------------|
| `--midi`    | `research/reference_audio/midi/bad_apple.mid`| Path to MIDI reference file             |
| `--bpm`     | `138.0`                                      | Tempo override                           |
| `--wav`     | `bad_apple.wav` (offline) / none (stream)    | Output WAV file path                     |
| `--stream`  | off                                          | Real-time playback via sounddevice       |
| `--viz`     | off                                          | Terminal visualiser with ASCII video     |
| `--bars`    | all (~124)                                   | Render only first N bars                 |
| `--volume`  | `1.0`                                        | Output volume multiplier                 |

---

## Architecture

```
bad_apple_cover.py
  parse_midi()          reads bad_apple.mid → per-bar note data
  BadAppleSong          duck-typed song dataclass for the visualiser
  BadAppleRenderer      owns DrumKit + SupersawPad + AcidLead + AcidBass
    render_bar()        mirrors SongRenderer._render_bar() from song/renderer.py
    render_bars()       loop over render_bar()
    write_wav()         identical to SongRenderer.write_wav()
  _stream_bars()        ported from trance_stream_v3._stream_bars()
    render thread       fills a queue.Queue(maxsize=3)
    audio thread        drains queue → sounddevice.OutputStream
    visualiser          Visualiser + make_bar_info() from tools/visualiser.py
```

### Signal chain per bar

1. **Kick** — MIDI drum steps, `DrumKit.render_kick()`, spill management across bars
2. **Hihat** — MIDI hihat steps, `DrumKit.render_hihat(decay_s=0.08)`
3. **Clap** — MIDI clap steps, `DrumKit.render_clap()`
4. **Pad** — hard-coded chord + `SupersawPad.render()` + sidechain ducking
5. **Bass** — MIDI bass notes, `AcidBass.render()` per note onset + sidechain
6. **Lead** — MIDI melody notes, `AcidLead.render()` per note onset + sidechain
7. **Master gain** (4-bar fade-in) + `np.tanh` soft clip

### Fallbacks when MIDI data is absent

If a bar contains no MIDI data for a voice, the renderer uses sensible defaults:
- No kick steps → four-on-floor `[0, 4, 8, 12]`
- No hihat steps → offbeat 8ths `[0, 2, 4, 6, 8, 10, 12, 14]`
- No clap steps → backbeat `[4, 12]`
- No bass notes → root note (A2) on steps 0 and 8
- No lead notes → lead instrument silent

---

## Known Limitations / Next Steps

- **Synth2 track ignored** — this track contains a counter-melody / harmony; mapping
  it to a second `AcidLead` instance would add richness
- **Guitar track ignored** — chordal strums; could drive the pad with richer voicings
- **No FM for intro bars** — FM depth is zero until bar 22 by design; the intro pad
  sounds slightly plain compared to the original
- **Vocals not synthesised** — could be approximated with a formant filter on the lead
- **Hihat decay is fixed** — `trance_stream_v3.py` modulates it with a triangle LFO
  (SA's confirmed pattern); `hihat_decay_arc()` from `song/arcs.py` could be wired in
