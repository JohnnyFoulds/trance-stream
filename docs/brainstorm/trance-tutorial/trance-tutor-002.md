# Trance Theory, The Practical Way

This is a full beginner tutorial that explains trance theory, notation, and procedural generation as one coherent guide.

It covers:

- the video-based music theory explanation
- the practical refinements that matter when turning theory into music
- how to think in scale degrees instead of note names
- how trance uses bass, lead, and pad differently
- how to express the same ideas in ASCII, ABC notation, and Strudel
- how to generate the same material procedurally in code

If you are brand new to music theory, read this as a pattern guide, not as a textbook.

---

## 1. The big idea

Trance is not complicated because the theory is complicated.
It sounds complicated because the same small set of notes is arranged in a few powerful ways:

- keep everything inside one scale
- move some notes up or down an octave
- make the bassline feel like it is climbing and dropping
- make the lead sound like a question and an answer
- make the pad hold a root note while the upper notes shift slowly
- lean on a minor scale, then briefly brighten it with a major chord feeling

If you remember only one sentence, remember this:

> trance is mostly one scale, spread across different octaves, with simple patterns that create tension and release

---

## 2. The scale: your safe note set

The video starts with a basic minor scale in C minor.
That is the safe playground.

In C minor, the useful notes are:

```
C D Eb F G Ab Bb C
1 2 3 4 5 6 7 1
```

In trance, it helps to stop thinking about note names and start thinking about scale degrees.

- Root = home
- 3rd = minor colour
- 4th = tension or movement
- 5th = stable / strong / iconic
- 6th = emotional lift
- 7th = more tension before resolution
- 9th = the 2nd an octave up, useful for colour

### ASCII piano-roll view

```
SAFE C MINOR ROWS

Pitch Degree Use
--------------------------
Bb  7     tension
Ab  6     emotional lift
G   5     strong anchor
F   4     movement / colour
Eb  3     minor colour
D   2     extra colour
C   1     home
```

### ABC equivalent

ABC is text notation that abcjs can render in a browser.

```abc
X:1
T:C minor scale
M:4/4
L:1/4
K:Cm
C D E F | G A B c |]
```

### Strudel equivalent

Strudel is live-coded music, so it is more useful for actually hearing the idea.

```javascript
note("c3 d3 eb3 f3 g3 ab3 bb3 c4")
.s("piano")
```

You can also use degrees:

```javascript
note("0 1 2 3 4 5 6 7")
.scale("c:minor")
.s("piano")
```

---

## 3. Why trance sounds emotional

Trance is usually minor, but it is not just sad.
The emotional trick is that it stays in minor long enough to feel nostalgic, then it uses bright-sounding motion to feel uplifting.

That push-pull is the trance feeling:

- minor scale = melancholic, inward, reflective
- strong rhythm = forward motion
- octave jumps = energy
- a major-flavoured chord moment = lift
- a long pad = atmosphere

So trance is not about complex harmony.
It is about emotional contrast.

---

## 4. Bassline: octave displacement

The bassline is the engine.

The important trick from the video is octave displacement: instead of playing a boring little step-by-step line, you take notes from the same scale and drop some of them down an octave.

The video's basic bass idea is:

- root
- 3rd
- 6th, but lower
- 7th, walking back up

### ASCII bassline

```
Trance bassline in C minor

Pitch    Beat 1   Beat 2   Beat 3   Beat 4
------------------------------------------
Eb3               [====]
C3      [====]
Bb2                         [====]
Ab2                 [====]

Pattern: Root -> 3rd -> drop to 6th -> rise to 7th
```

You can think of this as a bassline that says:

1. I am home.
2. I am moving.
3. I fall lower for weight.
4. I climb back toward resolution.

The 7th at the end is important: it is not a full resolution back to the root, but a walk upward that keeps the energy moving forward instead of shutting it down.

### ABC equivalent

```abc
X:2
T:Octave displacement bassline
M:4/4
L:1/4
K:Cm
C E A, B, |]
```

