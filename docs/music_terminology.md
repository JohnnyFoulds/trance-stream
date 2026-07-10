# Music Terminology: Layman's Reference

**Project:** trance-stream / Switch Angel style  
**Audience:** Anyone working on this codebase — assume no prior music production knowledge.  
**Purpose:** Shared vocabulary so we can describe what we hear and mean the same thing.  
**How to use:** Look up a word here before asking "what do you mean by X" — and if a word is missing, ask and it gets added.

---

## 1. Rhythm and Time

### BPM — Beats Per Minute
How fast the music moves. 140 BPM means 140 beats happen every minute — roughly two every second. This project targets **140 BPM** (Switch Angel's confirmed tempo). Faster BPM = more energetic; trance typically lives between 128–145 BPM.

### Beat
The basic pulse of the music — the thing you tap your foot to. At 140 BPM, one beat = 60/140 ≈ 0.43 seconds. Everything in the project is timed in multiples or fractions of a beat.

### Bar (Measure)
A group of beats. In 4/4 time (the only time signature used here), one bar = **4 beats**. At 140 BPM, one bar = ~1.71 seconds. When we say "the chord changes every 4 bars," we mean it changes every 6.86 seconds.

### 4/4 Time
The universal trance time signature: four beats per bar, the quarter note gets one beat. Almost all dance music uses this. The "four on the floor" kick pattern is literally four kick drums, one on each beat of the bar.

### Downbeat
Beat 1 of a bar — the strongest, most accented beat. A kick on the downbeat is the most fundamental kick placement in trance.

### Subdivision
How a single beat is divided into smaller pieces:
- **Quarter note** — one full beat (the base unit in 4/4)
- **Eighth note** — half a beat; two per beat
- **16th note** — quarter of a beat; four per beat — the smallest timing unit we use for gates and arps
- **Triplet** — divides a beat into three equal parts instead of two (rarer in trance)

When we say "the arp plays on every 16th note," we mean it plays 16 times per bar.

### Phrase
A musical sentence — typically 4 or 8 bars. The arrangement state machine advances in phrases. A "4-bar phrase" at 140 BPM is ~6.86 seconds.

### Four-on-the-Floor
A kick drum pattern where the kick lands on every beat (beats 1, 2, 3, 4 of every bar). This is the defining rhythmic feature of trance and house. "The floor" refers to the bass speaker in a club.

### Groove / Swing
Micro-timing deviations that make rigid 16th-note grids feel more human. A perfectly on-grid pattern can feel stiff. Swing nudges every other 16th note slightly late. We don't use swing in this project — SA's code doesn't either.

---

## 2. Pitch and Harmony

### Pitch
How high or low a note sounds. Measured in Hz (cycles per second) or on the MIDI note scale (0–127). Higher Hz = higher pitch. A4 = 440 Hz = MIDI note 69.

### Note / Semitone
The keyboard has 12 distinct pitches before the pattern repeats one octave higher. Each step is one **semitone** (also called a **half step**). On a piano, the distance from any key to the immediately adjacent key (black or white) is one semitone.

### Octave
12 semitones — after which the pitch pattern repeats at double the frequency. A4 = 440 Hz; A5 = 880 Hz; A3 = 220 Hz. When we say a sound is "an octave too high," we mean its fundamental pitch is 12 semitones above where it should be.

### Root (Root Note)
The home note of a key — the pitch everything is built around. **This project is in G** (specifically G natural minor). G is the "home base" that chords and melodies orbit.

### Scale
A set of notes that sound good together within a key. Not all 12 semitones are used — a scale picks 7 of them. The intervals between chosen notes define the emotional character.

**Natural minor** (used here): intervals `[0, 2, 3, 5, 7, 8, 10]` semitones from root. In G: G–A–Bb–C–D–Eb–F. Sounds dark, dramatic, tense.

### Interval
The distance between two notes, measured in semitones.
- Unison = 0 (same note)
- Minor 3rd = 3 semitones (the interval that makes a chord sound minor/sad)
- Major 3rd = 4 semitones (makes a chord sound major/bright)
- Perfect 5th = 7 semitones (the "power chord" interval — stable, full)
- Octave = 12 semitones

### Chord
Three or more notes played simultaneously. The character of a chord depends on the intervals between its notes:
- **Minor chord** — root + minor 3rd (3 semitones) + perfect 5th (7 semitones). Sounds dark/emotional.
- **Major chord** — root + major 3rd (4 semitones) + perfect 5th (7 semitones). Sounds bright/resolved.

### Chord Progression
A sequence of chords played in order — the harmonic backbone of a piece. SA's progression is **C minor → D minor → Eb major → F major** (or in Strudel degree notation: 3 → 4 → 5 → 6).

### Scale Degree
The position of a note within the current scale, counted from the root. In G natural minor:
- Degree 0 = G (root)
- Degree 3 = C (4th degree)
- Degree 4 = D (5th degree)
- Degree 5 = Eb (6th degree, the bVI — the "lift" chord)
- Degree 6 = F (7th degree)

Strudel uses **0-indexed** degrees. When you see `n("3 4 5 6")` in SA's code, she means the 4th, 5th, 6th, 7th scale degrees.

### Roman Numerals (i, iv, bVI, bVII)
A shorthand for chord positions relative to the key, independent of which key you're in:
- **i** — chord built on the root. Minor in minor keys.
- **iv** — chord built on the 4th degree. Minor in natural minor.
- **v** — chord built on the 5th degree. Minor in natural minor (unlike classical harmony, no dominant tension).
- **bVI** — the "borrowed" major chord on the flattened 6th. This is the euphoric lift chord in trance.
- **bVII** — the major chord on the flattened 7th. Feels like momentum/forward motion.

The progression **iv → v → bVI → bVII** (C min → D min → Eb maj → F maj) is the most characteristic sound of this style.

### Register
How high or low the fundamental pitches sit overall. Not to be confused with brightness (which is about harmonics). A **low-register** pad plays its root notes in the bass octave (G1–G2). A **high-register** pad plays in the mid-range (G3–G4). SA's pad is very low — root at approximately G1 (~49 Hz). We measure register with **spectral centroid** (the average frequency of all energy in the signal).

### Transposition / Octave Shift
Moving all notes up or down by a fixed interval without changing the relationships between them. "Transpose down an octave" = subtract 12 from every MIDI note number. This affects register but not the harmonic content.

---

## 3. Synthesis and Sound Design

### Oscillator
The electronic circuit (or mathematical function) that generates a repeating waveform. All pitched sounds in this project start with oscillators. The shape of the waveform determines the timbre:
- **Sine** — pure, no harmonics. Sounds like a tuning fork.
- **Square** — hollow, reedy. Strong odd harmonics only.
- **Sawtooth (saw)** — bright, buzzy. All harmonics present. The fundamental waveform of trance leads and pads.
- **Triangle** — softer than square, more harmonics than sine.

### Harmonic / Harmonic Series
A sound is almost never a single frequency — it is a **fundamental** (the pitch you hear) plus **harmonics** at integer multiples of that frequency. For a G2 pad at 98 Hz, harmonics appear at 196 Hz, 294 Hz, 392 Hz, etc. The relative loudness of each harmonic determines **timbre** (the difference between a piano and a violin playing the same note).

### Filter (Low-Pass Filter / LPF)
A circuit that removes frequencies above a cutoff point. "Low-pass" means it passes low frequencies through and blocks high ones. The key parameters:
- **Cutoff frequency** — the frequency above which attenuation begins. Lower cutoff = darker sound.
- **Resonance** — a boost at the cutoff frequency. High resonance creates a "wah" or "screech" quality. In SA's `rlpf`, this is called Q.

Trance pads are heavily low-pass filtered — SA's cutoff maps to ~350–450 Hz, removing most of the sawtooth buzz.

### ADSR Envelope
How a sound changes in amplitude over time. Four stages:
- **Attack** — time from note-on to full volume (fast attack = click; slow = fade in)
- **Decay** — time from peak to the sustain level
- **Sustain** — the level held while the note is pressed (not a time, a level)
- **Release** — time from note-off to silence

The kick drum uses a very fast attack (~1 ms) and short release (~120 ms). The pad has a slow attack (~80 ms) to soften the onset.

### LFO — Low-Frequency Oscillator
An oscillator running too slow to be heard as a pitch (typically < 20 Hz). Instead of making sound directly, it modulates another parameter — volume, filter cutoff, pitch — creating tremolo, wah, or vibrato effects. The trancegate is essentially an LFO on the pad's volume.

### Amplitude / Volume / Gain
- **Amplitude** — the physical magnitude of the sound wave (how big the oscillations are).
- **Volume** — perceptual loudness (roughly logarithmic in relation to amplitude).
- **Gain** — a multiplier applied to the signal. Gain 1.0 = unchanged. Gain 0.5 = 6 dB quieter. Gain 2.0 = 6 dB louder.

When we say "the pad gain is 0.4," we mean the pad's amplitude is 40% of its maximum level.

### Detuning / Supersaw
A **supersaw** is multiple sawtooth oscillators playing slightly different pitches at the same time. The small pitch differences between them cause the waves to go in and out of phase, creating a thick, shimmering, chorus-like quality. This is the defining sound of trance leads and pads. The amount of pitch spread between oscillators is measured in **cents** (100 cents = 1 semitone).

### Reverb
Simulates the natural echo of a physical space. A room adds reflections of a sound that arrive microseconds to seconds after the direct signal. Trance pads use heavy reverb — the tail of each chord blurs into the next, creating a continuous wash. Key parameters:
- **Room size** — larger = longer tail
- **Wet/dry ratio** — how much reverb is added relative to the dry signal
- **Decay time (RT60)** — how long the reverb tail takes to drop by 60 dB

### Clipping / Distortion
When a signal's amplitude exceeds the maximum value the system can represent (0 dBFS for digital audio), it clips — the tops of the waveform are chopped flat, creating harsh harmonic distortion. We avoid this. If the total mix is too loud, all voices clip together and the output sounds crunchy.

### RMS
Root Mean Square — a measure of average signal power (roughly, perceived loudness). When testing whether a synth is actually producing sound, we measure RMS. An RMS of 0.0 means silence. A healthy synth voice should read > 0.001. We use this in all automated audio tests.

---

## 4. Trance-Specific Production

### Sidechain / Sidechain Compression / Pumping
The effect where the pad and bass "duck" (get quieter) each time the kick drum hits. A compressor is triggered by the kick signal and applied to the pad/bass, causing a rhythmic volume pump. This is the most recognizable sonic signature of trance and house music — that "breathing" quality where the pad seems to gasp in time with the kick. The depth of the effect is the **duck ratio**: SA's code uses `.duckdepth(.6)`, meaning the signal drops to ~40% of its normal level on each kick.

### Trancegate
A rhythmic gating effect specific to this genre. Unlike sidechain (which is kick-driven), the trancegate pulses the pad volume at a fixed rate set by a `speed` parameter — independent of the kick. It creates the "breathing" or "chopping" quality in the sustained chords. SA uses `.trancegate(1.5, 45, 1)` — speed=1.5 means ~1.5 volume cycles per bar. The shape of each cycle is a smooth cosine wave (not a hard on/off switch).

### Arpeggiator (Arp)
Plays the notes of a chord one at a time in sequence rather than all at once. Instead of a full C minor chord, an arp might play C → Eb → G → Eb → C ... in rapid succession. The **arp rate** determines how fast the notes cycle — typically locked to 16th notes in trance. **Direction** can be up, down, or alternating. SA's arp direction is controlled by the cellular automaton gate (`ARP_DIR_BIT`).

### Lead / Lead Synth
The main melodic voice — the part you could hum. Typically a heavily filtered supersaw or sync lead. Plays shorter, more rhythmic melodic phrases (not sustained chords like the pad). In the arrangement, the lead comes in during the Groove and Drop phases.

### Pad
A sustained, harmonically rich sound that fills the background. Pads are played in long notes (one chord per 4 bars is common) and are filtered dark to avoid clashing with the lead. SA's pad is a supersaw run through a very dark low-pass filter with a trancegate.

### Bass Line
The lowest voice — plays single notes (not chords) that reinforce the root of each chord. In trance the bass sits in the 40–100 Hz range, usually following the kick or playing a counterrhythm. SA's bass plays a "rolling" 16th-note pattern that alternates between the root and a note a fifth above.

### Kick
The bass drum. In trance it always plays four-on-the-floor (every beat). The TR-909 kick used here has a characteristic pitch sweep: the pitch starts high (~285 Hz) and falls to the sub-bass floor (~50 Hz) in ~31 ms — this sweep is what makes the kick "punchy." The kick triggers the sidechain compression.

### Four-on-the-Floor Kick
See the Rhythm section. The kick placement pattern that defines dance music: one hit per beat, all four beats per bar.

### Drop / Build / Breakdown
The emotional arc of a trance track:
- **Breakdown** — the quiet, emotional section. Kick drops out. Pads and reverb dominate. Builds anticipation.
- **Build-up** — energy and density increase toward the Drop. Snare roll, filter opens, everything gets louder.
- **Drop** — the moment of maximum energy. All voices return at full intensity. This is the emotional payoff the entire track has been building toward.

### Arrangement
The large-scale structure of the track — which voices play when and at what level. Our arrangement state machine cycles through: **Intro → Groove → Breakdown → Build-up → Drop** and loops. Each phase has different per-voice gain multipliers and filter settings.

### Supersaw Lead vs Pad
Both use supersaw oscillators but serve different roles:
- **Pad** — very dark filter (cutoff ~400 Hz), long attack, heavily reverbed, sustained for multiple bars. Background harmony.
- **Lead** — brighter filter (cutoff 1000–3000 Hz), shorter attack, more percussive, plays melodic figures. Foreground melody.

### Sideband / Phasing / Chorus
When two very similar frequencies are played together, they alternately reinforce and cancel each other as the phase relationship cycles. This creates a **beating** effect — periodic volume fluctuation at the rate equal to the frequency difference. Two oscillators 5 Hz apart beat 5 times per second. When this beating is fast and complex (many detuned oscillators), it produces the characteristic shimmer of a supersaw.

---

## 5. Quick-Reference Table

| Word | Plain meaning | Unit / range | Project value |
|---|---|---|---|
| BPM | Track speed | beats per minute | 140 |
| Bar | 4 beats | ~1.71 seconds at 140 BPM | — |
| Root | Home note of the key | — | G |
| Scale | Notes that fit the key | 7 of 12 semitones | G natural minor |
| Semitone | Smallest pitch step | — | — |
| Octave | 12 semitones (2× frequency) | — | — |
| Chord | 3+ simultaneous notes | — | C min → D min → Eb maj → F maj |
| Cutoff | Filter threshold | Hz | ~400 Hz (pad) |
| RMS | Average signal power | 0.0 (silence) – ~1.0 | >0.001 = sound |
| Gain | Volume multiplier | 0.0 (mute) – ~2.0 | varies per voice |
| Centroid | Average frequency of signal | Hz | SA pad ~129 Hz |
| Duck ratio | Sidechain pump depth | 0–1 (1 = 100% ducking) | SA = 0.60 |
| Detuning | Pitch spread between oscillators | cents (100 = 1 semitone) | varies |
| Arp | Chord notes played in sequence | — | 16th-note rate |
| Trancegate | Rhythmic volume pulse | cycles/bar | 1.5 |
| Downbeat | Beat 1 of a bar | — | kick placement |
