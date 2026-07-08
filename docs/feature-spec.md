# TranceStream

## Changelog

| Date | Change | Triggered by |
| --- | --- | --- |
| 2026-07-08 | Initial draft — full spec through §3 | Session 1 |
| 2026-07-08 | Fix 10 pre-implementation issues: (1) replace pre-computed supersaw waveforms with step-rendered oscillator state model to enable LFO modulation; (2) add `lead_tgate_pattern`/`pad_tgate_pattern` to EngineState; (3) reconcile kick Intro behaviour across FR-13/§2.4/§2.8; (4) specify sidechain fires only when kick gain > 0; (5) add `TGATE_RAMP_MS` to §3.4; (6) fix PAD_HIGH note label; (7) add chord voicing table to §2.3; (8) remove undeclared Outro references; (9) add `apply_tgate` ramp inference note; (10) fix visualiser line width | Session 2 |
| 2026-07-08 | Fix 5 remaining issues: (1) fix `render_supersaw_step` buffer shape to `(samples_per_step,)` not `(N,1)`; (2) clarify `PAD_GATE` as on/off enable matching LEAD_GATE semantics; (3) add `ActiveNote` dataclass to §3.5 to define note accumulator structure; (4) extend FR-19 to include pad voice filter LFO; (5) fix ADR-T-0001 kick sweep description from linear to exponential | Session 2 |
| 2026-07-08 | Fix 3 blocking issues (fourth review pass): (1) rename `KICK_DECAY_MS` → `KICK_DECAY_S` throughout to match §2.5 pseudocode and `synthesise_kick` docstring; (2) add `samples_per_step: int` to `synthesise_arp()` signature — required to allocate output arrays; (3) sync `TGATE_SEEDS` in ADR-T-0002 to 16 entries matching §2.9 | Session 4 |
| 2026-07-08 | Fix 6 pre-implementation issues (fifth review pass): (1) add per-voice gain scalars (`kick_gain`, `bass_gain`, `lead_gain`, `arp_gain`, `pad_gain`) and `transition_step` to `EngineState` — required for phase gain ramps; (2) add `lead_leap_pending: bool` to `EngineState` — required for contrary-motion resolution after phrase-boundary leaps; (3) add `master_volume_current`, `fade_out_step`, `noise_riser_amplitude` to `EngineState` — required for fade-in/out and Build-up riser; (4) remove `PAD_GATE` CA bit — pad is chord-boundary triggered, not step-gated, to avoid oscillator retrigger phase discontinuities; (5) add `ArpNote` dataclass to §3.5 — defines pre-computed arp buffer storage model separate from `ActiveNote`; (6) add TGATE_SEEDS audition note to §2.9 — LFSR output must be verified by ear before listener test | Session 5 |
| 2026-07-08 | Fix 4 issues (third review pass): (1) add `synthesise_arp()` signature to §3.5 and `# --- SYNTHESIS: ARP ---` to §3.3 — arp was specified musically but had no synthesis contract; (2) clarify bass/pad note duration to `CHORD_DURATION_BARS * STEPS_PER_BAR` steps, fixing ambiguous "pad bass notes" phrasing; (3) correct §2.3 chord example to use transposed-down roots so all tones are within BASS register; (4) add explicit note in §2.5 that `render_supersaw_step` returns two 1D arrays not one 2D array; add `ARP_DECAY_TAU` constant to §3.4 | Session 3 |
| 2026-07-08 | Fix 4 further issues: (1) replace single `filter_lfo_phase` with `lead_lfo_phase`/`bass_lfo_phase`/`pad_lfo_phase` in EngineState, §2.10, §2.15, and ADR-T-0002 — single accumulator cannot serve three different LFO rates; (2) add Build-up kick gain 0.5 to §2.4 to match §2.8 table; (3) tighten gate ramp description from "1–3ms" to "2ms (`TGATE_RAMP_MS`)"; (4) add tgate pattern refresh and LFO advance to `advance_engine` docstring | Session 2 |

---

## 1. Requirements

### 1.1 Business / Product Requirements

| ID | Requirement |
| --- | --- |
| BR-1 | The script must produce music that sounds like a Switch Angel live-coded trance set to a listener familiar with the genre — not a generic synthesiser approximation — without the listener knowing it is procedurally generated. |
| BR-2 | The music must be DMCA-safe: generated entirely from mathematics with no sampled or pre-recorded audio. |
| BR-3 | The music must be suitable as stream background music for a live-coding session: driving but non-irritating, continuously evolving, and listenable for at least 30 minutes without fatigue. |
| BR-4 | The script must export standard MIDI files usable in any DAW or downstream tool without post-processing. |
| BR-5 | The script must be compatible with `stream_dj.py` crossfade infrastructure so it can participate in a multi-genre DJ playlist alongside `ca_synth.py` and `piano_stream.py`. |
| BR-6 | The reference for the target sound is Switch Angel's `prebake.strudel` (github.com/switchangel/strudel-scripts) and her "Coding Trance Music from Scratch" video (youtube.com/watch?v=iu5rnQkfO6M). The script must reproduce the core timbral and structural elements of that reference without copying code. |

### 1.2 Functional Requirements

| ID | Requirement |
| --- | --- |
| FR-1 | The script SHALL synthesise trance audio in real time and stream it to the default audio output device in stereo. |
| FR-2 | The script SHALL generate music that never exactly repeats, driven by a deterministic seed so the same seed always produces the same output. |
| FR-3 | The script SHALL support a `--mood` parameter selecting the harmonic character of the music from a fixed set of named moods, each defining a chord progression, bass pattern, and arp direction. |
| FR-4 | The script SHALL support a `--bpm` parameter controlling the tempo in beats per minute (valid range 120–150). |
| FR-5 | The script SHALL support a `--seed` parameter accepting a text string that deterministically initialises the generative engine. |
| FR-6 | The script SHALL support a `--volume` parameter controlling the master output level (0.0 to 1.0). |
| FR-7 | The script SHALL support a `--bars` parameter. When N > 0, after N bars the script triggers the standard 4-bar fade-out, then exits and saves the MIDI file if `--out_midi` is set. When `--bars` is 0 the script runs indefinitely. |
| FR-8 | The script SHALL support a `--out_midi` parameter specifying a file path to which a MIDI file is written on exit. |
| FR-9 | The script SHALL support a `--fade_in` parameter specifying the number of bars over which master volume fades from 0 to full on startup, for use by the DJ crossfade system. |
| FR-10 | The script SHALL respond to a `fade_<pid>.flag` file written by the DJ script by triggering a graceful fade-out and clean exit, compatible with `stream_dj.py` IPC protocol. |
| FR-11 | The script SHALL display a terminal visualiser once per bar showing the current phase, chord, active voices, bar number, and master volume. Output per step would flood the terminal; bar-level granularity is sufficient. |
| FR-12 | The script SHALL generate five voices: kick, bass, lead, arp, and pad, each synthesised independently and mixed into a single stereo audio stream. |
| FR-13 | The kick voice SHALL fire on every beat (four-on-the-floor) in Groove, Build-up (half-time), and Drop phases. In Breakdown the kick is fully muted (gain = 0). In Intro the kick fires at reduced gain (0.4) through a low-pass filter. |
| FR-14 | The bass voice SHALL place at least one note per bar on the downbeat (beat 1) in a register at least one octave below the lead voice. The bass is muted in Breakdown and Build-up phases. |
| FR-15 | The lead voice SHALL move predominantly by conjunct motion: consecutive notes no more than `MAX_LEAD_INTERVAL` semitones apart. Larger leaps up to one octave are permitted at phrase boundaries only and must be resolved by stepwise contrary motion on the following note. |
| FR-16 | The arrangement SHALL cycle automatically through phases: Intro → Groove → Breakdown → Build-up → Drop, repeating from Groove. Each phase lasts `PHASE_BARS` bars. Voice activity per phase is defined in ADR-T-0002. |
| FR-17 | The lead and pad voices SHALL have a trance gate applied: a rhythmic binary amplitude pattern (16 steps) that produces the characteristic pulsing, gated texture of Switch Angel's trance gate effect. The gate pattern is selected deterministically from a curated seed table. |
| FR-18 | The script SHALL apply sidechain ducking to the bass and pad voices: when the kick fires, the bass and pad volumes dip and recover over `SIDECHAIN_RELEASE` steps, producing the pumping effect characteristic of trance production. |
| FR-19 | The script SHALL apply a filter LFO to the lead, bass, and pad voices: a slow (0.1–0.5 Hz) sine wave modulates the IIR low-pass filter cutoff, producing the sweeping filter movement heard in Switch Angel's sets. |
| FR-20 | The script SHALL apply dynamic velocity variation: individual notes vary in velocity to avoid a mechanical, uniform sound. |
| FR-21 | The MIDI export SHALL assign General MIDI program 80 (Synth Lead, Square) to the lead channel, program 38 (Synth Bass, Finger) to the bass channel, and program 89 (Pad 2, Warm) to the pad channel, via program-change messages at beat 0. |
| FR-22 | The MIDI export SHALL use note velocity values derived from the musical engine on every note event. |
| FR-23 | The MIDI export SHALL emit clean note-off messages so notes do not hang when imported into a DAW. |

