# Listening Guide — Trance Synthesis Ear Training

A reference for what to listen for, vocabulary, and WAV samples you can use as benchmarks.
All paths are relative to the repo root.

---

## The golden reference

`research/reference_audio/sa_pad_harmonic_reference.wav`

Extracted from Switch Angel session `3fpx7Scysw4` using HPSS (harmonic-percussive source
separation). This is the target sound. Every tuning decision is validated against it.

---

## Vocabulary

### Register
**What it means:** How high or low the fundamental pitches are. Think of it as where on a piano keyboard the notes are being played.

**How to hear it:** A low-register pad sounds deep and chest-resonating. A high-register pad sounds more like a keyboard chord in the middle octaves.

**How we measure it:** Spectral centroid — the "centre of gravity" of all the frequencies. SA's pad centroid is ~129 Hz, which sits in the deep bass range.

**What goes wrong:** If the pad notes are set an octave too high, the centroid shifts up and the pad sounds "higher" and thinner than SA's. We had this bug — `ROOT_MIDI - 12` gave centroid 192 Hz; dropping to `ROOT_MIDI - 24` brings it to 116 Hz, close to SA's 129 Hz.

---

### Brightness
**What it means:** How much high-frequency harmonic content is audible above the fundamental notes. A dark pad has almost no energy above 500 Hz. A bright pad has lots — it sounds harsh, cutting, or "harsh."

**How to hear it:** Close your eyes and imagine the sound has a colour. Dark pads are deep brown or black. Bright pads are white or yellow.

**How we measure it:** Spectral rolloff — the frequency below which 95% of the signal's energy sits. SA's pad rolloff is ~447 Hz. Also the percentage of energy in the 200–600 Hz band (SA = 13%).

**What goes wrong:** The original pad used a 1-pole (6 dB/octave) LP filter instead of a 2-pole (12 dB/octave). This let almost all harmonics through. The pad sounded like a wall of noise because none of the brightness was removed.

**Filter cutoff:** Controlled by `cutoff_slider` in `SupersawPad`. The formula is `(slider × 12)^4` Hz.
- slider=0.50 → 1296 Hz (too bright, our original bug)
- slider=0.38 → 432 Hz (current, chosen by ear — see test files below)
- slider=0.36 → 348 Hz (darker, also tested)

**Reference files:**
- `research/reference_audio/sa_pad_harmonic_reference.wav` — SA's dark pad (target)
- `research/reference_audio/pad_stage1_osc_filter_only.wav` — our pad at slider=0.38, no gate/reverb (brighter than SA, centroid 176 Hz)
- `research/reference_audio/pad_stage3_full_chain.wav` — **approved full chain** (filter + gate + reverb), centroid 115 Hz vs SA's 129 Hz ✓

---

### Gate speed (trancegate)
**What it means:** The pad doesn't just play at a constant volume — it pulses in and out rhythmically. The gate speed controls how many times per bar it completes one full in-out cycle.

**How to hear it:** Count the "waves" — how many times the sound swells up and fades down in one bar (about 1.7 seconds at 138 BPM). More waves = faster gate = shorter cycle. SA's pad has a long, slow wave.

**How we measure it:** We take the amplitude envelope of the signal and FFT it to find the dominant modulation frequency. SA's dominant gate frequency is ~0.40 Hz = one full cycle every 2.5 seconds = ~0.69 cycles/bar.

**Parameters:** `speed` in `trancegate()`. Higher = faster pulsing.

**Reference files — listen in order, SA first:**
- `research/reference_audio/sa_pad_harmonic_reference.wav` — SA reference (~0.69 cycles/bar, 2.5s cycle)
- `research/reference_audio/gate_speed_069_2s5_cycle.wav` — our pad at speed=0.69 (matches SA measurement)
- `research/reference_audio/gate_speed_100_1s7_cycle.wav` — our pad at speed=1.0 (1.7s cycle)
- `research/reference_audio/gate_speed_150_1s2_cycle.wav` — our pad at speed=1.5 (current default, 1.2s cycle)

**Status:** Confirmed correct. SA's own code says `.trancegate(1.5, 45, 1)` — speed=1.5 is right. The HPSS-extracted reference made it sound slower due to source separation smearing; don't use the extracted file to judge gate speed.

---

## Tuning methodology

When comparing our sound to SA's reference, always:

1. Play SA's reference first.
2. Play our candidate immediately after.
3. Describe the difference using the vocabulary above.
4. Measure the difference with the spectral tools (centroid, rolloff, band energy).
5. Change ONE parameter at a time.
6. Record the result here.

---

## Parameters tuned so far

| Parameter | Bug | Fix | How confirmed |
|---|---|---|---|
| LP filter order | 1-pole (6 dB/oct) — barely filtered anything | 2-pole (12 dB/oct) | Spectral analysis: 46% energy in 600–1200 Hz dropped to 1% |
| Pad register (root octave) | `ROOT_MIDI - 12` → centroid 192 Hz | `ROOT_MIDI - 24` → centroid 116 Hz | Measured against SA centroid 129 Hz; confirmed by ear |
| Filter cutoff | slider=0.50 (1296 Hz) — too bright | slider=0.38 (432 Hz) | A/B ear test vs SA reference; 0.38 preferred over 0.36 |
| Voicing offsets | `[0, -14, -21]` — doublings go subsonic at A1 register | `[0]` — root only | Subsonic doublings add inharmonic energy in audible range |
| Gate speed | 1.5 cycles/bar | 1.5 cycles/bar (unchanged) | SA's code explicitly says `.trancegate(1.5, 45, 1)` — confirmed correct |
| Kick decay | decay_s=0.25 — long ring/echo | decay_s=0.12 | Old kick had audible "echo" tail not present in SA. Confirmed by ear. |
| Kick pitch floor | 80 Hz — too high, never reaches deep sub | 50 Hz | TR-909 reference measured: floor ~50 Hz |
| Kick pitch start | 180 Hz — too low at onset | 285 Hz (floor + 235) | TR-909 reference measured: onset ~285 Hz |
| Kick pitch decay | 50 ms tau — too slow, sounds acoustic | 31 ms tau | TR-909 zero-crossing measurement: tau = 31 ms. Faster sweep = more electronic. |
