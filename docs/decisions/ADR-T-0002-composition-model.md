# ADR-T-0002 — Composition model uses CA-gated multi-voice rule-based hybrid

**Status:** Accepted
**Date:** 2026-07-08

## Context

The musical engine must drive five independent voices (kick, bass, lead, arp, pad)
in a trance arrangement that evolves continuously without exact repetition (FR-2),
following the structure Switch Angel uses in her live sets: Intro → Groove →
Breakdown → Build-up → Drop cycling every N bars.

The engine must satisfy:
- Four-on-the-floor kick on every beat regardless of state (FR-13)
- Bass note on beat 1 of every bar (FR-14)
- Lead and arp notes selected from the current scale, with melodic continuity (FR-15)
- Dynamic arrangement: voices mute/unmute per phase (FR-16)
- Trance gate rhythmic texture on lead and pad (FR-17)
- Same seed always produces same output (FR-2)
- Music must be listenable for 30+ minutes (BR-3)

The reference composition model is Switch Angel's `prebake.strudel`. Key functions:
- `trancearp`: note pool with range syntax, restart direction (F/B), rhythm structure
- `tgate`: rhythmic gate from a curated 38-entry seed table
- `.mask()` patterns: binary on/off per 8-bar section for arrangement

Four composition models were evaluated:

| Model | Description |
|-------|-------------|
| **CA-only** | CA drives all musical decisions |
| **Markov chain** | Transition probabilities per scale degree |
| **State machine** | Explicit Groove/Breakdown/Buildup/Drop state machine with probabilistic voice |
| **Hybrid** | CA provides rhythm/gating; rules constrain note selection; state machine controls arrangement |

## Decision

Use a **CA-gated, rule-based hybrid with an arrangement state machine** (the hybrid
option), directly analogous to the piano_stream composition model but extended
to five voices and an explicit arrangement phase.

### CA layer — rhythm and gating

A Wolfram 1D CA (Rule 30, width `CA_WIDTH = 32`) advances one step per musical
step (16th note). Named bit positions gate each voice:

| Bit position | Gate |
|-------------|------|
| `LEAD_GATE` | 1 = lead note fires this step |
| `ARP_GATE` | 1 = arp note fires this step; `ARP_REST_PROBABILITY` is a secondary check applied when this bit is 1 |
| `PHRASE_BIT` | phrase boundary signal |
| `ARP_DIR_BIT` | arp direction reversal signal (guarded by phrase boundary) |

The pad voice is not CA-gated. Pad notes are triggered once per chord change
(`CHORD_DURATION_BARS * STEPS_PER_BAR` steps), sustaining for that full duration.
The trance gate (§2.9) handles all rhythmic texture on the pad; CA-gating would
retrigger oscillators each step and cause phase discontinuities in the sustained chord.