### 1.3 Non-Functional Requirements

| ID | Requirement |
| --- | --- |
| NFR-1 | The script must run on Python 3.10 or later with no dependencies beyond `numpy`, `sounddevice`, and `midiutil`. |
| NFR-2 | Audio output latency must not cause audible glitches on a modern laptop under normal load. Per-step audio buffers must be written synchronously (blocking write), matching the approach in `ca_synth.py`. |
| NFR-3 | The script must accept the same `--fade_in` / flag-file IPC protocol as `ca_synth.py` and `piano_stream.py` so that `stream_dj.py` can manage it without modification. |
| NFR-4 | CPU usage during normal playback must not prevent the host machine from running a coding session and screen-capture simultaneously. Five voices at N=7 oscillators each at 44,100 Hz must not exceed 30% CPU on a modern laptop. |
| NFR-5 | The MIDI export must be importable into GarageBand, Ableton Live, and standard MIDI sequencers without errors. |
| NFR-6 | The script must produce a terminal visualiser output that is legible at 80 columns. |
| NFR-7 | The trance synthesis must produce recognisable trance timbres: a supersaw lead with audible detuning width, a punchy kick with sub thump, and a pulsing trance gate texture — not a bland sine-wave approximation. |

### 1.4 Constraints and Assumptions

- The script targets a single output file: `trance_stream.py` (in your project directory of choice).
- The DJ compatibility constraint (NFR-3) is non-negotiable: the flag-file IPC and `--fade_in` argument must work exactly as in `ca_synth.py`.
- **Synthesis approach:** SuperpySaw (N=7 detuned sawtooth oscillators) + sine-sweep kick — see [ADR-T-0001](decisions/ADR-T-0001-synthesis-approach.md).
- **Composition model:** CA-gated rule-based hybrid with arrangement state machine — see [ADR-T-0002](decisions/ADR-T-0002-composition-model.md).
- **Audio output:** Stereo PCM via sounddevice — see [ADR-T-0003](decisions/ADR-T-0003-audio-output.md).
- **MIDI target:** General MIDI (standard DAW import).
- **Python standards:** PEP 8, 80-character line limit, type hints on all function signatures, Sphinx/RST docstrings on all public functions.
- **License:** MPL 2.0 header on the source file.
- The script must not depend on Switch Angel's `prebake.strudel` or Strudel.cc at runtime. It is a Python script, not a Strudel script. The prebake is used as a reference for the sound and composition approach, not as a dependency.

---

## 2. Functional Specification

### 2.1 Overview

`trance_stream.py` is a self-contained procedural trance music generator. It runs
indefinitely (or for a fixed number of bars) generating music in the style of
Switch Angel's live-coded trance sets, streaming stereo audio to the system output
device in real time and optionally writing a MIDI file on exit.

```text
trance_stream.py
├── Generative engine                ← drives all musical decisions each step
│     ├── Harmonic framework         ← chord progression, bar/beat/step clock
│     ├── Arrangement state machine  ← Intro/Groove/Breakdown/Build-up/Drop
│     ├── Kick voice                 ← four-on-the-floor, sidechain trigger
│     ├── Bass voice                 ← rolling supersaw bass, mood pattern
│     ├── Lead voice                 ← CA-gated stepwise melody, trance gate
│     ├── Arp voice                  ← CA-gated cycling arpeggio
│     └── Pad voice                  ← sustained chord cluster, trance gate
│
├── Synthesis engine                 ← converts note events to audio waveforms
│     ├── SuperpySaw synthesiser     ← N detuned sawtooth oscillators + IIR LPF
│     ├── Kick synthesiser           ← sine sweep + exponential envelope
│     ├── Trance gate                ← 16-step binary pattern per voice
│     ├── Sidechain envelope         ← kick-triggered gain dip on bass/pad
│     └── Mixer / limiter            ← sums voices stereo, soft-clips, master vol
│
├── MIDI recorder                    ← records note events in parallel with audio
│
└── Output layer
      ├── Audio stream               ← sounddevice.OutputStream, stereo, blocking
      ├── MIDI file                  ← midiutil.MIDIFile, written on exit
      └── Terminal visualiser        ← phase / chord / voice / state display per bar
```

The generative engine produces musical events (note-on, note-off, velocity,
sidechain trigger) each step. The synthesis engine converts those events to stereo
audio. The MIDI recorder captures the same events independently. The audio and
MIDI paths are decoupled — synthesis improvements do not affect MIDI, and MIDI
feature additions do not affect audio.

**No Strudel, no samples.** The synthesis engine computes all audio from scratch
using sawtooth oscillator accumulation (supersaw) and a sine-sweep kick. There
is no soundfont, no sample library, and no Strudel runtime. The reference
(`prebake.strudel`) is used to understand the target sound — it is not imported.

### 2.2 Time Model

The time model follows `ca_synth.py` exactly.

```
Bar
└── beats_per_bar (4 for 4/4 time)
      └── steps_per_beat (4 — 16th note resolution)
            └── STEP_DURATION = (60.0 / bpm) * 0.25  seconds
                └── samples_per_step = int(44100 * STEP_DURATION)
```

One step is one 16th note. One bar is 16 steps. At 140 BPM (the default),
one step = 107ms, one bar = 1.71s.

Harmonic rhythm: one chord per `CHORD_DURATION_BARS` bars (default 4). At 140 BPM
and 16-bar cycle length, the full progression repeats every 27.4 seconds.

Phase duration: each arrangement phase lasts `PHASE_BARS` bars (default 16).
One full cycle (Intro + 4 repeating phases) is Intro(16) + Groove(16) +
Breakdown(16) + Buildup(16) + Drop(16) = 80 bars = ~137 seconds at 140 BPM.
After the first cycle, Intro is skipped and the four-phase loop repeats.

### 2.3 Harmonic Framework

The harmonic framework defines chord progressions available via `--mood`.
Each mood defines: a 4-chord progression, a bass pattern, and an arp direction.

Root note derived from seed:
```python
root = 48 + (int(hashlib.md5(seed.encode()).hexdigest(), 16) % 12)
```

`CHORD_DURATION_BARS = 4`. Chord progression cycles every 16 bars (4 chords × 4
bars each).

