# ADR-T-0001 — Trance synthesis uses SuperpySaw + TB-303 physical models

**Status:** Accepted
**Date:** 2026-07-08

## Context

The acoustic requirement (BR-1) is that the output must sound like a Switch Angel
live-coded trance track to a listener familiar with the genre. NFR-7 makes this
concrete: the synthesis must reproduce the defining timbres of Switch Angel's
published Strudel sets — supersaw leads, gated pads, TB-303-style acid basslines,
and a clean four-on-the-floor kick — all from mathematics with no pre-recorded
samples (BR-2).

The reference for the target sound is Switch Angel's `prebake.strudel`
(github.com/switchangel/strudel-scripts) and her "Coding Trance Music from
Scratch" stream (youtube.com/watch?v=iu5rnQkfO6M).

Five synthesis tasks were identified:

| Voice | Timbre needed |
|-------|--------------|
| Kick  | Trance kick: sine sweep (pitch-drop), punchy attack, sub thump |
| Bass  | Supersaw: multiple detuned sawtooth waves, low-pass filter sweep, sidechain ducked |
| Lead  | Supersaw: higher register, more detuning spread, filter envelope, trance gate |
| Arp   | Single sawtooth or triangle, short decay, no sustain, acid envelope |
| Pad   | Supersaw or sine cluster, long attack/release, trance gate, deep reverb |

Two synthesis approaches were evaluated for the melodic voices:

**Option A — Additive / FM synthesis**
Sum harmonics explicitly. For a sawtooth: fundamental + 1/2 second + 1/3 third
+ … Each partial has an independent amplitude envelope. Controllable but requires
careful parameter tuning to avoid sounding thin.

**Option B — Naive supersaw (multiple detuned oscillators)**
Instantiate N sawtooth oscillators per note, each tuned slightly off-pitch
(spread controlled by a `detune_cents` parameter), and sum them. This is how
hardware and software synthesisers implement a "super saw". The detuning spread
produces the characteristic chorus-like width of the trance lead sound.

## Decision

Use **naive supersaw (N detuned sawtooth oscillators)** for all melodic voices.
Use **sine-sweep with envelope** for the kick. Use a **single sawtooth with fast
filter envelope** for the arp/acid voice.

**SuperpySaw — melodic voices (bass, lead, pad):**

1. Each note spawns N=7 sawtooth oscillators (N is a named constant, `SAW_COUNT`).
   Detuning offsets are distributed symmetrically: oscillator k is detuned by
   `(k - (N-1)/2) * spread_cents` where `spread_cents` is a per-voice constant.
2. Notes use a **live oscillator state model** — they do NOT pre-compute their full
   waveform at note-on time. Instead, `init_supersaw()` returns the initial state
   `(osc_phases, iir_L, iir_R, gain)`. Each step, `render_supersaw_step()` advances
   the oscillator phases by `samples_per_step` samples, applies the IIR filter at the
   current step's LFO cutoff, and returns the step buffer plus updated state.
3. Each oscillator generates one sample at a time: `phase += freq_k / SAMPLE_RATE`,
   wrapped mod 1.0; output `= 2*phase - 1` (bipolar sawtooth).
4. All N oscillators are summed and divided by N (normalise amplitude).
5. A first-order IIR low-pass filter is applied per render step:
   `y[n] = (1-a)*y[n-1] + a*x[n]` where `a = 2π*f_c / (2π*f_c + SAMPLE_RATE)`.
   The cutoff `f_c` is supplied by the caller, computed from the LFO each step.
   The filter state (`iir_L`, `iir_R`) is carried between render calls so cutoff
   changes never cause discontinuities.
6. The kick uses a sine wave with exponential frequency sweep from `KICK_F0` to
   `KICK_F1` over `KICK_DECAY` samples (geometric interpolation — see §2.5 formula),
   multiplied by an exponential amplitude envelope. No additional harmonics are
   needed — the sine sweep produces the characteristic thump.

**Sidechain simulation:**
A per-step gain envelope is applied to the bass and pad voices after the filter.
The kick fires on every beat 1, 2, 3, 4 (four-on-the-floor). Each kick triggers
a volume dip that recovers over `SIDECHAIN_RELEASE` steps, producing the
"pumping" effect characteristic of trance sidechain compression.

## Motivation

**Supersaw is the defining timbre.** Switch Angel's primary sound is the supersaw
lead, built from `s("supersaw")` in Strudel. Any synthesis approach that cannot
produce a convincing supersaw cannot satisfy BR-1.

**Seven oscillators is the industry-standard count.** The Roland JP-8000 supersaw
used 7 detuned oscillators. This is the reference for the genre. N=7 gives
sufficient width without prohibitive CPU cost (NFR-4). At N=3 the sound is thin;
at N=11 the cost is noticeable and the quality improvement marginal.

**Karplus-Strong is not suitable for these timbres.** KS models a decaying string,
which is excellent for piano (ADR-U-0002 in piano_stream). Trance leads and basses
sustain continuously for the duration of the note — they do not decay. A KS delay
line produces a continuously decaying waveform; the synthesis target here requires
steady-state oscillation. Using KS for supersaw would require a feedback mechanism
to maintain oscillation amplitude, which is more complex and less accurate than
direct oscillator accumulation.

**Sawtooth is analytically trivial.** A single sawtooth oscillator is one multiply,
one modulo, and one scale per sample — O(1) per oscillator, O(N) per note, O(N×P)
for P simultaneous notes. At N=7 and P=4 voices, this is 28 oscillators running
at 44,100 Hz — well within NFR-4.

**Sine-sweep kick avoids drum samples.** A trance kick is essentially a pitched
sine wave that drops from ~150Hz to ~50Hz over 50–80ms with an exponential volume
envelope. This is the standard programmatic kick synthesis technique. It requires
no pre-recorded material (BR-2) and is compact (~15 lines).

Alternatives considered:

| Alternative | Reason not chosen |
|-------------|-------------------|
| Karplus-Strong | Models decaying strings; unsuitable for sustained sawtooth oscillation |
| FM synthesis | Difficult to tune to a convincing supersaw; risk of "FM piano" artefacts |
| Additive (sawtooth via harmonics) | Correct in theory but requires 20+ harmonics for a convincing saw; naive supersaw achieves the same timbre more simply |
| Wavetable | Requires sampled data (violates BR-2) |

## Consequences

**Enables:**
- Convincing supersaw leads, basses, and pads (BR-1 satisfied)
- Register-independent timbre control via `detune_cents` per voice
- Continuous filter LFO modulation via the live oscillator state model: cutoff
  changes take effect at the next render step with no clicks or filter-state reset
- Sidechain pumping via per-step gain envelope on bass and pad voices

**Rules out:**
- Per-partial harmonic control (not needed; supersaw produces natural harmonic
  content from the beat-frequency interactions between detuned oscillators)
- Physically modelled resonance (not needed for this genre)

**Watch for:**
- Zipper noise: the IIR filter state (`iir_L`, `iir_R`) must be carried across
  render steps. `render_supersaw_step()` returns the updated filter state as part
  of its return tuple; the caller must pass it back on the next call.
- Aliasing: sawtooth oscillators alias above Nyquist. At 44,100 Hz this is audible
  for very high notes (>3 kHz fundamental). Anti-aliasing (BLEP or band-limited
  tables) can be added in a later pass if aliasing proves audible in the melody register.
  It is not required for the bass or pad voices.
- Kick pitch accuracy: `KICK_F0` and `KICK_F1` are tuned by ear during implementation
