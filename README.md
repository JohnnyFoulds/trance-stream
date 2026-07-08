# TranceStream

A procedural trance music generator in the style of Switch Angel's live-coded
Strudel sets. Streams stereo audio to your system output in real time, exports
MIDI, and participates in the `stream_dj.py` crossfade ecosystem.

All audio is synthesised from mathematics — no samples, no soundfonts, fully
DMCA-safe.

---

## Quick start

```bash
pip install numpy sounddevice MIDIUtil
python trance_stream.py
```

Plays indefinitely at 140 BPM in uplifting trance mode. Press Ctrl+C to stop.

---

## CLI reference

```
python trance_stream.py [OPTIONS]

  -m, --mood        Harmonic mood (default: uplifting)
                    uplifting | dark | acid | progressive | ambient

  -b, --bpm         Tempo in BPM, 120–150 (default: 140)

  -s, --seed        Text seed for deterministic generation (default: center)
                    Any string — same seed + mood always produces the same track.

  -v, --volume      Master volume 0.0–1.0 (default: 0.15)

      --fade_in     Fade in over N bars on startup (default: 0)
                    Used by stream_dj.py; you can also use it manually.

  -o, --out_midi    Write a MIDI file to this path on exit

      --bars        Stop after N bars then fade out (default: 0 = infinite)
                    The fade-out is always 4 bars, so total duration is N+4 bars.
```

---

## Making tracks

The two main levers are `--mood` and `--seed`.

**`--mood`** selects the harmonic character: chord progression, bass rhythm
pattern, and arp direction. This is the biggest tonal change between tracks.

**`--seed`** is a free-text string that does two things: it derives the root key
(via MD5 hash, so the key is deterministic but non-obvious), and it seeds the
entire generative engine so the same seed always produces the same output.

```bash
# Euphoric uplifting trance — soaring i-VI-III-VII progression
python trance_stream.py -m uplifting -s "sunrise"

# Dark driving trance — intense i-iv-v-i minor progression
python trance_stream.py -m dark -s "midnight" -b 145

# Acid hypnotic — TB-303-style bass, i-VII-VI-VII pattern
python trance_stream.py -m acid -s "303" -b 148

# Progressive, groovy — broken-octave bass, slower harmonic feel
python trance_stream.py -m progressive -s "journey" -b 130

# Ambient floating — major 7th chords, whole-bar bass sustain
python trance_stream.py -m ambient -s "void" -b 122
```

The seed can be anything: `"2026-07-08"`, `"velvet sphinx"`, a name, a date.
Two different seeds with the same mood give different keys, different CA-driven
rhythmic patterns, and different trance gate textures — but the same overall
structure and feel.

---

## Exporting MIDI

Add `--out_midi` and `--bars` to capture a fixed-length take:

```bash
# One full phase cycle (Intro + Groove + Breakdown + Buildup + Drop = 52 bars)
python trance_stream.py -m uplifting -s "sunrise" --bars 52 -o sunrise.mid

# Short 32-bar clip for a DAW loop
python trance_stream.py -m dark -s "midnight" -b 145 --bars 32 -o midnight.mid
```

The MIDI file is also written on Ctrl+C if `--out_midi` is set, so you can
record as long a take as you like and stop when it sounds good.

**Channel assignments** (General MIDI programs):

| Channel | Voice | GM Program |
|---------|-------|------------|
| 0 | Lead | 80 — Synth Lead (Square) |
| 1 | Arp | 80 — Synth Lead (Square) |
| 2 | Bass | 38 — Synth Bass (Finger) |
| 3 | Pad | 89 — Pad 2 (Warm) |
| 4 | Kick | 116 — Taiko Drum |

Imports cleanly into GarageBand, Ableton Live, and any standard MIDI sequencer.

---

## Moods