**Mood definitions** (decided in ADR-T-0002):

| Mood | Character | Progression | Bass pattern | Arp |
| --- | --- | --- | --- | --- |
| `uplifting` | Euphoric, soaring | i → VI → III → VII | Rolling 16ths | Up |
| `dark` | Intense, driving | i → iv → v → i | Off-beat | Up-down |
| `acid` | Hypnotic, TB-303 | i → VII → VI → VII | TB-303 pattern | Up |
| `progressive` | Groovy, slower | i → iv → I → VII | Broken octave | Down |
| `ambient` | Open, floating | Imaj7 → VIImaj7 → VImaj7 → VIImaj7 | Whole-bar sustain | Up |

Default mood: `uplifting`.

**Chord construction.** Each chord is built from intervals above the chord's root note:

| Quality | Intervals from chord root (semitones) |
| --- | --- |
| Minor triad | [0, 3, 7] |
| Major triad | [0, 4, 7] |
| Minor 7th | [0, 3, 7, 10] |
| Major 7th | [0, 4, 7, 11] |

**Scale-degree roots** (semitones above the scale root):

| Degree | +semitones |
| --- | --- |
| i / I | 0 |
| III / bIII | 3 |
| iv / IV | 5 |
| v / V | 7 |
| VI / bVI | 8 |
| VII / bVII | 10 |

**Example** (scale root = A2, MIDI 45, after octave-down transposition to keep tones ≤ BASS_HIGH=60):

| Chord | Degree | Chord-root MIDI | Quality | MIDI tones (bass register) |
| --- | --- | --- | --- | --- |
| Am | i | 45 | minor | [45, 48, 52] |
| C | III | 48 | major | [48, 52, 55] |
| Dm | iv | 50 | minor | [50, 53, 57] |
| Em | v | 52 | minor | [52, 55, 59] |
| F | VI | 53 | major | [53, 57, 60] |
| G | VII | 55 | major | [55, 59, 62→50] |

Note: the last chord (G) has a fifth (MIDI 62) above BASS_HIGH=60 — this tone is
transposed down an octave to 50 so all bass tones remain within [BASS_LOW, BASS_HIGH].

The implementation algorithm is: build the chord tones, then for any tone > BASS_HIGH
subtract 12 until it is within range. The lead and arp pool then re-adds +12/+24 to
place the same chord tones in [LEAD_LOW, LEAD_HIGH] = [60, 84].

All chord voicings use MIDI note numbers in the bass register. The lead and arp
voices derive their note choices from the same chord, transposed up to
`[LEAD_LOW, LEAD_HIGH]`.

### 2.4 Voice Architecture

Five independent voices, each with its own register, synthesis method, and
CA gate.

#### Kick

- Register: no pitch variation — fixed sine sweep from `KICK_F0` to `KICK_F1`
- Role: rhythmic foundation, four-on-the-floor (fires every 4 steps)
- Gate: full gain in Groove/Drop; half-time (every 8 steps) at gain 0.5 in Build-up;
  filtered at gain 0.4 in Intro; fully muted (gain=0) in Breakdown (FR-13)
- Sidechain: every kick trigger resets the sidechain envelope for bass and pad.
  In Breakdown (kick gain = 0) no sidechain trigger fires, so bass and pad
  sustain without pumping.

#### Bass

- Register: MIDI 36–60 (C2–C4), `[BASS_LOW, BASS_HIGH]`
- Role: harmonic root, rhythmic drive
- Synthesis: supersaw (`SAW_COUNT_BASS = 3`, narrower spread than lead)
- Filter: IIR LPF with slow LFO modulation (`BASS_LFO_RATE`)
- Gate: beat 1 unconditional; other steps follow mood-specific bass pattern
- Sidechain: gain is ducked when kick fires, recovers over `SIDECHAIN_RELEASE` steps
- Active in: Groove, Drop (muted in Intro, Breakdown, Build-up)

#### Lead

- Register: MIDI 60–84 (C4–C6), `[LEAD_LOW, LEAD_HIGH]`
- Role: primary melodic line, trance lead sound
- Synthesis: supersaw (`SAW_COUNT_LEAD = 7`, wide spread)
- Filter: IIR LPF with filter LFO modulation (`LEAD_LFO_RATE`)
- Gate: CA bit `LEAD_GATE`; step probability `REST_PROBABILITY = 0.15`
- Trance gate: 16-step binary pattern from curated seed table
- Motion constraint: max `MAX_LEAD_INTERVAL` semitones between consecutive notes;
  leaps up to 12 semitones at phrase boundaries, resolved by contrary stepwise motion
- Active in: Groove, Breakdown (filtered), Drop

#### Arp

- Register: MIDI 60–96 (C4–C7), `[ARP_LOW, ARP_HIGH]`
- Role: rhythmic harmonic decoration
- Synthesis: single sawtooth with short decay (no IIR LPF — brighter than lead)
- Gate: CA bit `ARP_GATE`; fires more densely than lead (lower rest probability)
- Direction: up / down / up-down per mood; reverses at phrase boundaries
- Active in: Groove, Breakdown, Build-up, Drop (muted in Intro)

#### Pad

- Register: MIDI 48–72 (C3–C5), `[PAD_LOW, PAD_HIGH]` — full chord sustained
- Role: harmonic texture, atmospheric body
- Synthesis: supersaw (`SAW_COUNT_PAD = 7`, widest spread, slow attack envelope)
- Trance gate: 16-step binary pattern (different seed from lead)
- Sidechain: gain is ducked when kick fires
- Active in: all phases; fully present in Groove and Drop, filtered in others

### 2.5 Synthesis Methods

See ADR-T-0001 for full rationale. Summary:

#### SuperpySaw

For bass, lead, and pad voices. Each note spawns `SAW_COUNT_VOICE` sawtooth
oscillators, detuned symmetrically by `DETUNE_CENTS_VOICE`. The oscillators
accumulate phase per sample; output is the normalised sum.

A first-order IIR low-pass filter is applied to the summed output:
```python
y = (1 - a) * y_prev + a * x
```
where `a` is derived from the target cutoff frequency `f_c`:
```python
a = (2 * math.pi * f_c) / (2 * math.pi * f_c + SAMPLE_RATE)
```
`f_c` is modulated each step by the filter LFO (FR-19).

**Stereo width:** oscillators are panned across the stereo field. For `SAW_COUNT = 7`,
oscillator k is panned to `pan_k = (k / (SAW_COUNT - 1)) * 2 - 1` (range −1 to +1).
Left channel receives `cos((pan_k + 1) * π/4)` of oscillator k; right channel
receives `sin((pan_k + 1) * π/4)`.

**Note accumulator (live oscillator state model):** Notes do not pre-compute their
full waveform. Instead, `init_supersaw()` returns the initial oscillator state:
`(osc_phases, iir_L, iir_R, gain)` where `osc_phases` is a `(SAW_COUNT,)` float32
array of per-oscillator phase accumulators. Each step, `render_supersaw_step()`
advances these phases by `samples_per_step` samples, applies the IIR LPF at the
**current step's LFO cutoff**, and returns a `(samples_per_step, 2)` stereo buffer.

This model allows the filter LFO to modulate the cutoff continuously across the
note's lifetime — a cutoff change takes effect at the next render call without
any discontinuity in the filter state (`iir_L`, `iir_R` are carried between calls).
Pre-computing the full waveform at note-on time (as in an offline renderer) would
lock the cutoff to its value at note onset and make FR-19 unimplementable.

`render_supersaw_step()` returns two separate `(samples_per_step,)` 1D float32
arrays — one per channel — not a single `(samples_per_step, 2)` interleaved array.

#### Kick

