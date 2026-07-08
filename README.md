# TranceStream

A procedural trance music generator in the style of Switch Angel's live-coded
Strudel sets. Streams stereo audio to your system output in real time, exports
MIDI, and writes WAV files for offline analysis.

All audio is synthesised from mathematics — no samples, no soundfonts, fully
DMCA-safe.

---

## Quick start

```bash
pip install numpy sounddevice MIDIUtil
python trance_stream_v2.py
```

Plays indefinitely at 140 BPM. Press Ctrl+C to stop.

---

## Scripts

| Script | Status | Description |
|--------|--------|-------------|
| `trance_stream_v2.py` | **Current** | Full rewrite from Switch Angel's actual Strudel code |
| `trance_stream.py` | Legacy | Original v1 — kept for reference |

Use `trance_stream_v2.py` for everything. The v1 script is preserved but no
longer actively developed.

---

## CLI reference — v2

```
python trance_stream_v2.py [OPTIONS]

  --mood        Harmonic character (default: uplifting)
                uplifting | dark | acid | progressive | dreamy

  -b, --bpm     Tempo in BPM (default: 140)

  -s, --seed    Text seed for deterministic generation (default: center)
                Any string — same seed + mood always produces the same track.
                Different seeds give different keys, patterns, and timing.

  -v, --volume  Master volume 0.0–1.0 (default: 0.90)

  -o, --out_midi   Write a MIDI file to this path on exit

      --bars    Stop after N bars then fade out (default: 0 = infinite)

      --wav     Write output to a WAV file instead of playing live
```

---

## Making tracks

The two main levers are `--mood` and `--seed`.

**`--mood`** sets the harmonic character: scale, chord progression, and overall
emotional texture.

**`--seed`** is a free-text string. It derives the root key via MD5 hash
(deterministic but non-obvious), picks the notearp rhythmic pattern, offsets
the 11 arrangement stage timings, and positions the two filter-arc pullbacks.
Same seed + mood always gives the same track.

```bash
# Uplifting — i → iv → III → v in a seed-derived key
python trance_stream_v2.py --mood uplifting -s "sunrise"

# Dark — i → iv → i → viidim, tighter gate
python trance_stream_v2.py --mood dark -s "midnight" -b 145

# Acid — i → III → iv → III loop
python trance_stream_v2.py --mood acid -s "303"

# Progressive — major scale, I → IV → V → ii
python trance_stream_v2.py --mood progressive -s "journey"

# Dreamy — dorian scale, i → iv → ii → III
python trance_stream_v2.py --mood dreamy -s "velvet sphinx"
```

The startup line shows what was generated from your seed:

```
[v2] seed=sunrise mood=uplifting root=F key=Fm prog=i-iv-III-v arp_variant=3
```

---

## Moods

| Mood | Scale | Progression | Character |
|------|-------|-------------|-----------|
| `uplifting` | Natural minor | i → iv → III → v | Euphoric, soaring |
| `dark` | Natural minor | i → iv → i → viidim | Tense, driving |
| `acid` | Natural minor | i → III → iv → III | Hypnotic, cyclic |
| `progressive` | Major | I → IV → V → ii | Bright, groovy |
| `dreamy` | Dorian | i → iv → ii → III | Bittersweet, floating |

---

## Arrangement

v2 uses an **additive stage model** — voices enter one at a time and stay.
There is no breakdown or drop (this matches Switch Angel's actual live-coding
approach: her arc is strictly additive over a 5–8 minute session).

The 11 stages and their default bar positions (shifted ±4 bars per seed):

| Stage | Default bar | What happens |
|-------|-------------|--------------|
| kick_on | 0 | Kick drum enters |
| pad_on | 2 | Pad enters on single root note |
| lead_root_on | 8 | Lead enters on single root note |
| lead_melody_on | 24 | Lead gets full notearp melody + delay |
| pad_chord_on | 40 | Pad gains moving chord pattern + seg 16 |
| lead_voicing_on | 48 | Lead gains bar-varying voicing shift |
| clap_on | 72 | Backbeat clap added |
| fm_on | 96 | FM modulation opens on lead |
| pulse_on | 108 | Pulse texture shimmer layer added |
| hihat_on | 112 | Hi-hat added |
| kick_syncopated | 116 | Kick upgrades from 4-on-floor to beat(0,4,8,11,14) |

---

## Parameter arcs

Three synthesis parameters evolve continuously over the session, independent of
the stage system. These match documented slider movement in Switch Angel's videos:

**Filter cutoff** (`rlpf slider`): starts at ~2.8 kHz, opens to ~12 kHz by
bar 128. Two deliberate pullbacks (darker moments) at seed-determined positions.

**FM depth**: zero for the first ~96 bars, then ramps to 0.55 — adds metallic
texture and warmth to the lead in the second half of the session.