### Strudel equivalent

Using scale degrees:

```javascript
note("0 2 -2 -1")
.scale("c:minor")
.s("tb303")
.lpf(1000)
```

Using absolute note names:

```javascript
note("c3 eb3 ab2 bb2")
.s("tb303")
.lpf(1000)
```

### Why this works

The bass sounds bigger than it really is because the ear hears distance between notes as motion.
The line is simple, but the octave jump makes it feel intentional and energetic.

---

## 5. Lead: call and response

The lead is the logo.
It should be catchy enough to remember after one listen.

The video's lead logic is not "play everything."
It is more like a short musical exchange:

- the call asks a question
- the response answers it
- the phrase often returns toward where it started, or closes with a specific walk-down

The important notes in the video are mostly the 5th, 6th, and 7th.
That is why trance leads often float high above the bass.

### ASCII lead

```
Lead phrase in C minor

Pitch    Beat 1   Beat 2   Beat 3   Beat 4
------------------------------------------
Bb3                              [##]   <- 7th
Ab3      [###]      [###]               <- 6th
G3       [###]              [#]        <- 5th (starts and ends here)

Call:  start on 5th, move through 5/6/7, end high (tension)
Response: mirror the rhythm, walk down through 7 -> 6 -> 5 (resolution)
```

The 7-6-5 walk-down at the end is one of the most specific production tips in the video. It is not a generic resolution all the way to the root. It is a short, confident step-down that lands on the 5th, which feels stable enough to repeat.

### ABC equivalent

```abc
X:3
T:Call and response lead
M:4/4
L:1/8
K:Cm
G2 A2 B4 | B2 A2 G4 |]
```

### Strudel equivalent

```javascript
note("4 5 ~ 6 6 ~ 5 ~")
.scale("c:minor")
.s("sawtooth")
.delay(0.5)
```

Or with note names:

```javascript
note("g3 ab3 ~ bb3 bb3 ~ ab3 ~ g3")
.s("sawtooth")
.delay(0.5)
```

### How to hear it

If the bass is the floor, the lead is the headline.
It should sit above everything else and feel like it is singing.

---

## 6. Putting the three layers together

Before we get to pads, it helps to see all three parts at once.
This is what a single bar of basic trance looks like when every layer is plotted together:

```
Time ->      |1       |2       |3       |4       |

PAD  : [C+Eb+G]-----[C+F+Ab]-----[C+G+Bb]-----[C+Eb+G]
BASS : C3----Eb3----Ab2----Bb2
LEAD : G3--Ab3--F3--Eb3--Bb3--Ab3--G3
```

Each layer has a different job:

- PAD = long, breathing harmony (the atmosphere)
- BASS = rhythmic low movement (the engine)
- LEAD = memorable top-line phrase (the identity)

If you can hear those three layers separately, you can build the whole genre.

---

## 7. Pads: the real trance atmosphere

This is where the pad concept becomes more accurate.

At first, the pad was explained too simply as "just hold a chord."
The better reading is:

- keep a root note anchored underneath
- move the upper notes slowly
- let the pad feel like it is breathing
- use simple chord movement rather than fancy harmony

This is the pedal-tone idea.

### What the pad is doing

In the video, the chord area is not a wild jazz progression.
It is a simple set of notes from the scale, with a strong root underneath.

You can think of it like this:

```
Pedal root: C
Upper notes move through:

Chord 1: C + Eb + G   (C minor triad)
Chord 2: C + F + Ab   (F minor over C = brief Ab major lift)
Chord 3: C + G + Bb   (G minor over C)
Chord 4: back to C + Eb + G   (resolves home)
```

The lower note stays anchored while the top two notes shift.
That is what gives the pad its trance float.

The move to chord 2 is the emotional key moment: the 6th degree (Ab) over the root (C) creates an Ab major feeling. That is the brief flash of brightness inside the minor context. It is the "major chord" the video points to when it says the 6th degree makes the track feel uplifting even though the scale is minor.

### ASCII pad

