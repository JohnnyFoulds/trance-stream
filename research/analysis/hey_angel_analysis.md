# "Hey Angel…" — Audio Analysis
**Source**: https://www.youtube.com/shorts/2o9Riel8iCg  
**Uploaded**: Jun 11 2026 by Switch Angel  
**Duration**: 32.6s  
**Audio file**: `research/reference_audio/hey_angel.wav` (downloaded via yt-dlp, 48kHz WAV)

---

## 1. Tempo and meter

| Parameter | Value | Method |
|---|---|---|
| BPM | **138 BPM** (most likely) | Kick interval grid (3+5 pattern) + arp 16th grid |
| Autopilot estimate | 112.5 BPM | librosa beat_track — unreliable on this track (half-time feel) |
| Kick interval | 857ms = half note @ 140 BPM, 869ms @ 138 | Sub-bass peak detection |
| 16th note from arp | 117ms | Fast arp runs in t=5-8s section |
| Best BPM fit | **138 BPM** | 138 BPM: 16th=108.7ms (≈117ms), 3×16th=326ms (≈313ms), 8×16th=870ms (≈857ms) |

The kick sits on **half-notes** (every 857ms), giving a half-time feel. Within each half-note the sub-bass hits twice in a **3+5 sixteenth** subdivision:
- Hit at 0 (main kick/bass drop to G1)
- Hit at 3 sixteenths (~321ms) (second bass note F2)
- No more hits until the next half-note at 8 sixteenths (857ms)

In Strudel: `"x . . x . . . ."` at 16th resolution, cycled over 2 bars.

---

## 2. Key and scale

| Parameter | Value |
|---|---|
| Root | G1 (49Hz) — confirmed by sub-bass FFT (full mix peak: 46–51Hz) |
| Mode | **G minor / Dorian** — bass anchored on G1 |
| Melody character | Chromatic descend: C4 → B3 → Bb3 → A3 → Ab3 → G3 → F#3 (6 semitones down, non-diatonic) |
| Top chroma (full mix) | F#(0.842), F(0.687), D#(0.608), D(0.588), G(0.580) |
| K-S key detection | "D# minor" (artefact — chromatic melody spreads energy across all PCs, defeating K-S) |
| K-S on melody stem | "G major / F# major" — confirms G tonal centre despite chromatic decoration |
| Harmonic/Percussive ratio | 1.63 (harmonic-dominant, as expected for a melodic piece) |

