# Pad Tuning Methodology

## Reference file

`research/reference_audio/sa_pad_harmonic_reference.wav`

Extracted from Switch Angel session `3fpx7Scysw4` using HPSS (harmonic-percussive source
separation). This is the ground truth. Every tuning decision is validated against it.

---

## Vocabulary (taught as we go)

**Register** — how high or low the fundamental pitches are.
- Measured by: spectral centroid (Hz) — the "centre of gravity" of the frequency spectrum.
- SA pad centroid: ~129 Hz. That puts the average energy in the deep bass range.
- If the centroid is too high, the pad sounds "higher" and less deep than SA's.

**Brightness** — how much harmonic content is audible above the fundamentals.
- Measured by: spectral rolloff — the frequency below which 95% of the signal's energy sits.
- SA pad rolloff: ~447 Hz. That means almost nothing audible above 450 Hz.
- Also measured by the 200–600 Hz energy band: SA has 13% there.
- If too bright, the pad sounds harsh, cutting, or "noisy" rather than warm and dark.

**Darkness** — the opposite of brightness. A dark pad is heavily low-pass filtered.
- SA's pad: 86% of energy below 200 Hz, 13% in 200–600 Hz, 1% above 600 Hz.
- Controlled by: the LP filter cutoff (`cutoff_slider` in `SupersawPad`).

---

## Tuning process (A/B method)

Always compare against `sa_pad_harmonic_reference.wav` using side-by-side playback:
```
afplay research/reference_audio/sa_pad_harmonic_reference.wav && afplay <candidate>.wav
```

Tune one parameter at a time. After each change, measure with:
```python
fft = np.abs(np.fft.rfft(signal))**2
freqs = np.fft.rfftfreq(len(signal), 1/SR)
centroid   = np.dot(freqs, fft) / fft.sum()
rolloff_95 = freqs[np.searchsorted(np.cumsum(fft)/fft.sum(), 0.95)]
sub200_pct = 100 * fft[freqs < 200].sum() / fft.sum()
band_200_600_pct = 100 * fft[(freqs >= 200) & (freqs < 600)].sum() / fft.sum()
```

SA targets:
| Metric | SA value | Meaning |
|---|---|---|
| Centroid | 129 Hz | pitch centre sits in deep bass |
| Rolloff (95%) | 447 Hz | virtually nothing above 450 Hz |
| Sub-200 Hz | 86% | almost all energy is in the deep bass |
| 200–600 Hz | 13% | a small amount of low-mid warmth |
| 600–1200 Hz | 1% | essentially absent |
| >1200 Hz | 0% | absent |

---

## Parameters found so far

Each decision was made by measuring against SA targets, then confirmed by ear.

| Parameter | Old value | New value | Why |
|---|---|---|---|
| Filter order | `lpf` (1-pole, 6 dB/oct) | `lpf2` (2-pole, 12 dB/oct) | SC's `rlpf` is 2nd-order; 1-pole let all harmonics through = noise wall |
| Pad root octave | `ROOT_MIDI - 12` (A2, 110 Hz) | `ROOT_MIDI - 24` (A1, 55 Hz) | Centroid 192 Hz → 116 Hz; SA is 129 Hz |
| Cutoff slider | 0.50 (1296 Hz) | 0.38 (432 Hz) | 0.36 and 0.38 tested by ear against SA reference; 0.38 chosen. Neither was a perfect match — revisit this with a finer sweep if pad darkness is still wrong after other fixes. |
| Voicing offsets | `[0, -14, -21]` | `[0]` (root only) | At this register -14/-21 go subsonic; their harmonics add unwanted upper-mid energy |

---

## Stage isolation approach

When something sounds wrong, isolate each stage of the signal chain:

1. **Oscillators + filter only** — bypass gate and reverb. Should sound like a held chord.
2. **Add gate** — should add a slow gentle pulse (~1.2s cycle), not change the tone.
3. **Full chain** — add reverb. Should add space, not change brightness or register.

If stage N sounds fine but stage N+1 sounds wrong, the bug is in stage N+1.