```
Pad with pedal tone in C minor

Pitch    Bar 1        Bar 2        Bar 3        Bar 4
-------------------------------------------------------
Bb3                        [========]               <- 7th
Ab3                                    [========]   <- 6th (major lift)
G3      [========]                [========]   [========]
F3                      [========]                   <- 4th
Eb3     [========]                [========]           <- 3rd
C3      [=============================================]  <- Pedal tone (never leaves)
```

Root stays on. Upper notes change slowly.

### ABC equivalent

```abc
X:4
T:Pedal tone pad
M:4/4
L:1/1
K:Cm
[C, E G] [C, F A] | [C, G B] [C, E G] |]
```

### Strudel equivalent

```javascript
note("[c2,eb3,g3] [c2,f3,ab3] [c2,g3,bb3] [c2,eb3,g3]")
.s("supersaw")
.slow(4)
.room(0.8)
.sz(0.9)
```

### Why the pad matters more than it looks

A static chord would sound fine.
A moving pedal-tone pad sounds like a trance track.
The slow shift underneath a fixed root is what creates the "breathing" feeling that makes the genre feel massive even with simple harmony.

---

## 8. The same ideas in abcjs and Strudel

This section is the direct side-by-side comparison.

### Scale stencil

```abc
X:1
T:C minor scale
M:4/4
L:1/4
K:Cm
C D E F | G A B c |]
```

```javascript
note("0 1 2 3 4 5 6 7")
.scale("c:minor")
.s("piano")
```

### Bassline

```abc
X:2
T:Octave displacement bassline
M:4/4
L:1/4
K:Cm
C E A, B, |]
```

```javascript
note("0 2 -2 -1")
.scale("c:minor")
.s("tb303")
.lpf(1000)
```

### Lead

```abc
X:3
T:Call and response lead
M:4/4
L:1/8
K:Cm
G2 A2 B4 | B2 A2 G4 |]
```

```javascript
note("4 5 ~ 6 6 ~ 5 ~")
.scale("c:minor")
.s("supersaw")
.delay(0.5)
```

### Pad

```abc
X:4
T:Pedal tone pad
M:4/4
L:1/1
K:Cm
[C, E G] [C, F A] | [C, G B] [C, E G] |]
```

```javascript
note("[c2,eb3,g3] [c2,f3,ab3] [c2,g3,bb3] [c2,eb3,g3]")
.s("supersaw")
.slow(4)
.room(0.8)
```

### What abcjs is for

abcjs is the browser-friendly text notation layer.
It is good when you want notation to render visually in a web page or note-taking app.

### What Strudel is for

Strudel is the live audio layer.
It is good when you want to hear the same idea immediately, using patterns and scale degrees.

---

## 9. Procedural generation: turning the tutorial into code

This repo does not just explain trance.
It generates it.

The procedural version of the tutorial is not just "play the same four bars forever."
It is a set of rules that can produce infinite variations while staying inside the trance vocabulary:

- store the safe notes in a scale
- store the rhythm as a pattern of degrees
- generate bass, lead, and pad separately
- map degrees to MIDI notes
- render the result bar by bar

The important shift from "music theory demo" to "procedural system" is this:

> the same compositional rules are expressed as constraints and patterns, not as fixed note lists

That means you can change the root, the scale, the tempo, and the seed, and the system will produce a new track that still sounds like trance.

### The full algorithmic ruleset

These are the rules the generator follows, derived directly from the tutorial:

**Canvas (Key and Scale):**
- Randomise tempo between 135 and 140 BPM.
- Pick a root note (MIDI integer, 0-11 for the twelve keys).
- Use a fixed minor-scale interval array: `[0, 2, 3, 5, 7, 8, 10]`.
- Every safe pitch is computed as `root + interval_array[degree] + octave_shift * 12`.

