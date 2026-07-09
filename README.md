# TranceStream

A procedural trance music generator in the style of Switch Angel's live-coded
Strudel sets. Streams stereo audio to your system output in real time, exports
WAV and MIDI, and is fully deterministic from a text seed.

All audio is synthesised from mathematics — no samples, no soundfonts, fully
DMCA-safe.

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

      --viz             Full-screen text visualiser while streaming.
                        Shows chord, filter arc, active tracks, trancegate phase,
                        and a Rule-30 cellular automaton animation.
                        Only valid with --stream.

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

v3 uses an **additive stage model** — voices enter one at a time and stay.
There is no breakdown or drop (this matches Switch Angel's live-coding
approach).

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