Sine sweep from `KICK_F0` (160 Hz) to `KICK_F1` (50 Hz) over `KICK_DECAY_S`
seconds, with exponential volume envelope. The kick is always centre (L=R).

```python
for i in range(kick_samples):
    t = i / SAMPLE_RATE
    freq = KICK_F0 * (KICK_F1 / KICK_F0) ** (t / KICK_DECAY_S)
    phase += freq / SAMPLE_RATE
    amp = math.exp(-t / KICK_ENV_TAU)
    sample = math.sin(2 * math.pi * phase) * amp
```

`KICK_F0`, `KICK_F1`, `KICK_DECAY_S`, `KICK_ENV_TAU` are tuned by ear during
implementation.

#### Trance gate

Applied to lead and pad voices after the IIR filter and before the sidechain.
A 16-step binary pattern (one entry per 16th note step in the bar) determines
whether each step's output is passed through or attenuated to near-silence.

The pattern is generated from a curated seed (FR-17). On each phase transition,
a new seed is selected from `TGATE_SEEDS` using the seeded RNG.

Gate attack and release are 2ms (`TGATE_RAMP_MS`) to avoid clicks while preserving
the rhythmic punch. Implemented as a per-sample linear ramp on the gate state.

#### Sidechain

A scalar `sidechain_env` in `[0.0, 1.0]` is maintained in `EngineState`. When
the kick fires, `sidechain_env` is set to `SIDECHAIN_DEPTH` (e.g. 0.3, meaning
volume drops to 30%). Each subsequent step, `sidechain_env` increases by
`1.0 / SIDECHAIN_RELEASE` until it returns to 1.0.

The bass and pad voice gains are multiplied by `sidechain_env` before the final
mix. The lead and arp voices are not sidechained (they should cut through the mix).

**Sidechain trigger rule:** the sidechain trigger fires if and only if the kick
gain scalar for the current phase is > 0 (i.e. the kick is not fully muted).
In Breakdown (kick gain = 0 per §2.8), no sidechain trigger occurs. In Intro
(kick gain = 0.4), the sidechain trigger does fire at the normal beat positions,
producing a subtle pump even through the filtered kick.

### 2.6 Mixer and Output

All active voice waveforms are summed each step to produce a stereo buffer.
A soft-clip limiter is applied before writing:

```python
mixed = np.tanh(mixed * drive) / drive  # applied independently to L and R
```

Master volume (`--volume`) is applied after the limiter. Fade-in and fade-out
envelope is applied after master volume.

Output: `sounddevice.OutputStream` at 44,100 Hz, 2 channels, float32.
Each write is exactly `(samples_per_step, 2)` samples.

Mono fallback: if `sounddevice` reports `max_output_channels < 2`, fall back to
mono (sum L+R, divide by 2) with a one-line warning to stderr.

### 2.7 MIDI Export

The MIDI file records all note events from all five voices in parallel with audio.

#### Channel assignments

| Channel | Voice | GM Program |
| --- | --- | --- |
| 0 | Lead | 80 — Synth Lead (Square) |
| 1 | Arp | 80 — Synth Lead (Square) |
| 2 | Bass | 38 — Synth Bass (Finger) |
| 3 | Pad | 89 — Pad 2 (Warm) |
| 4 | Kick | 116 — Taiko Drum (GM percussion channel workaround) |

#### Note events

Every note-on fired in the audio engine is written to the MIDI file:
- `beat_time = step * STEP_BEATS` where `STEP_BEATS = 0.25`
- Duration: one step for kick, arp, and lead; `CHORD_DURATION_BARS * STEPS_PER_BAR` steps for bass and pad (sustained harmonic texture)
- Velocity: from the musical engine (FR-22)

#### MIDI file write

Written on: clean `--bars` exit, Ctrl+C, or DJ fade-out completion.
Not written on abnormal exit (crash).

### 2.8 Arrangement State Machine

The arrangement cycles through phases automatically. Each phase is
`PHASE_BARS` bars long (default 16). Voice gain scalars (0.0–1.0) are
ramped over `PHASE_TRANSITION_BARS` bars (default 2) at each phase boundary.

```text
Intro (once) → Groove → Breakdown → Build-up → Drop → Groove → …
```

| Phase | Kick gain | Bass gain | Lead gain | Arp gain | Pad gain | Noise |
| --- | --- | --- | --- | --- | --- | --- |
| Intro | 0.4 (LPF) | 0.0 | 0.0 | 0.0 | 0.6 (heavy LPF) | no |
| Groove | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | no |
| Breakdown | 0.0 | 0.0 | 0.7 (heavy delay) | 1.0 | 1.0 | no |
| Build-up | 0.5 (half-time) | 0.0 | 0.0 | 1.0 | 1.0 | yes |
| Drop | 1.0 | 1.0 | 1.0 | 1.0 | 1.0 | no |

**Noise riser** (Build-up only): a white noise burst with exponential amplitude
increase over `PHASE_BARS - 4` bars, peaking 4 bars before the Drop. Implemented
as a separate noise accumulator with a per-step amplitude increment.

**Half-time kick** (Build-up): the kick fires every 8 steps instead of every 4,
building tension before the Drop returns to four-on-the-floor.

### 2.9 Trance Gate Implementation

The trance gate is applied to lead and pad voices. The gate pattern is a 16-entry
list of `{0, 1}` values (one per 16th note step in the bar). A `1` means the voice
passes through; a `0` means the voice is attenuated by `TGATE_ATTENUATION` (e.g.
0.05, close to but not fully silent — same behaviour as Switch Angel's `clip(.7)` on
the gated structure).

The pattern is generated from a seed value via a simple LFSR (linear feedback
shift register), matching the seeded-random approach of Switch Angel's `tgate`
function:

```python
def tgate_pattern(seed: int, length: int = 16) -> list[int]:
    state = seed % (2**16)
    pattern = []
    for _ in range(length):
        bit = (state ^ (state >> 1)) & 1
        pattern.append(bit)
        state = (state >> 1) | (bit << 15)
    return pattern
```

Curated seeds that produce musical patterns (ported from Switch Angel's lookup
table):

```python
TGATE_SEEDS = [45, 116, 99, 100, 107, 53, 57, 58, 67, 81, 89, 115, 8, 118, 120, 149]
```

On each phase transition, a new seed is drawn from `TGATE_SEEDS` via the seeded
RNG, independently for lead and pad (two draws).

**Implementation note:** The LFSR applied to these seeds will generate different
patterns than Switch Angel's original Strudel lookup table (which stores fully
pre-computed patterns). The LFSR output for each seed must be auditioned early in
the implementation pass — any seed that produces an all-0 run (silence) or all-1
run (ungated drone) should be replaced with a nearby integer that yields a more
rhythmically varied pattern. The starter values are derived from her documented
seed table and are expected to be musical, but this must be confirmed by ear
before T-002 (listener genre-identification test) can pass.

### 2.10 Filter LFO

A slow sine LFO modulates the IIR low-pass filter cutoff on lead, bass, and pad
voices (FR-19). Each voice has an independent phase accumulator advanced each step
at its own rate:

```python
state.lead_lfo_phase = (state.lead_lfo_phase + LEAD_LFO_RATE / steps_per_second) % 1.0
state.bass_lfo_phase = (state.bass_lfo_phase + BASS_LFO_RATE / steps_per_second) % 1.0
state.pad_lfo_phase  = (state.pad_lfo_phase  + PAD_LFO_RATE  / steps_per_second) % 1.0

# where steps_per_second = SAMPLE_RATE / samples_per_step
# cutoff per voice, e.g. lead:
cutoff = LEAD_CUTOFF_BASE + LEAD_CUTOFF_SWEEP * math.sin(2 * math.pi * state.lead_lfo_phase)
```

Per-voice constants:

| Voice | `CUTOFF_BASE` | `CUTOFF_SWEEP` | `LFO_RATE` |
| --- | --- | --- | --- |
| Lead | 2000 Hz | 1500 Hz | 0.15 Hz |
| Bass | 800 Hz | 400 Hz | 0.08 Hz |
| Pad | 600 Hz | 300 Hz | 0.05 Hz |

All values are initial defaults; tuned by ear during implementation.

### 2.11 DJ Compatibility and IPC

Identical to `piano_stream.py` §2.8. The flag-file IPC and `--fade_in` argument
are inherited unchanged from `ca_synth.py`.

**DJ discovery:** `trance_stream.py` does not match the `ca_synth*.py` glob.
Symlink as `ca_synth_trance.py` or extend the DJ with a `--synth` argument.
(Deferred.)

### 2.12 Terminal Visualiser

One line printed per bar:

```
[<mood>] [Bar <N>] [<ph>] [<chord>] K:<k> B:<b> L:<l> A:<a> P:<p> vol=<v>
```

Phase codes (4 chars, fixed width):

| Phase | Code |
| --- | --- |
| Intro | `Intr` |
| Groove | `Grv ` |
| Breakdown | `Bkdn` |
| Build-up | `Bld ` |
| Drop | `Drop` |

Examples:
```
[uplifting] [Bar  32] [Drop] [Am  ] K:1 B:1 L:1 A:1 P:1 vol=1.00
[progressive] [Bar  16] [Bkdn] [Dm  ] K:0 B:0 L:1 A:1 P:1 vol=0.82
```

Fields:
- `mood` — active mood, variable width (longest: `progressive` = 11 chars)
- `Bar N` — current bar, right-aligned in 4 digits
- `ph` — 4-char phase code (see table above)
- `chord` — current chord name, fixed width 4 + 2 brackets
- `K/B/L/A/P` — voice active (1) or muted (0) this bar
- `vol` — current master volume (4 chars: `0.00`–`1.00`)

Width check (worst case `progressive` mood, bar ≥ 1000):
```
[progressive] [Bar 1000] [Bkdn] [Dm  ] K:0 B:0 L:1 A:1 P:1 vol=0.82
```
= 69 characters — fits within 80 columns (NFR-6).

### 2.13 Error Behaviour

| Condition | Behaviour |
| --- | --- |
| `--volume` outside [0.0, 1.0] | Exit with `ValueError` |
| `--bpm` outside [120, 150] | Exit with `ValueError` |
| `--bars` < 0 | Exit with `ValueError` |
| `--mood` not in known mood list | Exit with `ValueError`, list valid moods |
| `sounddevice.OutputStream` fails to open | Print error to stderr, exit code 1 |
| `max_output_channels < 2` | Warn to stderr, fall back to mono |
| `--out_midi` path not writable | Warn to stderr; continue playing; MIDI not written on exit |
| Ctrl+C | Stop audio cleanly; write MIDI if `--out_midi` set; exit code 0 |
| Synthesis produces NaN or Inf | Replace with silence; warn to stderr once |

### 2.14 Velocity Model

Same three-layer model as `piano_stream.py`, adapted for trance:

```python
v_struct = {0: 95, 4: 80, 8: 80, 12: 80}.get(step_in_bar, 65)  # beat accent
v_phrase = int(15 * (step_in_phrase / max(phrase_length - 1, 1)))
           if midi_note >= phrase_high_note else 0              # phrase shape
v_noise  = rng.randint(-8, 8)                                   # organic variation
velocity = clamp(v_struct + v_phrase + v_noise, VELOCITY_MIN, VELOCITY_MAX)
```

Trance velocities are slightly higher than piano (beat 1 gets 95 vs. 90) to
reflect the genre's more assertive dynamic character.

Kick velocity is fixed at `KICK_VELOCITY = 100` — the kick is always at near-
maximum volume. Arp velocity follows a separate, simpler model: fixed 70 + noise.

### 2.15 Generative Engine Architecture

Identical in structure to `piano_stream.py` §2.12 — a deterministic recurrent
state machine, with the same CA/rule/LSTM analogy, same three-timescale architecture
(step / bar / phrase), and same soft phrase reset (`phrase_high_note // 2` decay).

Extensions over the piano model:

1. **Arrangement state** (`phase`, `phase_bar`) — two additional fields in
   `EngineState` that track the current arrangement phase and bar count within it.
2. **Arp state** (`prev_arp_index`, `arp_direction`) — the arp voice requires
   its own index and direction, independent of the lead voice state.
3. **Sidechain envelope** (`sidechain_env`) — a scalar tracking the current
   sidechain compression gain.
4. **Filter LFO phases** (`lead_lfo_phase`, `bass_lfo_phase`, `pad_lfo_phase`) —
   three independent scalars, one per filtered voice, each advancing at its own
   `LFO_RATE` each step (§2.10).

Four CA gate bits are named:
- `LEAD_GATE` — lead note fires this step
- `ARP_GATE` — arp note fires this step; `ARP_REST_PROBABILITY` is a secondary check applied when this bit is 1
- `PHRASE_BIT` — phrase boundary signal (guarded by `MIN_PHRASE_BARS`)
- `ARP_DIR_BIT` — arp direction reversal signal (guarded by phrase boundary)

The kick, bass downbeat, and pad are unconditional and require no CA gate. The pad
voice fires once per chord change (every `CHORD_DURATION_BARS * STEPS_PER_BAR` steps)
and sustains for that full duration; CA-gating would retrigger oscillators each step
and cause phase discontinuities in the sustained chord cluster. Rhythmic texture on
the pad is handled entirely by the trance gate (§2.9).

---

## 3. Technical Specification

### 3.1 File and Directory Layout

```text
trance_stream.py             ← the complete script (single file)
docs/
  feature-spec.md            ← this document
  decisions/
    ADR-T-0001-synthesis-approach.md
    ADR-T-0002-composition-model.md
    ADR-T-0003-audio-output.md
tests/
  manual-acceptance-tests.md
```

### 3.2 CLI Interface

```python
parser = argparse.ArgumentParser(description="🎛️ Procedural Trance Stream")
parser.add_argument('-m', '--mood',     type=str,   default='uplifting',
    choices=['uplifting', 'dark', 'acid', 'progressive', 'ambient'],
    help="Harmonic mood / chord progression")
parser.add_argument('-b', '--bpm',      type=int,   default=140,
    help="Tempo in BPM (120–150)")
parser.add_argument('-s', '--seed',     type=str,   default='center',
    help="Text seed for deterministic generation")
parser.add_argument('-v', '--volume',   type=float, default=0.15,
    help="Master volume (0.0–1.0)")
parser.add_argument('--fade_in',        type=int,   default=0,
    help="Fade in over N bars (used by DJ script)")
parser.add_argument('-o', '--out_midi', type=str,   default=None,
    help="MIDI output file path")
parser.add_argument('--bars',           type=int,   default=0,
    help="Stop after N bars (0 = infinite)")
```

No `--rule` argument — the CA rule is an internal constant. No `--genre`
argument — this script is trance only.

### 3.3 Module Structure

Single file, organised with `# ---` dividers:

```
# --- CLI ARGUMENT PARSER ---
# --- CONFIGURATION & TIME SCALING ---
# --- MUSIC THEORY: MOODS & CHORDS ---
# --- GENERATIVE ENGINE ---          (CA-gated rule-based hybrid; ADR-T-0002)
# --- SYNTHESIS: SUPERSAW ---        (N detuned sawtooth oscillators; ADR-T-0001)
# --- SYNTHESIS: ARP ---             (single sawtooth, exponential decay)
# --- SYNTHESIS: KICK ---            (sine sweep + envelope; ADR-T-0001)
# --- SYNTHESIS: TRANCE GATE ---     (16-step binary pattern from seed)
# --- SYNTHESIS: SIDECHAIN ---       (kick-triggered gain envelope)
# --- SYNTHESIS: FILTER LFO ---      (slow sine LFO for cutoff modulation)
# --- NOTE ACCUMULATOR ---           (active note buffer, stereo)
# --- MIXER ---                      (stereo sum, soft-clip, master vol)
# --- VELOCITY MODEL ---
# --- MIDI RECORDER ---
# --- TERMINAL VISUALISER ---
# --- MAIN LOOP ---
```

### 3.4 Key Constants

| Constant | Value | Notes |
| --- | --- | --- |
| `SAMPLE_RATE` | `44100` | Hz |
| `STEP_BEATS` | `0.25` | One 16th note |
| `STEPS_PER_BAR` | `16` | 4/4, 16th note resolution |
| `BASS_LOW` | `36` | C2 MIDI |
| `BASS_HIGH` | `60` | C4 MIDI |
| `LEAD_LOW` | `60` | C4 MIDI |
| `LEAD_HIGH` | `84` | C6 MIDI |
| `ARP_LOW` | `60` | C4 MIDI |
| `ARP_HIGH` | `96` | C7 MIDI |
| `PAD_LOW` | `48` | C3 MIDI |
| `PAD_HIGH` | `72` | C5 MIDI |
| `MAX_LEAD_INTERVAL` | `7` | Max semitone step in lead melody |
| `VELOCITY_MIN` | `20` | MIDI velocity floor |
| `VELOCITY_MAX` | `115` | MIDI velocity ceiling |
| `CHORD_DURATION_BARS` | `4` | Bars per chord |
| `PHASE_BARS` | `16` | Bars per arrangement phase |
| `PHASE_TRANSITION_BARS` | `2` | Bars for voice gain ramp at phase boundary |
| `CA_WIDTH` | `32` | CA row width |
| `MIN_PHRASE_BARS` | `4` | Minimum bars before phrase boundary can fire |
| `PHRASE_SHORT` | `64` | Short phrase in steps (4 bars) |
| `PHRASE_LONG` | `128` | Long phrase in steps (8 bars) |
| `REST_PROBABILITY` | `0.15` | Lead melody rest probability per step |
| `ARP_REST_PROBABILITY` | `0.10` | Arp rest probability per step |
| `BAR_DIRECTION_DESCENT_THRESHOLD` | `5` | Semitones before downward bias |
| `BAR_SPARSE_THRESHOLD` | `2` | Notes below which rest is suppressed |
| `FADE_OUT_BARS` | `4` | DJ crossfade fade-out duration |
| `SAW_COUNT_LEAD` | `7` | Oscillators per lead note |
| `SAW_COUNT_BASS` | `3` | Oscillators per bass note |
| `SAW_COUNT_PAD` | `7` | Oscillators per pad note |
| `DETUNE_CENTS_LEAD` | tuned by ear | Cents spread across SAW_COUNT_LEAD oscillators |
| `DETUNE_CENTS_BASS` | tuned by ear | Narrower than lead |
| `DETUNE_CENTS_PAD` | tuned by ear | Widest spread |
| `KICK_F0` | tuned by ear | Kick start frequency (Hz), ~160 |
| `KICK_F1` | tuned by ear | Kick end frequency (Hz), ~50 |
| `KICK_DECAY_S` | tuned by ear | Kick pitch-drop duration in seconds (~0.07) |
| `KICK_ENV_TAU` | tuned by ear | Kick amplitude decay time constant (seconds) |
| `KICK_VELOCITY` | `100` | Fixed kick MIDI velocity |
| `ARP_DECAY_TAU` | tuned by ear | Arp amplitude decay time constant (seconds), ~0.08 |
| `SIDECHAIN_DEPTH` | tuned by ear | Post-kick gain floor (~0.3) |
| `SIDECHAIN_RELEASE` | tuned by ear | Steps to recover to full gain (~8 steps) |
| `TGATE_SEEDS` | see §2.9 | Curated list of 16 gate pattern seeds |
| `TGATE_ATTENUATION` | `0.05` | Gate-closed amplitude (near-silence) |
| `TGATE_RAMP_MS` | `2` | Gate open/close transition ramp duration (ms) |
| `drive` | tuned by ear | Soft-clip drive constant |

### 3.5 Function Signatures