**Bassline generator (octave displacement rules):**
- Rhythm: 16th-note grid. The first 16th note of each beat is a rest (leaves room for the kick drum). The remaining three 16th notes play the same pitch.
- Pitch logic across four bars:
  - Bar 1: Scale index 0 (Root).
  - Bar 2: Random choice from index 2, 3, or 4 (3rd, 4th, or 5th).
  - Bar 3: Random choice from index 4, 5, or 6, then subtract 12 semitones to force the octave drop.
  - Bar 4: Pick index +1 or -1 from Bar 3 to walk back up or down.
- Result: constant octave displacement without repeating the same line.

**Lead generator (constrained call and response):**
- Lead is restricted to scale indexes 0, 4, 5, 6 (Root, 5th, 6th, 7th).
- Call phase: generate an 8th-note sequence across two bars. Rule: the final note of the call must land on index 4, 5, or 6 (ends on tension).
- Response phase: clone the rhythm of the call. Rule: the second bar walks down index-by-index and must end on index 0 or 4 (resolution).
- The 7-6-5 walk-down is a special case of this: when the call ends on index 6 (7th), the response walks 6 -> 5 -> 4.

**Pad generator (pedal tone logic):**
- Bottom layer: hardcode the root note at two octaves (e.g., C2 and C4) and hold for the full phrase.
- Top layer: for each bar, randomly select a two-note stack from the scale:
  - Option A: index 2 + index 4
  - Option B: index 3 + index 5
  - Option C: index 4 + index 6
- Because the pedal tone never moves, any combination of those upper stacks produces a valid, floating trance pad.

### Minimal Python helper functions

```python
SCALE_MINOR = [0, 2, 3, 5, 7, 8, 10]  # semitone intervals

def degree_to_midi(root_midi: int, degree: int, octave_shift: int = 0) -> int:
    """Convert a scale degree to a MIDI note number."""
    degree_index = degree % len(SCALE_MINOR)
    octave = degree // len(SCALE_MINOR)
    return root_midi + SCALE_MINOR[degree_index] + 12 * (octave + octave_shift)

def make_bass_line(root_midi: int) -> list[int]:
    """Root -> 3rd -> 6th (dropped) -> 7th."""
    return [
        degree_to_midi(root_midi, 0),    # Root
        degree_to_midi(root_midi, 2),    # 3rd
        degree_to_midi(root_midi, -2),   # 6th, one octave down
        degree_to_midi(root_midi, -1),   # 7th, one octave down (walking back up)
    ]

def make_lead_phrase(root_midi: int) -> list[int]:
    """5/6/7-based call and response with 7-6-5 ending."""
    return [
        degree_to_midi(root_midi, 4),  # 5th
        degree_to_midi(root_midi, 5),  # 6th
        degree_to_midi(root_midi, 3),  # 4th
        degree_to_midi(root_midi, 2),  # 3rd
        degree_to_midi(root_midi, 6),  # 7th (call tension)
        degree_to_midi(root_midi, 5),  # 6th (7-6-5 walkdown)
        degree_to_midi(root_midi, 4),  # 5th (resolution)
    ]

def make_pad_chords(root_midi: int) -> list[list[int]]:
    """Pedal-tone chord progression."""
    return [
        [degree_to_midi(root_midi, 0), degree_to_midi(root_midi, 2), degree_to_midi(root_midi, 4)],
        [degree_to_midi(root_midi, 0), degree_to_midi(root_midi, 3), degree_to_midi(root_midi, 5)],
        [degree_to_midi(root_midi, 0), degree_to_midi(root_midi, 4), degree_to_midi(root_midi, 6)],
        [degree_to_midi(root_midi, 0), degree_to_midi(root_midi, 2), degree_to_midi(root_midi, 4)],
    ]
```

These functions are deterministic on purpose: they encode the rules, not random numbers.
The actual procedural randomness lives in the caller, which picks bars, orderings, and register shifts from the seed.

### How this maps to the real repo

The real generator in this repository does the same job, but in a more complete way:

- `song/theory.py` stores the musical constants and scale mappings
- `song/builder.py` chooses the seed-driven progression, register, and arc
- `song/renderer.py` turns that song state into bar-by-bar audio
- `instruments/` and `synth/` actually synthesize the sound