| Mood | Character | Progression | Bass | Arp direction |
|------|-----------|-------------|------|---------------|
| `uplifting` | Euphoric, soaring | i → VI → III → VII | Rolling 16ths | Up |
| `dark` | Intense, driving | i → iv → v → i | Off-beat | Up-down |
| `acid` | Hypnotic, TB-303 | i → VII → VI → VII | TB-303 pattern | Up |
| `progressive` | Groovy, slower | i → iv → I → VII | Broken octave | Down |
| `ambient` | Open, floating | Imaj7 → VIImaj7 → VImaj7 → VIImaj7 | Whole-bar sustain | Up |

All moods use 4/4 time at 16th-note resolution, with 4 bars per chord and 16
bars per arrangement phase.

---

## Arrangement

Every run cycles automatically through five phases. Each phase is 16 bars.
After the first cycle, Intro is skipped and the four-phase loop repeats
indefinitely.

```
Intro → Groove → Breakdown → Buildup → Drop → Groove → Breakdown → …
```

| Phase | Length | Kick | Bass | Lead | Arp | Pad | Other |
|-------|--------|------|------|------|-----|-----|-------|
| Intro | 4 bars | soft | off | off | filtered | filtered | — |
| Groove | 16 bars | full | full | full | full | full | — |
| Breakdown | 16 bars | off | off | filtered | full | full | — |
| Buildup | 16 bars | half-time | off | off | full | full | noise riser |
| Drop | 16 bars | full | full | full | full | full | — |

Voice gains ramp smoothly over 2 bars at each phase boundary — no hard cuts.

At 140 BPM one full cycle (~52 bars) is approximately 89 seconds. The music
never exactly repeats — the CA-driven lead and arp lines are aperiodic.

---

## How it works

### Synthesis

**Lead and pad:** N detuned sawtooth oscillators (7 for lead and pad, 3 for
bass) — the classic "supersaw" of the Roland JP-8000. Oscillators are spread
across the stereo field using constant-power panning. A first-order IIR
low-pass filter with a slow LFO sweep (0.05–0.15 Hz) gives the characteristic
filter-breathing movement.

**Trance gate:** A 16-step binary pattern derived from a curated seed table is
applied rhythmically to the lead and pad voices, producing the pulsing gated
texture that defines the sound. The pattern changes on every phase transition.

**Kick:** Exponential sine sweep from ~160 Hz down to ~50 Hz with an
exponential amplitude envelope. No samples needed — this is standard programmatic
kick synthesis.

**Arp:** Single sawtooth with a short exponential decay. Intentionally brighter
(no LPF) to cut through the mix.

**Sidechain:** When the kick fires, the bass and pad volumes dip and recover
over ~8 steps (~0.5 seconds), producing the pumping compression effect. The
lead and arp are not sidechained so they always cut through.

### Composition

A Wolfram Rule 30 cellular automaton (32 cells wide, advancing one step per
16th note) drives the lead and arp gating — specific bit positions gate whether
a voice fires on a given step. This produces aperiodic rhythmic patterns that
feel composed rather than mechanical.

Note selection follows harmonic rules: the lead moves by conjunct motion (≤7
semitones between consecutive notes), phrase boundaries allow occasional leaps
resolved by contrary motion, and the arp cycles through chord tones across
multiple octaves in the direction set by the mood.

The arrangement state machine drives voice muting and gain ramps independently
of the CA, so the structure is always musically coherent even as the melodic
content varies.

---

## Terminal visualiser

One line is printed per bar:

```
[uplifting] [Bar   17] [Grv ] [A#m ] K:1 B:1 L:1 A:1 P:1 vol=0.30
[uplifting] [Bar   33] [Bkdn] [F#  ] K:0 B:0 L:1 A:1 P:1 vol=0.30
[uplifting] [Bar   49] [Bld ] [D   ] K:1 B:0 L:0 A:1 P:1 vol=0.30
[uplifting] [Bar   65] [Drop] [A#m ] K:1 B:1 L:1 A:1 P:1 vol=0.30
```

Fields: mood · bar number · phase code · current chord · voice active flags
(1 = active, 0 = muted) · master volume. Always fits in 80 columns.

---

## DJ integration

TranceStream implements the same flag-file IPC protocol as `ca_synth.py` and
`piano_stream.py`, so `stream_dj.py` can manage it in a crossfade playlist.

