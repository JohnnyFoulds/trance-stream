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
C  D  Eb  F  G  Ab  Bb  C
1  2   3  4  5   6   7  1
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

```text
SAFE C MINOR ROWS

Pitch   Degree   Use
--------------------------
Bb      7        tension
Ab      6        emotional lift
G       5        strong anchor
F       4        movement / colour
Eb      3        minor colour
D       2        extra colour
C       1        home
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

The video’s basic bass idea is:

- root
- 3rd
- 6th, but lower
- 7th, walking back up

### ASCII bassline

```text
Trance bassline in C minor

Pitch   Beat 1   Beat 2   Beat 3   Beat 4
------------------------------------------
Eb3                [====]
C3      [====]
Bb2                         [====]
Ab2               [====]

Pattern:
Root -> 3rd -> drop to 6th -> rise to 7th
```

You can think of this as a bassline that says:

1. I am home.
2. I am moving.
3. I fall lower for weight.
4. I climb back toward resolution.

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

The video’s lead logic is not “play everything.”
It is more like a short musical exchange:

- the call asks a question
- the response answers it
- the phrase often returns toward where it started

The important notes in the video are mostly the 5th, 6th, and 7th.
That is why trance leads often float high above the bass.

### ASCII lead

```text
Lead phrase in C minor