If you want to understand the real implementation, start there.

### Procedural Strudel example

Strudel can express the same generative logic directly in the browser.
The key production tricks that make it sound like trance rather than a demo:

- **Fake sidechain compression:** use `isaw.fast(4).range(0.2, 0.8)` on `.gain()` to duck the pad and lead on every kick hit.
- **Filter envelopes:** use `.lpenv()` on the bass to make it pluck and roll instead of sustaining.
- **Slow filter sweeps:** use `sine.slow(8).range(400, 3500)` on the pad filter for a breathing, evolving atmosphere.
- **Delay and room:** `.delay(0.75).delayfeedback(0.5)` on the lead, `.room(1)` on the pad.

```javascript
stack(
  // 1. Drums: four-on-the-floor kick, offbeat hats, clap on 2 and 4
  s("bd*4").gain(1.4).lpf(2000),
  s("[~ hh]*4").gain(0.8).hpf(5000),
  s("[~ cp]*2").gain(0.7).room(0.5),

  // 2. Bass: rolling 16th notes, octave displacement, acid filter envelope
  note("~ 0 0 0").fast(4).add("<0 2 -2 -1>")
    .scale("c:minor")
    .s("sawtooth")
    .lpf(400).lpenv(4).lpq(12)
    .decay(0.15).sustain(0)
    .gain(1.1),

  // 3. Pad: pedal tone with slow-moving upper chords, fake sidechain, slow filter swell
  note("<[c2,c3,eb3,g3] [c2,c3,f3,ab3] [c2,c3,g3,bb3] [c2,c3,eb3,g3]>")
    .s("supersaw")
    .detune(0.015)
    .lpf(sine.slow(8).range(400, 3500))
    .gain(isaw.fast(4).range(0.2, 0.9))
    .room(1),

  // 4. Lead: call and response in 5/6/7, 7-6-5 resolution, wide delay, slow opening filter
  note("<[4 5 ~ 6 6 ~ 5 ~] [6 5 ~ 4 4 ~ ~ ~]>")
    .scale("c:minor")
    .fast(2)
    .s("supersaw")
    .detune(0.02)
    .decay(0.3).sustain(0.1)
    .gain(isaw.fast(4).range(0.2, 0.8))
    .delay(0.75).delayfeedback(0.5)
    .lpf(sine.slow(16).range(800, 8000))
    .room(0.8)
).cpm(138)
```

### The honest limitation

The algorithm gives you structure, not final polish.

If you want something that sounds fully finished and club-ready, you still need serious sound design, filtering, compression, and sidechain control. The generator can create the musical skeleton, but the production chain has to make it sound like trance.

That is why the tutorial is useful even if the raw Strudel version sounds rough: it gives you the note logic and the arrangement logic that a procedural system can build on.

---

## 10. Beginner checklist

If you are new to music theory, this is the practical memory aid:

- use one minor scale
- do not leave that scale unless you know why
- make the bass jump by octaves
- make the lead sound like a question and answer
- close the lead phrase with 7-6-5 before repeating
- keep the pad simple and slow
- let the root note anchor the harmony
- use a major-flavoured chord moment (the 6th degree) for lift
- do not overcomplicate the progression

If it sounds too plain, add motion.
If it sounds too busy, remove notes.

That is a lot of trance production in one sentence.

---

## 11. Listening guide

When you listen back, focus on these questions:

- Do I hear one clear home note?
- Does the bass move in jumps instead of chromatic wandering?
- Does the lead feel like a memorable phrase, ending on 7-6-5?
- Does the pad breathe instead of just sitting still?
- Does the track feel minor but still uplifting?

If the answer to all five is yes, you are in the right zone.

---

## 12. Short version

Trance is:

- one scale
- three roles
- a few strong intervals
- octave movement
- tension and release
- 7-6-5 closing the lead
- a held root underneath slow-moving harmony

That is the core of the video and the procedural version all at once.
