# TranceStream

A procedural trance music generator in the style of Switch Angel's live-coded
Strudel sets. Streams stereo audio to your system output in real time, exports
WAV and MIDI, and is fully deterministic from a text seed.

All audio is synthesised from mathematics — no samples, no soundfonts, fully
DMCA-safe.

---

## Vision

**The ultimate goal is Death Angel** — a fully original AI live-coding trance entity with its own identity, style, and generative personality.

Switch Angel (SA) is the current focus because she provides a concrete, measurable target. Matching her sound precisely is the discipline that builds the full stack: synthesis, composition, arrangement, and style parameterisation. Once we can convincingly reproduce SA's output from first principles, everything needed to build something original is in place.

SA is the vehicle. Death Angel is the destination.

---

## Current goal (SA phase)

**Make a listener familiar with trance believe they are hearing Switch Angel playing live — without knowing the music is procedurally generated.**

The reference is Switch Angel (SA): a live-coder who builds trance tracks in real time using Strudel.cc. Her sound fingerprint has been reverse-engineered from OCR analysis of 311 code snapshots across 5 of her YouTube sessions. Every synthesis constant in this project traces back to a measurement from that source.

The target sound requires getting five things right simultaneously:

| Element | SA's approach | This project |
|---|---|---|
| **Pad** | 5-voice supersaw, very dark LP filter (~400 Hz), trancegate breathing, FDN reverb, sidechain pump | `instruments/pad.py` — full chain implemented |
| **Kick** | TR-909 style: 285→50 Hz pitch sweep, tau=31 ms, decay 120 ms | `instruments/drums.py` — confirmed constants |
| **Sidechain** | Pad/bass duck to ~40% on every kick; `.duckdepth(.6)` | `SIDECHAIN_DEPTH=0.6` in `song/theory.py` |
| **Trancegate** | Smooth cosine pulse, 1.5 cycles/bar | `synth/envelopes.py` |
| **Chord progression** | C min → D min → Eb maj → F maj (iv–v–bVI–bVII), 4 bars per chord, G natural minor at 140 BPM | `song/theory.py` — SA-confirmed values |

### What is done and what remains

The v3 architecture is structurally correct — all five voices exist, all SA-confirmed constants are in `song/theory.py`, and the arrangement arc (Intro → Groove → Breakdown → Build-up → Drop) is implemented. The remaining gap is **perceptual verification**: the output has not yet been measured against SA's reference for sidechain pump depth, trancegate shape, and filter floor. The constants are right; the measurements are missing.

See `CLAUDE.md` for the prioritised list of parameters still needing output-level verification.

---

## Quick start

```bash
pip install numpy scipy sounddevice mido
python trance_stream_v3.py --stream
```

Streams indefinitely until Ctrl-C. Add `--bars N` to stop after N bars.

---

## CLI reference

```
python trance_stream_v3.py [OPTIONS]

  -s, --seed SEED       Text seed for deterministic generation (default: sunrise)
                        Same seed + mood always produces the same track.

  -m, --mood MOOD       Harmonic character (default: uplifting)
                        uplifting | dark | acid | dreamy | progressive

      --bpm BPM         Tempo in BPM (default: 140)

      --bars N          Number of bars to generate (default: infinite when
                        streaming, 128 when rendering to file)

      --volume V        Master volume 0.0–1.0 (default: 1.0)

      --stream          Real-time bar-by-bar playback, runs forever. Ctrl-C to stop.

      --from-bar BAR    Skip silently to BAR before streaming or rendering.
                        All instrument state (oscillator phases, filter, sidechain,
                        chord progression) is advanced correctly. Instantaneous —
                        useful for jumping to a specific moment for diagnosis.

                        Examples:
                          --stream --from-bar 90          stream from bar 90
                          --stream --from-bar 45 --bars 12  hear the breakdown
                          --stream --from-bar 96 --solo lead  isolate lead at climax

      --viz             Full-screen text visualiser while streaming.
                        Shows chord, filter arc, active tracks, trancegate phase,
                        and a Rule-30 cellular automaton spacetime diagram.
                        Only valid with --stream.

      --ascii-video [PATH ...]
                        Load one or more pre-rendered ASCII video frame files and
                        use them as a colour overlay on the CA diagram. The CA
                        continues running; the video colours each cell. Press v
                        to cycle through the loaded videos and back to normal CA
                        colour mode.
                        If omitted, all ascii_videos/*.txt files are
                        auto-discovered (Bad Apple + Star Wars when both are
                        present). Only active with --stream --viz.

      --wav PATH        Write output to a WAV file (default when not streaming:
                        /tmp/trance_v3.wav)

  -o, --out-midi PATH   Write a MIDI file (default when not streaming:
                        /tmp/trance_v3.mid)

      --solo TRACK ...  Solo one or more tracks; all others are muted.
      --mute TRACK ...  Mute one or more tracks.

                        Track names: kick  pad  lead  bass  hihat  clap  pulse

      --analyse         Print spectral/MIDI analysis after rendering
      --spectrogram     Generate a spectrogram PNG after rendering
      --play            Play back the WAV after batch rendering
```