Pitch   Beat 1   Beat 2   Beat 3   Beat 4
------------------------------------------
Bb3                         [##]
Ab3               [###]            [##]
G3      [###]                          [#]
F3               [###]       [###]
Eb3                        [###]

Idea:
start high -> move around 5/6/7 -> return toward the starting tone
```

One practical refinement matters here:

- the lead should not live on every scale degree
- it should hover mostly around the top of the scale
- it often returns upward to the starting pitch rather than resolving all the way to the root

### ABC equivalent

```abc
X:3
T:Call and response lead
M:4/4
L:1/8
K:Cm
G2 A F E4 | B2 A G4 |]
```

### Strudel equivalent

```javascript
note("4 5 3 2 ~ 6 5 4")
  .scale("c:minor")
  .s("sawtooth")
  .delay(0.5)
```

Or with note names:

```javascript
note("g3 ab3 f3 eb3 ~ bb3 ab3 g3")
  .s("sawtooth")
  .delay(0.5)
```

### How to hear it

If the bass is the floor, the lead is the headline.
It should sit above everything else and feel like it is singing.

---

## 6. Pads: the real trance atmosphere

This is where the pad concept becomes more accurate.

At first, the pad was explained too simply as “just hold a chord.”
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

```text
Pedal root: C
Upper notes move through:

Chord 1: C + Eb + G
Chord 2: C + F  + Ab
Chord 3: C + G  + Bb
Chord 4: back to C + Eb + G
```

The lower note stays anchored while the top two notes shift.
That is what gives the pad its trance float.

### ASCII pad

```text
Pad with pedal tone in C minor

Pitch   Bar 1        Bar 2        Bar 3        Bar 4
--------------------------------------------------------
Bb3                 [========]                [========]
Ab3        [========]                    [========]
G3      [================================================]
F3                 [========]
Eb3      [========]                    [========]
C3      [================================================]

Root stays on. Upper notes change slowly.
```

### ABC equivalent

```abc
X:4
T:Pedal tone pad
M:4/4
L:1/1
K:Cm
[C, E G] [C, F A] [C, G B] [C, E G] |]
```

### Strudel equivalent

```javascript
note("[c2,eb3,g3] [c2,f3,ab3] [c2,g3,bb3] [c2,eb3,g3]")
  .s("supersaw")
  .slow(4)
  .room(0.8)
  .sz(0.9)
```

### The major-flash feeling

One of the most important emotional tricks in trance is the bright chord moment.
Even though the track sits in minor, a move to the 6th degree area can briefly feel major and uplifting.

That is why trance can sound sad and euphoric at the same time.

---

## 7. Putting the three layers together

The full track logic is:

1. the pad holds the atmosphere
2. the bass gives movement and weight
3. the lead gives identity

If you strip it down, trance is usually this:

```text
PAD  = long, breathing harmony
BASS = rhythmic low movement
LEAD = memorable top-line phrase
```

### Combined ASCII sketch

```text
Time -> |1      |2      |3      |4      |

PAD    : [C+Eb+G]----[C+F+Ab]----[C+G+Bb]----[C+Eb+G]
BASS   : C3----Eb3----Ab2----Bb2
LEAD   : G3--Ab3--F3--Eb3--Bb3--Ab3--G3
```

If you can hear those three layers separately, you can build the whole genre.

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
G2 A F E4 | B2 A G4 |]
```

```javascript
note("4 5 3 2 ~ 6 5 4")
  .scale("c:minor")
  .s("sawtooth")
  .delay(0.5)
```

### Pad

```abc
X:4
T:Pedal tone pad
M:4/4
L:1/1
K:Cm
[C, E G] [C, F A] [C, G B] [C, E G] |]
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

The procedural version of the tutorial is simple:

- store the safe notes in a scale
- store the rhythm as a pattern of degrees
- generate bass, lead, and pad separately
- map degrees to MIDI notes
- render the result bar by bar

The procedural version needs an explicit algorithm for turning theory into a trance groove in Strudel:

- start from four layers: drums, bass, lead, pad
- keep the bass off the kick by using a rolling pattern instead of full-beat notes
- make the lead phrase repeatable but not static by alternating call/response fragments
- keep the pad slow and wide with a pedal tone under moving upper notes
- use hats and delay to add motion even when the melodic material is simple
- fake sidechain in Strudel by shaping amplitude rhythmically, since the environment does not give you DAW-style compression

That is the key algorithmic shift from “music theory demo” to “actually sounds like trance”.

### Minimal Python example

This is a tiny standalone version of the idea.

```python
SCALE_C_MINOR = [0, 2, 3, 5, 7, 8, 10]

def degree_to_midi(root_midi: int, degree: int, octave_shift: int = 0) -> int:
    """Convert a scale degree to a MIDI note."""
    degree_index = degree % len(SCALE_C_MINOR)
    octave = degree // len(SCALE_C_MINOR)
    return root_midi + SCALE_C_MINOR[degree_index] + 12 * (octave + octave_shift)

def make_bass_line(root_midi: int) -> list[int]:
    """Root -> 3rd -> 6th down -> 7th."""
    return [
        degree_to_midi(root_midi, 0),
        degree_to_midi(root_midi, 2),
        degree_to_midi(root_midi, -2),
        degree_to_midi(root_midi, -1),
    ]

def make_lead_phrase(root_midi: int) -> list[int]:
    """A simple 5/6/7-based trance phrase."""
    return [
        degree_to_midi(root_midi, 4),
        degree_to_midi(root_midi, 5),
        degree_to_midi(root_midi, 3),
        degree_to_midi(root_midi, 2),
        degree_to_midi(root_midi, 6),
        degree_to_midi(root_midi, 5),
        degree_to_midi(root_midi, 4),
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

### How this maps to the real repo

The real generator in this repository does the same job, but in a more complete way:

- `song/theory.py` stores the musical constants and scale mappings
- `song/builder.py` chooses the seed-driven progression, register, and arc
- `song/renderer.py` turns that song state into bar-by-bar audio
- `instruments/` and `synth/` actually synthesize the sound

If you want to understand the real implementation, start there.

### Procedural Strudel example

You can also express the same generation idea directly in Strudel.

```javascript
let scale = "c:minor"

let bass = note("0 2 -2 -1")
  .scale(scale)
  .s("tb303")
  .lpf(1000)

let lead = note("4 5 3 2 ~ 6 5 4")
  .scale(scale)
  .s("sawtooth")
  .delay(0.5)

let pad = note("[c2,eb3,g3] [c2,f3,ab3] [c2,g3,bb3] [c2,eb3,g3]")
  .s("supersaw")
  .slow(4)
  .room(0.8)

bass.stack(lead).stack(pad)
```

### Can this be the basis for procedural trance generation?

Yes.

The tutorial is not just a list of notes. It is already an algorithm for building trance material:

- choose one minor key
- reduce the note pool to safe scale degrees
- use octave displacement to make the bass move
- write the lead as a repeatable call/response phrase
- keep the pad anchored to a pedal tone while the upper notes shift
- let the rhythm breathe with rests, delays, and a repeating drum grid

That means the tutorial can be turned into procedural music generation by making the note choices, octave shifts, rhythm patterns, and chord changes deterministic rules instead of manual editing.

### The actual algorithm from the tutorial chain

This is not really a "raw Strudel makes perfect trance" story. The useful algorithm is the compositional one.

The basic idea is:

1. pick a scale, usually minor
2. choose a root note
3. generate a bassline from a short degree pattern
4. generate a lead from a 5/6/7 call-response phrase
5. generate a pad from pedal-tone chords
6. repeat those structures across bars with small variations
7. add rhythm and movement with drum grids, delays, and amplitude shaping

That is the part that can be automated.

### Practical pseudocode

```python
def build_trance_song(seed: str) -> dict:
    scale = choose_minor_scale(seed)
    root = choose_root(seed)

    bass_pattern = [0, 2, -2, -1]          # root, 3rd, 6th down, 7th
    lead_pattern = [4, 5, 3, 2, 6, 5, 4]   # call / response / return
    pad_chords = [
        [0, 2, 4],
        [0, 3, 5],
        [0, 4, 6],
        [0, 2, 4],
    ]

    drums = {
        "kick": [0, 4, 8, 12],
        "hats": [2, 6, 10, 14],
        "clap": [4, 12],
    }

    arrangement = {
        "intro": 16,
        "groove": 16,
        "breakdown": 16,
        "buildup": 16,
        "drop": 16,
    }

    return {
        "scale": scale,
        "root": root,
        "bass": bass_pattern,
        "lead": lead_pattern,
        "pad": pad_chords,
        "drums": drums,
        "arrangement": arrangement,
    }
```

### A Strudel version of the algorithmic idea

This is the clean procedural sketch: not a final production mix, but a direct expression of the compositional rules.

```javascript
let scale = "c:minor"

let bass = note("0 2 -2 -1")
  .scale(scale)
  .s("tb303")
  .lpf(1000)

let lead = note("<4 5 3 2 6 5 4>")
  .scale(scale)
  .s("sawtooth")
  .delay(0.5)

let pad = note("[c2,eb3,g3] [c2,f3,ab3] [c2,g3,bb3] [c2,eb3,g3]")
  .s("supersaw")
  .slow(4)
  .room(0.8)

let drums = s("bd hh bd hh cp hh bd hh")

stack(drums, bass, lead, pad)
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
- keep the pad simple and slow
- let the root note anchor the harmony
- use a major-flavoured chord moment for lift
- do not overcomplicate the progression

If it sounds too plain, add motion.
If it sounds too busy, remove notes.

That is a lot of trance production in one sentence.

---

## 11. Listening guide

When you listen back, focus on these questions:

- Do I hear one clear home note?
- Does the bass move in jumps instead of chromatic wandering?
- Does the lead feel like a memorable phrase?
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
- a held root underneath slow-moving harmony

That is the core of the video and the procedural version all at once.