The kick fires unconditionally on every beat (every 4th step); no CA gate is
needed. The bass fires unconditionally on beat 1 of each bar; other bass steps
follow a pattern determined by `--mood` (same per-mood pattern model as
piano_stream's accompaniment patterns).

### Rule layer — note selection

**Lead:** At each step where `LEAD_GATE` fires, select a note from the current
chord tones and their octave transpositions within `[LEAD_LOW, LEAD_HIGH]`. The
candidate must be within `MAX_LEAD_INTERVAL` semitones of the previous note.
At phrase boundaries (signalled by `PHRASE_BIT`), a leap of up to 12 semitones
is permitted, followed by stepwise contrary motion on the next note.

**Arp:** At each step where `ARP_GATE` fires, select a note by cycling an arp
index through the current chord tones plus two octave transpositions. The arp
direction (up/down/up-down) is determined by `--mood`. On phrase boundaries the
arp direction reverses. This models Switch Angel's `trancearp` forward/backward
cycling.

**Bass:** Beat 1 always fires the root note of the current chord. Non-beat-1
steps follow the mood-specific bass pattern (rolling 16ths, off-beat, or root-
only). Bass notes are selected from `[BASS_LOW, BASS_HIGH]`.

**Pad:** Does not select individual notes. Instead, the pad voice sustains the
full current chord as a supersaw cluster in `[PAD_LOW, PAD_HIGH]`. The trance
gate (FR-17) is applied to the pad output using a seed selected from the
curated table (see §2.9).

### Arrangement state machine

The arrangement cycles through four phases, each lasting `PHASE_BARS` bars:

```
Intro → Groove → Breakdown → Build-up → Drop → (repeat from Groove)
```

| Phase | Kick | Bass | Lead | Arp | Pad | Noise riser |
|-------|------|------|------|-----|-----|-------------|
| Intro | low-pass filtered | muted | muted | muted | filtered | no |
| Groove | full | full | full | full | full | no |
| Breakdown | muted | muted | filtered | full | full | no |
| Build-up | half-time | muted | muted | full | full | yes |
| Drop | full | full | full | full | full | no |

Voice muting is implemented via per-step gain scalars (0.0 = muted, 1.0 = full),
not by suppressing synthesis. This allows smooth transitions (gain ramps rather
than hard cuts) at phase boundaries and preserves the IIR filter state across
transitions.

Phase duration is controlled by `PHASE_BARS` (default 16 bars). Intro runs once at
the start; the four-phase loop (Groove → Breakdown → Build-up → Drop) repeats
indefinitely.

### `EngineState` — concrete definition

```python
@dataclass
class EngineState:
    ca_row: np.ndarray          # shape (CA_WIDTH,), dtype int; current CA row
    step: int                   # global step counter (0-indexed)
    prev_lead_note: int | None  # last lead note; None at phrase start
    lead_leap_pending: bool     # True if previous lead note was a phrase-boundary leap;
                                # next select_lead_note call must return a note in the
                                # opposite direction (contrary stepwise resolution)
    prev_arp_index: int         # last arp index (0-indexed into chord pool)
    arp_direction: int          # +1 = ascending, -1 = descending
    phrase_step: int            # steps elapsed in current phrase (0-indexed)
    phrase_length: int          # phrase length in steps (PHRASE_SHORT or PHRASE_LONG)
    phrase_high_note: int       # highest lead note seen this phrase (velocity shaping)
    bar_note_count: int         # lead notes fired in current bar; reset every 16 steps
    bar_net_direction: int      # sum of semitone intervals this bar
    phase: str                  # current arrangement phase name
    phase_bar: int              # bars elapsed in current phase
    transition_step: int        # steps elapsed in current phase transition (0 = stable)
    kick_gain: float            # current voice gain scalar (0.0–1.0), ramping at transitions
    bass_gain: float
    lead_gain: float
    arp_gain: float
    pad_gain: float
    sidechain_env: float        # current sidechain envelope value (0.0–1.0)
    lead_lfo_phase: float       # lead filter LFO phase (0.0–1.0)
    bass_lfo_phase: float       # bass filter LFO phase (0.0–1.0)
    pad_lfo_phase: float        # pad filter LFO phase (0.0–1.0)
    lead_tgate_pattern: list    # 16-step binary gate pattern for lead; set at phase transitions
    pad_tgate_pattern: list     # 16-step binary gate pattern for pad; set at phase transitions
    master_volume_current: float  # real-time master volume (fade-in/out in progress)
    fade_out_step: int          # steps elapsed since fade-out triggered (0 = not fading)
    noise_riser_amplitude: float  # current amplitude of Build-up white noise riser (0.0–1.0)
    rng: random.Random          # seeded RNG; sole source of randomness
```

### Chord progressions per mood

Root note derived from seed: `root = 48 + (int(hashlib.md5(seed.encode()).hexdigest(), 16) % 12)`.

`CHORD_DURATION_BARS = 4` (trance uses slower harmonic rhythm than piano; 4 bars
per chord gives 16 bars per full cycle, matching a standard 16-bar trance phrase).

| Mood | Character | Progression | Subgenre |
|------|-----------|-------------|----------|
| `uplifting` | Euphoric, emotional | i → VI → III → VII (minor) | Uplifting trance |
| `dark` | Driving, intense | i → iv → v → i (minor) | Dark/tech trance |
| `acid` | Hypnotic, TB-303 | i → VII → VI → VII (minor) | Acid trance |
| `progressive` | Groovy, slower | i → iv → I → VII (minor/modal) | Progressive trance |
| `ambient` | Open, floating | Imaj7 → VIImaj7 → VImaj7 → VIImaj7 | Ambient trance |

### Bass patterns per mood

| Mood | Pattern |
|------|---------|
| `uplifting` | Rolling 16ths: root on every 16th step, gated by sidechain |
| `dark` | Off-beat: root on beat 1, syncopated hit on step 10 |
| `acid` | TB-303 pattern: root + chromatic slide notes, accent and glide |
| `progressive` | Broken octave: root on 1, octave on 7, root on 9, fifth on 13 |
| `ambient` | Whole-bar sustain: root fires on beat 1 only, sustains until beat 1 of next bar |

### Trance gate seeds (FR-17)

The trance gate is applied to lead and pad voices using a seed from a curated table
(ported from Switch Angel's `tgate` lookup in `prebake.strudel`). Each phase selects
a trance gate seed deterministically from `EngineState.rng` at the phase boundary:

```python
TGATE_SEEDS = [45, 116, 99, 100, 107, 53, 57, 58, 67, 81, 89, 115, 8, 118, 120, 149]
```

These seeds index into an internal 16-bit pseudo-random sequence to produce a
rhythmic 16-step binary pattern. The resulting gate pattern is applied to the lead
and pad voice gains each step.

## Motivation

**Five-voice architecture mirrors Switch Angel's layer model.** Her sets always
have: kick, bass, lead, arp, and pad as distinct layers, mixed live using
`.mask()` patterns. A flat monophonic generator cannot reproduce this.

**CA layer for rhythm satisfies FR-2 without sampled patterns.** The same
aperiodic non-repetition property that makes Rule 30 suitable for piano works
for trance gating. The lead gate bit produces irregular rhythmic patterns that
feel composed rather than mechanical.

**State machine for arrangement is required.** Unlike piano (two voices, no
phases), trance has explicit arrangement structure: the breakdown and drop are
musically essential and cannot emerge from a CA alone. A state machine is
the correct tool for explicit phase transitions.

**Per-voice gain scalars for muting over hard synthesis suppression.** Trance
transitions are smooth (2-bar fade between phases). Hard muting produces clicks;
gain ramps do not.

**`CHORD_DURATION_BARS = 4` matches trance harmonic rhythm.** Piano uses 2-bar
chords (fast harmonic movement). Trance typically holds a chord for 4–8 bars —
the hypnotic quality comes from slow harmonic change with fast rhythmic activity.
4 bars is the minimum for trance to feel correct.

Alternatives considered:

| Alternative | Reason not chosen |
|-------------|-------------------|
| CA-only | Cannot enforce interval constraints or produce structured arrangement |
| Markov chain | Requires training data; no advantage over rule layer for this genre |
| State machine only (no CA) | Note selection without a stochastic driver converges on repeated patterns |
| Copy Switch Angel's Strudel patterns verbatim | Not procedural generation; would not satisfy FR-2 |

## Consequences

**Enables:**
- Five-voice trance arrangement with automatic phase transitions
- Non-repeating lead and arp lines via CA gating
- Smooth phase transitions via gain ramps
- Trance gate texture on lead and pad via seeded binary gate patterns

**Rules out:**
- Per-step arrangement editing (arrangement is automatic, not live-coded)
- Complex chord voicings (chords are root-position triads and sevenths only)

**Watch for:**
- Phrase boundary detection (same guard as piano_stream): `PHRASE_BIT` must be
  guarded by `MIN_PHRASE_BARS` to prevent erratic phrase resets
- Sidechain envelope: the sidechain trigger fires if and only if the kick gain
  scalar for the current phase is > 0. In Breakdown (kick gain = 0) no sidechain
  trigger fires; bass and pad sustain at full gain. In Intro (kick gain = 0.4)
  the sidechain trigger does fire, producing a subtle pump.
- Arp direction reversal at phrase boundaries: if `arp_direction` is not
  carried across phase transitions, the arp restarts unpredictably. Carry
  `prev_arp_index` and `arp_direction` through phase changes unchanged