---

## Track isolation (solo / mute)

Standard DAW solo and mute for diagnosing what each element sounds like in
isolation. Useful when something sounds wrong and you want to identify which
track is responsible.

```bash
# Hear only the kick
python trance_stream_v3.py --stream --solo kick

# Hear only the lead synth
python trance_stream_v3.py --stream --solo lead

# Hear everything except the lead
python trance_stream_v3.py --stream --mute lead

# Pad + bass together — check harmonic content without rhythm
python trance_stream_v3.py --stream --solo pad bass

# Diagnose lead entering at bar 7 with no other distractions
python trance_stream_v3.py --stream --solo lead --bars 20
```

---

## Making tracks

The two main levers are `--mood` and `--seed`.

**`--mood`** sets the harmonic character: scale, chord progression, and BPM
range.

**`--seed`** is a free-text string. It derives the root key via MD5 hash
(deterministic but non-obvious), picks the chord progression variant, offsets
the arrangement stage timings, and controls lead character and arc shape.
Same seed + mood always gives the same track.

```bash
# Uplifting — euphoric arc, natural minor
python trance_stream_v3.py --stream --mood uplifting -s "sunrise"

# Dark — tension loop, slower BPM
python trance_stream_v3.py --stream --mood dark -s "midnight"

# Acid — hypnotic i → III → iv loop
python trance_stream_v3.py --stream --mood acid -s "303"

# Progressive — major scale, bright and groovy
python trance_stream_v3.py --stream --mood progressive -s "journey"

# Dreamy — dorian scale, bittersweet
python trance_stream_v3.py --stream --mood dreamy -s "velvet sphinx"
```

---

## Moods

| Mood | Scale | Chord roots | BPM range |
|------|-------|-------------|-----------|
| `uplifting` | Natural minor | i – VI – III – v | 138–142 |
| `dark` | Natural minor | i – iv – i – VII | 136–140 |
| `acid` | Natural minor | i – III – iv – III | 138–145 |
| `progressive` | Major | I – IV – V – ii | 128–138 |
| `dreamy` | Dorian | i – V – VI – III | 128–136 |

Each chord entry carries a root and a fifth so the lead notearp has two
distinct pitches to arpeggiate between.

---

## Arrangement

v3 uses an **additive stage model** — voices enter one at a time and then stay. The arrangement has three dynamic phases:

**Build (bars 0 → pullback−4):** voices enter one by one; master gain rises from 0.55 to 1.0, making each new entry feel bigger than the last. Once `pad_chord_on` is reached the pad switches from a sustained drone to 16 rhythmic filter stabs per bar (SA's `.seg 16` equivalent).

**Breakdown (4 bars before pullback):** bass, lead, hihat and clap all drop out simultaneously, leaving only kick + pad. The filter then dips to ~311 Hz over 8 bars — the darkest, most stripped-back moment in the song.

**Second half (after pullback):** all voices re-enter as the filter reopens toward 12 kHz. The chord progression shifts to `chord_prog_b` and the root may lift by +2 semitones (seed-determined). FM modulation and hi-hat enter in the final third.

Default stage positions (shifted ±4 bars per seed):

| Stage | Default bar | What happens |
|-------|-------------|--------------|
| kick_on | 0 | Kick drum — four-on-floor |
| pad_root_on | 2 | Pad enters on single root note |
| bass_on | 4 | Acid bass enters — rhythmic pattern from SA's bstruct |
| lead_root_on | 8 | Lead enters on single root note |
| lead_melody_on | 16 | Lead gets full notearp melody + delay |
| pad_chord_on | 20 | Pad gains moving chord + trancegate |
| lead_voicing_on | 32 | Lead gains bar-varying voicing shift |
| clap_on | 56 | Backbeat clap added |
| fm_on | 88 | FM modulation opens on lead |
| pulse_on | 100 | Pulse texture shimmer layer |
| hihat_on | 112 | Hi-hat added |
| kick_syncopated | 116 | Kick upgrades to beat(0,4,8,11,14) |

---

## Synthesis

| Voice | Signal chain |
|-------|-------------|
| **Kick** | Sine sweep + noise transient, tail bleeds into next bar |
| **Pad** | 5-voice supersaw → LP swell (lpenv) → trancegate (1.5×, depth 0.7, breathes 0.3–1.0) → FDN reverb → sidechain; plays in C4 register |
| **Bass** | Sawtooth → acidenv LP sweep → LPF; 5–7 spaced hits per bar with clear gaps |
| **Lead** | 3-voice supersaw + FM → acidenv LP sweep → trancegate → ping-pong delay; plays in C5 register, one octave above pad |
| **Hi-hat** | White noise → HPF → exponential decay; tri-LFO varies decay |
| **Clap** | Filtered noise burst, backbeat (steps 4, 12) |
| **Pulse** | Pulse oscillator × 16 triggers per bar, FM-modulated by time |

All oscillators maintain phase continuity across bar boundaries. Kick tails
overflow into the next bar. Trancegate phase is anchored to absolute session
time so instruments entering mid-song breathe in sync with the kick.
Sidechain uses a stateful IIR follower so ducking recovers smoothly across bars.

Stream uses a dedicated render thread feeding a queue so the audio thread
never stalls between bars.

---

## Visualiser

```bash
python trance_stream_v3.py --stream --viz --seed dawn --mood uplifting
```

### ASCII video overlay

The CA diagram has a second display mode where pre-rendered ASCII video files
are used as a colour overlay. The CA keeps scrolling and driving the music;
the video frame at each moment determines the colour of each cell.

Two built-in assets are available — download them once:

```bash
# Bad Apple (6,572 frames, 30 fps, 60×32)
python tools/fetch_bad_apple.py

# Star Wars asciimation (15,973 frames, 15 fps, 67×13)
python tools/fetch_starwars.py
```

Once the frame files are in `tools/`, run `--viz` and they are auto-discovered:

```bash
python trance_stream_v3.py --stream --viz
```

Press **`v`** while streaming to cycle through the videos:
`[normal CA colours]` → `[Bad Apple]` → `[Star Wars]` → `[normal CA colours]` → …

Load specific files or a custom set:

```bash
# One file only
python trance_stream_v3.py --stream --viz --ascii-video ascii_videos/bad_apple_frames.txt

# Explicit playlist
python trance_stream_v3.py --stream --viz --ascii-video ascii_videos/bad_apple_frames.txt ascii_videos/starwars_15fps_frames.txt
```

The overlay uses cover scaling: the video always fills the entire CA area with
no letterbox bars. The video is center-cropped to fit the terminal shape.
Playback is wall-clock synced at the video's native frame rate, advancing
smoothly on every sixteenth-note tick regardless of BPM.

Any conforming frame file works — the format is one frame per line with rows
separated by literal `\n` (the backslashxx/bad-apple-ascii format). The frame
rate is parsed from the filename pattern `*_Nfps_*`; defaults to 30 if absent.

Renders a full-screen text display that updates once per bar. Layout
adapts to terminal width: wide (≥ 100 cols) shows full labels and timing
stats; narrow (< 100 cols) uses compact abbreviations.

### UI panels

| Panel | What it shows |
|-------|--------------|
| Header | Seed, mood, BPM |
| Info row | Bar number, current chord name, filter cutoff in Hz, FM depth % |
| Track row | Seven track indicators that flicker in sync with actual hits (see below) |
| Filter bar | Cyan filled bar tracking the cutoff arc from ~850 Hz to ~12 kHz |
| Gate bar | `●` cursor showing the trancegate position within the current bar cycle |
| CA diagram | Rule-30 cellular automaton spacetime history (see below) |
| Timing row | Render time, bar budget, headroom in ms (wide layout only) |

### Track indicators

Each bar is delivered as 16 sixteenth-note chunks. The indicator line updates on every chunk, flashing in sync with what the listener actually hears.

Percussive voices (kick, bass, hihat, clap) go fully dark between hits — you can read the rhythm pattern directly from the display. Sustained voices (pad, lead, pulse) stay dim `●` while active to show they are droning, flashing bright on each retrigger.

| State | Meaning |
|-------|---------|
| Bold bright `●` | Instrument firing this sixteenth note |
| Dim `●` | Active but not firing (sustained voice) |
| `○` | Between hits (percussive voice) or not yet in the arrangement |

### CA diagram — reading the colours

The automaton section fills all available terminal rows and uses the full
width (one character per cell). Each bar appends a new row at the bottom;
older rows scroll up. Two musical properties are encoded in the colour:

**Hue = chord.** Each of the four chords in the progression has its own
colour. Reading horizontal bands in the history shows the harmonic cycle:

| Colour | Chord index | Role in progression |
|--------|-------------|---------------------|
| Cyan   | 0 | Tonic — home, stable |
| Green  | 1 | First movement away from tonic |
| Yellow | 2 | Tension chord |
| Magenta | 3 | Release / turnaround |

A colour change in the diagram means a chord change in the music. Wide
bands = that chord holds for several bars; narrow bands = quick movement.

**Brightness = filter arc / session energy.** The filter cutoff opens
gradually over the session, driving the characteristic trance energy build:

| Brightness | Filter slider | Filter Hz | Session phase |
|------------|--------------|-----------|---------------|
| Dim | < 0.5 | < ~2985 Hz | Early, closed |
| Normal | 0.5 – 0.7 | ~2985 – 5096 Hz | Mid session |
| Bold | > 0.7 | > ~5096 Hz | Late, open |

There is a deliberate dim dip around bar 64 (the pullback moment), then
rows go bold and stay bold once the filter fully opens around bar 96.
Reading the diagram top-to-bottom is reading the harmonic and energy
history of the entire stream.

**"Rule 30"** appears as a dim overlay on the rightmost edge of the newest
row — ambient metadata, not part of the pattern.

### CA → sound (the loop is closed)

The automaton does not just visualise the music — it drives three sound parameters each bar:

| CA property | Sound parameter | Effect |
|-------------|----------------|--------|
| Two centre bits → index into `(0, 2, 5, 7)` | Lead voicing offset (semitones) | Melody shifts register each bar — SA's `.add "<5 4 0 <0 2>>"` equivalent |
| Cell density (fraction of live cells) | Lead delay wet `0.25–0.85` | Dense rows = washed/spacious; sparse rows = dry/tight |
| Cell density > 0.55 | Bass step pattern | Busier pattern when CA is active; sparser when quiet |

Musical events inject bits back into the CA: chord changes force bit 0 to 1; FM onset forces the centre bit; every 4-bar phrase boundary toggles a near-centre bit. This creates a feedback loop where harmony drives pattern which drives timbre which drives variation.

---

## Exporting

```bash
# Render 128 bars to WAV only (no audio hardware needed)
python trance_stream_v3.py --bars 128 --wav out.wav -s "sunrise"

# Stream forever and write WAV simultaneously (Ctrl-C to stop and finalise)
python trance_stream_v3.py --stream --wav out.wav -s "sunrise"

# Write MIDI
python trance_stream_v3.py --bars 64 --wav out.wav -o out.mid -s "sunrise"
```

WAV and stream output are sample-identical (same seed, same path, same result).

---

## Diagnostic tools

```bash
# Spectral report
python tools/analyse_audio.py /tmp/trance_v3.wav

# Spectrogram image
python tools/spectrogram.py /tmp/trance_v3.wav --out /tmp/spec.png
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `numpy` | Audio buffer arithmetic |
| `scipy` | Filters (`lfilter`), stateful IIR |
| `sounddevice` | Real-time stereo PCM output |
| `mido` | MIDI file construction |

```bash
pip install numpy scipy sounddevice mido
```

Python 3.10 or later required.

---

## Research

Built from 311 OCR'd code snapshots across 5 of Switch Angel's YouTube
live-coding sessions. See `research/analysis/switch_angel_vocabulary.md`
for the full synthesis parameter reference.

TranceStream does not copy or depend on her code. The research was used to
understand the target synthesis chain; all code is original.

---

## License

Mozilla Public License 2.0.