```python
# --- GENERATIVE ENGINE ---

def initialise_engine(seed: str) -> EngineState:
    """
    Initialise the generative engine state from a text seed.

    Seeds the CA row and EngineState.rng from seed so that all subsequent
    output is deterministic (FR-2). All counters and envelope states are
    set to their start-of-run values.

    :param seed: Text seed string from --seed CLI argument.
    :returns:    Fully initialised EngineState ready for the main loop.
    """

def advance_engine(state: EngineState) -> EngineState:
    """
    Advance the generative engine by one step and return the new state.

    Applies the Wolfram CA rule to state.ca_row. Increments step, phrase_step,
    phase_bar. Fires phrase boundary if PHRASE_BIT and MIN_PHRASE_BARS
    conditions are met. Resets bar_note_count and bar_net_direction at step 0
    of each bar. Advances arrangement phase when phase_bar reaches PHASE_BARS;
    on phase transitions, draws new tgate seeds from state.rng and updates
    lead_tgate_pattern and pad_tgate_pattern. Advances lead_lfo_phase,
    bass_lfo_phase, and pad_lfo_phase independently at their per-voice rates.
    Recovers sidechain_env toward 1.0.

    :param state: Current engine state.
    :returns:     New engine state with all fields updated.
    """

def select_lead_note(
    state: EngineState,
    chord: list[int],
    step_in_bar: int,
) -> int | None:
    """
    Select the lead note for the current step.

    Reads LEAD_GATE from state.ca_row. If open, chooses a chord tone within
    MAX_LEAD_INTERVAL semitones of state.prev_lead_note. At phrase boundaries,
    a leap up to one octave is allowed; the following call must return a note
    in the opposite direction by step. Returns None for rests.

    :param state:       Current engine state.
    :param chord:       MIDI note numbers of the current chord.
    :param step_in_bar: 0-based step index within the bar (0–15).
    :returns:           MIDI note in [LEAD_LOW, LEAD_HIGH], or None.
    """

def select_arp_note(
    state: EngineState,
    chord: list[int],
    step_in_bar: int,
) -> int | None:
    """
    Select the arp note for the current step.

    Reads ARP_GATE from state.ca_row. If open, advances state.prev_arp_index
    in state.arp_direction, wrapping through the chord pool (chord tones plus
    two octave transpositions within [ARP_LOW, ARP_HIGH]). Direction reverses
    at phrase boundaries (ARP_DIR_BIT) and when the arp index reaches the
    top or bottom of the pool. Returns None for rests.

    :param state:       Current engine state.
    :param chord:       MIDI note numbers of the current chord.
    :param step_in_bar: 0-based step index within the bar (0–15).
    :returns:           MIDI note in [ARP_LOW, ARP_HIGH], or None.
    """

def select_bass_notes(
    state: EngineState,
    chord: list[int],
    step_in_bar: int,
    pattern: str,
) -> list[int]:
    """
    Select bass notes for the current step.

    Beat 1 (step_in_bar == 0) always returns the root note (FR-14).
    Other steps follow the mood-specific bass pattern. All returned notes
    are within [BASS_LOW, BASS_HIGH].

    :param state:       Current engine state.
    :param chord:       MIDI note numbers of the current chord.
    :param step_in_bar: 0-based step index within the bar (0–15).
    :param pattern:     Bass pattern name (e.g. 'rolling', 'offbeat', 'tb303').
    :returns:           List of MIDI note numbers; may be empty on rests.
    """

# --- SYNTHESIS: SUPERSAW ---

def init_supersaw(
    midi_note: int,
    velocity: float,
    saw_count: int,
    detune_cents: float,
) -> tuple[np.ndarray, float, float, float]:
    """
    Initialise a supersaw note: return live oscillator state for step-by-step
    rendering. Does NOT pre-compute the waveform.

    :param midi_note:    MIDI note number (21–108).
    :param velocity:     Normalised amplitude (0.0–1.0); stored as gain.
    :param saw_count:    Number of sawtooth oscillators (SAW_COUNT_LEAD etc.).
    :param detune_cents: Total detuning spread in cents across all oscillators.
    :returns:            Tuple of (osc_phases, iir_L, iir_R, gain) where
                         osc_phases is a (saw_count,) float32 array of initial
                         phase accumulators (initialised to 0.0), iir_L and
                         iir_R are the IIR filter states for left and right
                         channels (initialised to 0.0), and gain is velocity.
    """

def render_supersaw_step(
    osc_phases: np.ndarray,
    iir_L: float,
    iir_R: float,
    gain: float,
    midi_note: int,
    saw_count: int,
    detune_cents: float,
    cutoff_hz: float,
    samples_per_step: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, float, float]:
    """
    Render one step (samples_per_step samples) of a supersaw note, advancing
    the oscillator phases and IIR filter state.

    The IIR filter cutoff is taken as-is from cutoff_hz — the caller is
    responsible for computing the current LFO-modulated cutoff before calling.
    The filter state (iir_L, iir_R) is carried in and out to avoid
    discontinuities at step boundaries.

    :param osc_phases:      (saw_count,) float32 array of current phase
                            accumulators; mutated in-place and returned.
    :param iir_L:           Current IIR filter state for left channel.
    :param iir_R:           Current IIR filter state for right channel.
    :param gain:            Amplitude scalar (0.0–1.0).
    :param midi_note:       MIDI note number (21–108).
    :param saw_count:       Number of sawtooth oscillators.
    :param detune_cents:    Total detuning spread in cents.
    :param cutoff_hz:       IIR LPF cutoff for this step (LFO-modulated by caller).
    :param samples_per_step: Number of samples to render.
    :returns:               Tuple of (buffer_L, buffer_R, osc_phases, iir_L, iir_R)
                            where buffer_L and buffer_R are (samples_per_step,)
                            float32 arrays, and osc_phases/iir_L/iir_R are the
                            updated state for the next render call.
    """

def synthesise_arp(
    midi_note: int,
    velocity: float,
    duration_steps: int,
    samples_per_step: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Synthesise one arp note: a single sawtooth oscillator with exponential
    amplitude decay. No IIR filter — the arp is intentionally brighter than
    the lead (§2.4). Pre-computes the full waveform at note-on time (the
    arp decays to silence, so no LFO modulation is needed after note-on).

    Stereo position: centre (L = R). The arp's brightness differentiates it
    from the stereo-spread lead without needing panning.

    :param midi_note:        MIDI note number (21–108).
    :param velocity:         Normalised amplitude (0.0–1.0).
    :param duration_steps:   Note length in steps.
    :param samples_per_step: Samples per 16th-note step (derived from --bpm).
    :returns:                Tuple of (left_wave, right_wave) float32 arrays,
                             each of length duration_steps * samples_per_step.
    """

def synthesise_kick(rng: random.Random) -> tuple[np.ndarray, np.ndarray]:
    """
    Synthesise one kick drum hit: sine sweep with exponential envelope.

    Returns centre-panned stereo arrays (left == right). Length is
    int(SAMPLE_RATE * KICK_DECAY_S * 3) to allow tail decay beyond the
    pitch sweep.

    :param rng: Seeded RNG from EngineState (reserved for future variation).
    :returns:   Tuple of (left_wave, right_wave) float32 numpy arrays.
    """

# --- SYNTHESIS: TRANCE GATE ---

def tgate_pattern(seed: int, length: int = 16) -> list[int]:
    """
    Generate a 16-step binary gate pattern from an integer seed using an LFSR.

    :param seed:   Integer seed (from TGATE_SEEDS).
    :param length: Pattern length in steps (default 16).
    :returns:      List of 0/1 integers, length = length.
    """

def apply_tgate(
    buffer_l: np.ndarray,
    buffer_r: np.ndarray,
    pattern: list[int],
    step_in_bar: int,
    samples_per_step: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Apply a trance gate pattern to a stereo buffer.

    The gate opens or closes at the boundary of each step. Brief attack/
    release ramps (TGATE_RAMP_MS) prevent clicks. The ramp direction for the
    current step is determined by comparing pattern[(step_in_bar - 1) % 16]
    (previous step's gate state) with pattern[step_in_bar] (current step).
    No explicit prev_gate_state parameter is required — it is inferred from
    the pattern itself.

    :param buffer_l:        Left channel float32 array of length samples_per_step.
    :param buffer_r:        Right channel float32 array of length samples_per_step.
    :param pattern:         16-step binary gate pattern from tgate_pattern().
    :param step_in_bar:     Current step index (0–15) for indexing pattern.
    :param samples_per_step: Number of samples in this step buffer.
    :returns:               Tuple of (gated_left, gated_right).
    """

# --- SYNTHESIS: SIDECHAIN ---

def apply_sidechain(
    buffer_l: np.ndarray,
    buffer_r: np.ndarray,
    sidechain_env: float,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Apply sidechain gain to a stereo buffer.

    Multiplies the buffer by sidechain_env (scalar 0.0–1.0). The ramp
    within a step is linear from sidechain_env at step start to the
    value it will reach by step end (callers should use advance_engine()
    to get the updated sidechain_env after the step).

    :param buffer_l:     Left channel float32 array.
    :param buffer_r:     Right channel float32 array.
    :param sidechain_env: Current sidechain envelope scalar.
    :returns:            Tuple of (ducked_left, ducked_right).
    """

# --- VELOCITY MODEL ---

def compute_velocity(
    step_in_bar: int,
    step_in_phrase: int,
    phrase_length: int,
    midi_note: int,
    phrase_high_note: int,
    rng: random.Random,
) -> int:
    """
    Compute MIDI velocity using the three-layer model (§2.14).

    Same signature as piano_stream.py. Trance structural accents are
    slightly higher (beat 1 → 95 vs 90).

    :param step_in_bar:     0-based step index within bar (0–15).
    :param step_in_phrase:  0-based step index within current phrase.
    :param phrase_length:   Total phrase length in steps.
    :param midi_note:       MIDI note number being played.
    :param phrase_high_note: Highest note heard so far in this phrase.
    :param rng:             Seeded RNG from EngineState.
    :returns:               Integer MIDI velocity in [VELOCITY_MIN, VELOCITY_MAX].
    """

# --- MIXER ---

def mix_and_limit(
    voice_buffers: list[tuple[np.ndarray, np.ndarray]],
    master_vol: float,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Sum stereo voice buffers, apply soft-clip limiter, scale by master volume.

    :param voice_buffers: List of (left, right) float32 array pairs, each
                          exactly samples_per_step long.
    :param master_vol:    Current master volume scalar (0.0–1.0).
    :returns:             Tuple of (mixed_left, mixed_right) float32 arrays.
    """
```

**`ArpNote` — pre-computed arp buffer entry** (one per sounding arp note):

```python
@dataclass
class ArpNote:
    buffer_l: np.ndarray  # pre-computed left channel float32 array, full note duration
    buffer_r: np.ndarray  # pre-computed right channel float32 array
    sample_pos: int       # current read position in the buffer (advanced by samples_per_step each step)
```