**Fade-in:** pass `--fade_in N` and the script ramps master volume from 0 to
full over N bars, matching the outgoing track's fade-out window.

**Fade-out:** the DJ writes `fade_<pid>.flag` in the working directory. The
script detects this on the next step, triggers a 4-bar fade-out, writes the
MIDI file if `--out_midi` is set, and exits cleanly.

To make `stream_dj.py` discover the script automatically, create a symlink:

```bash
ln -s trance_stream.py ca_synth_trance.py
```

The DJ globs `ca_synth*.py` in the working directory and picks the most
recently modified match.

---

## Diagnostic tools

Two scripts in `tools/` let you analyse a render without listening to it —
useful for catching synthesis bugs, level imbalances, and composition problems
before they reach the speaker.

```bash
# Render a clip offline (no audio hardware)
python trance_stream.py --bars 32 --wav /tmp/out.wav -o /tmp/out.mid -s center

# High-level audio + MIDI report
python tools/analyse_audio.py /tmp/out.wav /tmp/out.mid --seed center

# Bar-by-bar note dump (shows exactly what each voice is playing)
python tools/midi_forensic.py /tmp/out.mid --seed center --voice lead
```

`analyse_audio.py` reports spectral energy by frequency band, crest factor,
lead interval distribution, harmony violations, and voice density — and flags
problems automatically (e.g. bass too loud, lead notes too short for trance gate
to work with, notes outside the scale).

`midi_forensic.py` dumps every note event bar by bar with beat position, pitch,
duration, and an in-chord flag. Use it when `analyse_audio.py` identifies a
problem and you need to see the exact notes causing it.

See `tools/README.md` for full usage, flag reference, and the development
history of how these tools were used to diagnose and fix audio problems.

Additional dependencies for the tools:

```
pip install mido
```

---

## Dependencies

| Package | Purpose | Install |
|---------|---------|---------|
| `numpy` | Audio buffer arithmetic, oscillator accumulation | `pip install numpy` |
| `sounddevice` | Real-time stereo PCM output | `pip install sounddevice` |
| `MIDIUtil` | MIDI file construction | `pip install MIDIUtil` |

Python 3.10 or later required (uses `X | None` union syntax). No other
dependencies — stdlib only beyond the three above.

---

## Tuning parameters

Several synthesis constants are marked "tuned by ear" in the source. Their
starter values are reasonable but you may want to adjust them for your
monitoring setup:

| Constant | Default | What it controls |
|----------|---------|-----------------|
| `DETUNE_CENTS_LEAD` | 15 | Supersaw width on lead — higher = fatter/more chorus |
| `DETUNE_CENTS_BASS` | 8 | Supersaw width on bass — keep narrower than lead |
| `DETUNE_CENTS_PAD` | 20 | Supersaw width on pad — widest spread |
| `KICK_F0` | 160 Hz | Kick pitch sweep start — affects "click" attack |
| `KICK_F1` | 50 Hz | Kick pitch sweep end — affects sub thump |
| `KICK_ENV_TAU` | 0.025 s | Kick amplitude decay — lower = punchier |
| `SIDECHAIN_DEPTH` | 0.3 | How far bass/pad dip on kick (0 = no duck, 1 = silence) |
| `SIDECHAIN_RELEASE` | 8 steps | How many steps to recover from the dip |
| `DRIVE` | 1.5 | Soft-clip drive — higher = more saturation |

All constants are named at the top of the file in the
`# --- CONFIGURATION & TIME SCALING ---` section.

---

## Reference

The target sound is Switch Angel's live-coded trance work:
- `prebake.strudel` — `github.com/switchangel/strudel-scripts`
- "Coding Trance Music from Scratch" — `youtube.com/watch?v=iu5rnQkfO6M`

TranceStream does not depend on or copy from either source. The reference was
used to understand the target timbre and composition approach; all synthesis
and composition code is original.

---

## License

Mozilla Public License 2.0 — see the header of `trance_stream.py`.
