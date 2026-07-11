# Sidequest: "Hey Angel…" Style Generator

**Branch**: `sidequest/pluck-arp-analysis`  
**Source track**: https://www.youtube.com/shorts/2o9Riel8iCg  
**Analysis doc**: `research/analysis/hey_angel_analysis.md`

---

## What we're trying to do

"Hey Angel…" has a distinctly different character from the main trance-stream generator output, even though it's the same artist (Switch Angel) and the same root (G1, 50Hz). This sidequest figures out what those differences are and how to reproduce them procedurally.

The track starts at ~4s with the key elements in place:
- A **slow chromatic glide melody** that descends one tritone per bar
- A **high bright pluck** in the E5 register with a fast filter-close on attack
- A **portamento bass** that snaps from F2 back to G1 with a whoosh
- Heavy **sidechain pump** locked to half-note kicks
- **Half-time feel** at ~138 BPM (groove feels like 70 BPM but grid is 138)

None of these are in the current generator. The goal is to add them.

---

## Goals

### 1. Measure and confirm synthesis targets
- [x] Download and analyse audio (`research/reference_audio/hey_angel.wav`)
- [x] Confirm BPM (~138), key (G Dorian), and arrangement structure
- [x] Measure sidechain pump depth (-11dB peak, -7.7dB average)
- [x] Measure bass portamento rate (~120 sem/sec)
- [x] Measure melody glide rate (~15 sem/sec)
- [x] Characterise high pluck timbre (filter-burst, 660Hz + 1300Hz only)

### 2. Implement the new synthesis elements
- [ ] **Portamento bass** — G1(quarter) F2(8th) sweep-back(8th) pattern with `portamento ~0.1s`
- [ ] **Legato melody** — mono lead with `portamento 0.065s`, descends C4→F#3 over 1 bar
- [ ] **High pluck voice** — filtered oscillator, fast VCF burst (opens/closes in 25ms on attack), E5 register, long sustain
- [ ] **Sidechain** — deepen duck ratio in generator from current 0.08 to target -11dB (~0.28 min ratio)

### 3. Validate against the reference
- [ ] Spectral centroid of high pluck output: should start at ~2500Hz, fall to ~1600Hz in 25ms
- [ ] Bass portamento: measure pitch sweep rate in output, confirm ~120 sem/sec
- [ ] Sidechain depth: measure RMS trough/peak ratio, confirm ~0.28 minimum
- [ ] BPM grid: 16th note at ~108ms (138 BPM)

### 4. Wire into the procedural generator
- [ ] Add `hey_angel_style` as a configurable arrangement mode in `trance_stream_v3.py`
- [ ] Keep the existing 11-stage arrangement intact; this is an alternate voicing set

---

## Key measurements (from analysis)

| What | Measured value |
|---|---|
| BPM | ~138 (half-time feel, kick on half-notes) |
| Key | G Dorian (G A Bb C D E F) |
| Melody portamento | 15 sem/sec (slow continuous glide, C4→F#3 per bar) |
| High pluck frequency | E5 = 660Hz |
| High pluck brightness decay | 2500Hz → 1600Hz in 25ms |
| Bass upper note | F2 = 87Hz (flat-7th) |
| Bass portamento speed | 120–130 sem/sec (fast snap back to G1) |
| Sidechain duck (mean) | -7.7 dB |
| Sidechain duck (peak) | -11.1 dB |
| Root note | G1 = 50Hz (same as existing generator) |

---

## What's NOT in scope
- Vocals or voice samples
- Matching the exact SA reverb/master chain (that's a separate sidequest)
- Reproducing the exact 32-second structure — we want the groove elements for procedural use