The arp accumulator is a `list[ArpNote]`. Each step, the main loop reads
`buffer_l[sample_pos : sample_pos + samples_per_step]` from every entry, sums
the slices into the arp mix buffer, advances `sample_pos`, and removes entries
that reach `len(buffer_l)`. This is separate from the supersaw `ActiveNote`
accumulator because arp waveforms are pre-computed (no per-step LFO modulation
needed — the arp decays to silence within its step duration).

**`ActiveNote` — live oscillator state entry** (one per sounding note in the note accumulator):

```python
@dataclass
class ActiveNote:
    osc_phases: np.ndarray  # (saw_count,) float32 — per-oscillator phase accumulators
    iir_L: float            # IIR filter state, left channel
    iir_R: float            # IIR filter state, right channel
    gain: float             # amplitude scalar (velocity-derived, 0.0–1.0)
    midi_note: int          # MIDI note number; used to compute oscillator frequencies
    saw_count: int          # number of oscillators (SAW_COUNT_LEAD / BASS / PAD)
    detune_cents: float     # total detuning spread in cents
    steps_remaining: int    # steps until note-off; decremented by main loop each step
```

The note accumulator is a `list[ActiveNote]`. Each step, the main loop calls
`render_supersaw_step()` for every entry, sums the buffers, decrements
`steps_remaining`, and removes entries that reach zero.

**`EngineState` — concrete definition** (decided in ADR-T-0002):

```python
@dataclass
class EngineState:
    ca_row: np.ndarray          # shape (CA_WIDTH,), dtype int
    step: int                   # global step counter (0-indexed)
    prev_lead_note: int | None  # last lead note; None at phrase start
    lead_leap_pending: bool     # True if previous lead note was a phrase-boundary leap;
                                # next select_lead_note call must return a note in the
                                # opposite direction (contrary stepwise resolution)
    prev_arp_index: int         # last arp pool index
    arp_direction: int          # +1 ascending, -1 descending
    phrase_step: int            # steps elapsed in current phrase
    phrase_length: int          # phrase length in steps
    phrase_high_note: int       # highest lead note in this phrase
    bar_note_count: int         # lead notes fired in current bar
    bar_net_direction: int      # sum of semitone intervals this bar
    phase: str                  # current arrangement phase
    phase_bar: int              # bars elapsed in current phase
    transition_step: int        # steps elapsed in current phase transition (0 = stable)
    kick_gain: float            # current voice gain scalar (0.0–1.0), ramping at transitions
    bass_gain: float
    lead_gain: float
    arp_gain: float
    pad_gain: float
    sidechain_env: float        # current sidechain gain (0.0–1.0)
    lead_lfo_phase: float       # lead filter LFO phase (0.0–1.0)
    bass_lfo_phase: float       # bass filter LFO phase (0.0–1.0)
    pad_lfo_phase: float        # pad filter LFO phase (0.0–1.0)
    lead_tgate_pattern: list    # 16-step binary gate pattern for lead voice
    pad_tgate_pattern: list     # 16-step binary gate pattern for pad voice
    master_volume_current: float  # real-time master volume scalar (tracks fade-in/out)
    fade_out_step: int          # steps elapsed since fade-out triggered (0 = not fading)
    noise_riser_amplitude: float  # current amplitude of Build-up white noise riser (0.0–1.0)
    rng: random.Random          # seeded RNG; sole source of randomness
```

### 3.6 Dependency Constraints

`trance_stream.py` may import only:

| Import | Purpose |
| --- | --- |
| `numpy` | Audio buffer arithmetic, oscillator accumulation |
| `sounddevice` | Stereo audio output stream |
| `midiutil` | MIDI file construction |
| `argparse` | CLI argument parsing |
| `os` | Flag file detection |
| `sys` | stderr, exit |
| `random` | Seeded RNG |
| `math` | Trigonometry, exponentials |
| `hashlib` | MD5 tonic derivation |
| `logging` | Structured log output |
| `dataclasses` | `@dataclass` for EngineState |

No other dependencies. Runs with:
```bash
pip install numpy sounddevice MIDIUtil
python trance_stream.py
```

### 3.7 Acceptance Test Summary

| Test ID | Requirement | Observable criterion |
| --- | --- | --- |
| T-001 | FR-1, NFR-7 | Script starts and produces stereo audio within 2 seconds |
| T-002 | BR-1, NFR-7 | A listener familiar with trance identifies the output as trance music within 15 seconds |
| T-003 | FR-2, FR-5 | Same `--seed` produces identical output on two separate runs |
| T-004 | FR-13 | Kick fires every 4 steps in Groove and Drop phases |
| T-005 | FR-14 | Every bar in MIDI export contains at least one bass note below MIDI 60 in Groove/Drop phases |
| T-006 | FR-15 | MIDI export shows no consecutive lead notes more than 7 semitones apart (except phrase boundaries) |
| T-007 | FR-16 | Script progresses through Intro→Groove→Breakdown→Buildup→Drop automatically |
| T-008 | FR-17 | Lead voice has audible rhythmic gating, not a continuous tone |
| T-009 | FR-18 | Bass/pad volume drops immediately after kick then recovers over ~0.5 seconds |
| T-010 | FR-9, FR-10 | Writing `fade_<pid>.flag` causes fade-out and exit within 4 bars |
| T-011 | NFR-3 | `stream_dj.py` can launch and crossfade `trance_stream.py` without modification |
| T-012 | NFR-6 | Terminal visualiser output ≤80 columns per line |
| T-013 | FR-8, FR-7 | `--bars 32 --out_midi test.mid` produces valid MIDI and exits cleanly |
| T-014 | BR-3 | Script runs for 30 minutes without crash, audio glitch, or terminal freeze |
| T-015 | NFR-4 | CPU usage on a modern laptop does not prevent simultaneous coding and screen-capture |

### 3.8 Open Questions and TBD Items

| Item | Blocks | Status |
| --- | --- | --- |
| Synthesis approach | §2.5, ADR-T-0001 | ✓ SuperpySaw + sine-sweep kick |
| Composition model | §2.15, ADR-T-0002 | ✓ CA-gated hybrid + state machine |
| Audio output | §2.6, ADR-T-0003 | ✓ Stereo PCM via sounddevice |
| `DETUNE_CENTS_LEAD` | §3.4, T-002 | Open — tuned by ear; start at 15 cents |
| `DETUNE_CENTS_BASS` | §3.4, T-002 | Open — tuned by ear; start at 8 cents |
| `DETUNE_CENTS_PAD` | §3.4, T-002 | Open — tuned by ear; start at 20 cents |
| `KICK_F0`, `KICK_F1`, `KICK_DECAY_S`, `KICK_ENV_TAU` | §2.5, T-004 | Open — tuned by ear during implementation |
| `SIDECHAIN_DEPTH`, `SIDECHAIN_RELEASE` | §2.5, T-009 | Open — tuned by ear; start at 0.3, 8 steps |
| `drive` (soft-clip) | §2.6 | Open — tuned during implementation |
| Filter LFO constants | §2.10 | Open — defaults in §2.10; tuned by ear |
| Arp chord pool size | §2.4 | Open — chord tones + 2 octaves = 9–12 entries |
| Bar-level state necessity | §2.15 | Open — implement two-timescale first; add bar state only if listen test reveals need |
| DJ discovery (glob) | §2.11 | Open — symlink `ca_synth_trance.py` is simplest fix; deferred |
| Stereo mono fallback threshold | §2.6 | Open — detect at startup; warn and continue |
| Noise riser synthesis | §2.8 | Open — white noise with per-step amplitude increment; exact envelope TBD |
| TB-303 bass pattern detail | §2.4 | Open — root + slide + accent notes; accent velocity and slide duration TBD |