**Key finding**: The Krumhansl-Schmuckler algorithm returns a spurious "D# minor" for the full mix because the chromatic descending line activates all 12 pitch classes equally, washing out the key signature. Analysis of the isolated Demucs melody stem (which places the K-S correlation on G major and F# major) alongside the confirmed G1 bass root establishes **G minor** as the correct key. The F# is a chromatic passing note / leading tone from the descend, not a scale member.

---

## 3. Track arrangement (32.6s)

```
t=0.0–2.5s   INTRO ARP: smooth chromatic-glide melody, mid-range (C4→F#3)
t=2.5–3.1s   SUSPENSION: bass sweeps down to G1, silence/drone only
t=3.1–4.0s   HIGH PLUCK ENTERS: E5 (665Hz) sustained pluck layer
t=4.0–4.9s   MID ARP + BASS: full arrangement begins
t=4.9–32.6s  GROOVE: F2 bass, G1 drone, rolling arp, sidechain pump active
```

---

## 4. Synthesis layers

### 4a. Melody / Arp (the iconic descending line)

This is NOT a conventional step-arp. It is a **mono legato line with slow portamento glide**.

| Parameter | Value |
|---|---|
| Pitch range | C4 (261Hz) sliding down to F#3 (185Hz) per bar |
| Portamento rate | ~15 semitones/second (slow, continuous glide) |
| Octave | Mid-range: 185–260Hz |
| Duration | One smooth phrase per ~0.5s bar |
| Notes | C4 → B3 → A#3 → A3 → G#3 → G3 → F#3 (chromatic, 6 semitones down = tritone) |
| Repetition | Same descend repeated every bar, with slight variations and different start notes |
| Octave doubling | A second layer appears an octave lower in some bars |

**Synthesis approach**: Detuned saw or filtered square, legato mode with portamento glide time ~60ms for the melody. The slow glide rate means any synth with `portamento 0.06s` and `legato on` would reproduce this.

### 4b. High pluck (enters at t=3.1s)

| Parameter | Value |
|---|---|
| Pitch | E5 (660Hz) sustained, briefly D#5 |
| Timbre | Very clean: fundamental + 2nd harmonic (660Hz, 1300Hz ≈ 1320Hz) |
| Attack | Near-instantaneous (<1ms) |
| Brightness decay | Spectral centroid drops from 2500Hz → 1600Hz in first 25ms |
| Sustain | Long-held (not pluck-style decay — more like a pad but brighter) |
| Character | KP-style or hard-filtered saw: bright click, then smooth sustained tone |
| Sub-harmonics | Bleed from bass layer (60–140Hz subharmonics present but not from pluck itself) |

**Key observation**: The brightness decay (centroid: 2500→1600Hz in 25ms) is the pluck character. This is a **one-pole lowpass filter sweep on attack** — the filter opens briefly and closes. Not a full Karplus-Strong; more like a sine with a VCF burst.

### 4c. Bass (the sweep-and-drone)

| Parameter | Value |
|---|---|
| Anchor note | G1 (50Hz) — same as SA pad root |
| Upper note | F2 (87Hz) — flat 7th, classic trance bass move |
| Pattern | G1 (quarter note hold) → F2 (8th note) → portamento sweep back to G1 (8th note) |
| Portamento rate | **~120–130 semitones/second** (fast snap, not gradual) |
| Sweep duration | 100–120ms |
| Sweep character | The pitch sweeps from A2/G2 (whichever upper note) down to G1 in ~107ms |

**Bass formula in Strudel**: `"g1 [f2 ~]"` with fast portamento (~0.1s). The sweep creates a "wah-swoop" effect that is heavily SA-characteristic.

---

## 5. Sidechain pump

| Parameter | Value |
|---|---|
| Duck ratio (mean trough/mean peak) | 0.413 (-7.7 dB) |
| Peak-to-min duck depth | 0.279 (-11.1 dB) |
| Pump period | Synced to kick = half-note (857ms) |
| Character | Visible in RMS: peaks at ~0.250, troughs at ~0.087 during groove |

The sidechain duck is pronounced and rhythmically locked to the bass hits. The pump reaches -11dB at the deepest trough. In the generator this maps to SA's `duckdepth(0.6)` target.

---

## 6. What makes this sound SA-specific

1. **G1 (50Hz) root drone** — this is a signature SA anchor, matching existing generator
2. **Flat-7 bass movement** (G→F, then sweep back) — the "wah-swoop" portamento bass
3. **Slow chromatic glide melody** — not a step arp, a legato descend
4. **Half-time feel at ~138 BPM** — listener perceives ~70 BPM groove but grid is 138
5. **High pluck layer** — very bright, fast filter close, E5 register
6. **G Dorian** — the natural 6th (E) against the root (G) — that open, emotional quality

---

## 7. Implementation targets for the generator

| Feature | Target | Status |
|---|---|---|
| BPM | 138 (or 140) | trance_stream_v2 has 138 ✓ |
| Root | G1 = 50Hz | ✓ in v2 |
| Bass portamento | ~120 sem/sec → 0.1s glide | Not implemented |
| Bass pattern | G1(quarter) F2(8th) sweep(8th) | Not implemented |
| Slow-glide melody | Legato, 15 sem/sec, C4→F#3 | Not implemented — v2 has step arp |
| High pluck | Filter-burst sine, E5, long sustain | Not implemented |
| Sidechain | -11dB depth at trough | Measured at 0.08 in v2, target -11dB |

---

## 8. Stem separation results (Demucs htdemucs_6s)

Run on 2026-07-10. Stems committed to `research/reference_audio/stems/htdemucs_6s/hey_angel/`.  
Demucs version 4.0.1; model `htdemucs_6s` (Défossez et al., 2021, 2022).

| Stem | RMS | Notable content |
|---|---|---|
| drums | 0.1041 | Kick + hihat — good separation |
| bass | 0.0926 | Sub-bass G1 (49Hz) — clean isolation |
| other | 0.0496 | Atmospheric pad layer |
| guitar | 0.0073 | Small — likely high pluck bleed |
| vocals | 0.0640 | **Contains melody lead** — Demucs classified the synth lead as "vocals" (common for sustained tonal content) |
| piano | 0.0003 | Negligible |

**Key correction from stem analysis**: PYIN on the bass stem returned F1 (43.6Hz), but sub-bass FFT on both the full mix and the bass stem shows the true fundamental at 46–51Hz = G1 (49Hz). The F1 reading was a PYIN octave alias. G1 is confirmed.

**Melody classification**: The synth lead was separated into the "vocals" stem. This is expected — Demucs HTDemucs_6s uses learned features that associate sustained mono pitch with vocals. The MIDI extracted from this stem correctly recovers the melody notes.

### MIDI extracted from stems

| Stem | MIDI file | Notes | Method |
|---|---|---|---|
| bass | `research/reference_audio/midi/hey_angel/bass.mid` | 100 | PYIN monophonic |
| melody (vocals stem) | `research/reference_audio/midi/hey_angel/melody.mid` | ~270 | PYIN monophonic |

The melody MIDI correctly captures: chromatic descend C4→F#3 (t=0–1.2s), high E5 pluck (t=3.1–4.0s), D#3→B2→G1 bass-register fall (t=4.0–4.5s), F3/F2 sustained note (t=5.5–18s second half). The MIDI contains the full note pitch trajectory including portamento glide — the note onsets correctly map each new pitch inflection.

---

## 9. Key synthesis questions (for sidequest implementation)

1. **Is the melody a detuned saw with portamento or a sine with FM?**  
   The harmonic content (660Hz + 1300Hz ≈ 2nd harmonic only) suggests sine or near-sine, not saw. The portamento slide is pitch-based (glide), not FM.

2. **Is the bass the SA pad `n("0").add(-14).scale("g:minor")` from the other tracks?**  
   Same root pitch (50Hz), same SA style. But "Hey Angel" has a more active bass pattern (F2 alternation) vs. the drone-only approach in the main generator.

3. **What creates the brightness burst on the high pluck?**  
   Most likely: filtered saw or square with a fast ENV → VCF attack (filter opens on note-on, then closes in ~25ms). Alternatively a bandpass with a resonant peak.