**Delay wet** (lead): opens toward a 0.80 wash around bar 48 (maximum spatial
depth), then pulls back to 0.50 for clarity. The delay is always 70% wet /
80% feedback / quarter-note time.

**AcidEnv brightness**: steadily brightens from 0.44 → 0.85 over the full
session — notes become punchier and more present as the arrangement fills in.

---

## Synthesis — what v2 does differently from v1

v2 was rebuilt from scratch after OCR-analysing 311 code snapshots extracted
from Switch Angel's YouTube live-coding sessions. See
`research/analysis/switch_angel_vocabulary.md` for the full reference.

| Element | v1 | v2 |
|---------|----|----|
| Kick pattern | Four-on-floor | Syncopated beat(0,4,8,11,14) |
| Hi-hat | Absent | white!16, HPF 1200Hz, tri-LFO decay |
| Clap | Absent | Backbeat (steps 4, 12) |
| Trancegate | Binary on/off | Smooth cosine, 1.5× bar rate |
| Lead | 3-voice stack held 4 bars | Notearp rhythmic pattern, acidenv |
| Lead FM | Absent | Brown noise FM, depth follows arc |
| Lead delay | Absent | 70% wet / 80% feedback / quarter-note |
| Pad | Moving chords, binary gate | seg-16 retrigger, acidenv, smooth gate |
| Filter | Static closed LPF | Open (lpenv sweep per trigger + arc) |
| Pulse texture | Absent | pulse!16 FM-time modulated |
| Arrangement | 5-phase loop | 11 additive stages, no breakdown/drop |
| Seed variation | Root key only | Key + scale + chord prog + arp pattern + stage timing + filter arcs |

---

## Exporting WAV and MIDI

```bash
# Render 128 bars to WAV (no audio hardware needed)
python trance_stream_v2.py --bars 128 --wav out.wav -s "sunrise" --mood uplifting

# Write MIDI on exit
python trance_stream_v2.py --bars 64 --wav out.wav -o out.mid -s "sunrise"
```

MIDI channel assignments:

| Channel | Voice |
|---------|-------|
| 0 | Lead |
| 4 | Kick |

---

## Terminal output

One line per bar:

```
[v2] bar=   1  stages=1/11  K:0.04 P:0.00 L:0.00  filt=1.9kHz fm=0.00 dly=0.55
[v2] bar=   9  stages=3/11  K:1.00 P:0.99 L:0.04  filt=2.2kHz fm=0.00 dly=0.55
[v2] bar=  41  stages=5/11  K:1.00 P:1.00 L:1.00  filt=3.1kHz fm=0.00 dly=0.71
[v2] bar=  97  stages=8/11  K:1.00 P:1.00 L:1.00  filt=8.7kHz fm=0.05 dly=0.60
[v2] bar= 117  stages=11/11 K:1.00 P:1.00 L:1.00  filt=11kHz  fm=0.40 dly=0.50
```

Fields: bar number · stages active · kick/pad/lead gain · filter cutoff · FM depth · delay wet.

---

## Research pipeline

The `research/` directory contains the full reproducibility pipeline used to
extract Switch Angel's synthesis parameters from her YouTube videos.

```
research/
  analysis/
    switch_angel_vocabulary.md    — synthesis parameters, end-state reference
    switch_angel_song_structure.md — temporal arc, build order, variation techniques
  extracted/
    <video_id>/
      code.jsonl    — timestamped OCR'd code snapshots
      summary.md    — annotated code evolution
  README.md         — pipeline documentation
```

To re-extract from the videos:

```bash
# Install research deps
pip install -r tools/requirements-research.txt
brew install tesseract ffmpeg   # macOS

# Download the 5 canonical videos
python tools/download_videos.py

# Extract and OCR
python tools/extract_strudel_code.py
```

Raw video files are excluded from git (too large). Extracted text
(`code.jsonl`, `summary.md`) is committed.

---

## Diagnostic tools

```bash
# Render offline
python trance_stream_v2.py --bars 32 --wav /tmp/out.wav -s center

# Spectral report
python tools/analyse_audio.py /tmp/out.wav

# Spectrogram image
python tools/spectrogram.py /tmp/out.wav --out /tmp/spec.png
```

See `tools/README.md` for full usage.

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `numpy` | Audio buffer arithmetic |
| `sounddevice` | Real-time stereo PCM output |
| `MIDIUtil` | MIDI file construction |

```bash
pip install numpy sounddevice MIDIUtil
```

Python 3.10 or later required.

---

## Reference

Target sound: Switch Angel's live-coded trance sets.

- YouTube channel: `https://www.youtube.com/@Switch-Angel`
- 311 OCR'd code snapshots across 5 videos — see `research/extracted/`
- Full synthesis and structural analysis — see `research/analysis/`

TranceStream does not copy or depend on her code. The research was used to
understand the target synthesis chain and composition approach; all code is
original.

---

## License

Mozilla Public License 2.0 — see the header of `trance_stream_v2.py`.
