# Regression Report: bad_apple_cover.py — Trancegate Binary Gate

**Date raised:** 2026-07-10
**Branch:** sidequest/pluck-arp-analysis
**Current HEAD:** 6f00b06
**Status:** Documented, fix deferred pending reference baseline

---

## Symptom

`bad_apple_cover.py` sounds choppy and stuttery after commit `64b58a4`. The pad and lead
have harsh amplitude clicks throughout every bar instead of the smooth swelling texture they
had at the time the cover was written (`175bbba`).

---

## Reference audio

`research/reference_audio/bad_apple_reference_175bbba.wav`

Rendered from commit `175bbba` ("Add Bad Apple cover, TR-909 kick fit, PolyBLEP oscillator,
strudel debug utility") — the commit that introduced `bad_apple_cover.py` and the last
known-good state before the regression.

**How to regenerate:**
```bash
git checkout 175bbba
python bad_apple_cover.py --bars 32 --wav research/reference_audio/bad_apple_reference_175bbba.wav
git checkout sidequest/pluck-arp-analysis
```

---

## Root causes

### 1. Binary gate model replaces smooth cosine (commit `64b58a4`)

`synth/envelopes.py trancegate()` was changed from a **smooth raised-cosine** amplitude
envelope to a **hard binary step function**:

| Property | Old (cosine) | New (binary) |
|---|---|---|
| Values | Continuous [0.3, 1.0] | Hard steps: 0.3 or 1.0 only |
| Shape | Sinusoidal, 1.5 cycles/bar | 16 rectangular slots/bar |
| Transitions | Smooth (no clicks) | Hard amplitude snap (click at every transition) |
| Suitable for | Continuous melody lines | Per-slot retriggered notes (SA trance style) |

The binary gate is correct for SA-style trance (notes are retriggered per 16th-note slot,
so the gate acts as a note on/off). It is wrong for `bad_apple_cover.py`, which plays a
continuous melody line — each hard gate transition creates an audible click every ~107ms
(one 16th-note slot at 138 BPM), producing ~10 clicks per bar.

The 5ms crossfade that was briefly added to soften transitions was removed in `4f723d7`
("EXP-001 through EXP-016"), making the clicks worse.

### 2. BPM mismatch causes gate drift (`bad_apple_cover.py` line 349)

`bad_apple_cover.py` constructs `SupersawPad` without `bpm=`:

```python
# bad_apple_cover.py line 349 — BUG
self._pad = SupersawPad(root_midi=ROOT_MIDI, sr=sr,
                        detune_cents=60.0, room_size=0.7, saw_count=5)
# SupersawPad.__init__ defaults to bpm=140.0
```

The cover runs at 138 BPM (SPB = 76695 samples/bar). But `pad.render()` computes:
```python
spb = samples_per_bar(bpm=self.bpm)  # self.bpm=140.0 → spb=75600, wrong
```

The gate's `bar_index = bar_offset_samples // 75600` miscounts bars, causing the gate
pattern's random seed to advance faster than the beat. After ~70 bars the gate is a full
bar ahead of the kick, and the pad's amplitude pattern drifts out of sync with the beat.

The **lead** does not have this bug — `bad_apple_cover.py` passes `samples_per_bar=spb`
explicitly in the lead's `.render()` call (line ~547), where `spb` is computed correctly
from 138 BPM.

---

## Proposed fix

Add `gate_mode: str = 'binary'` parameter to `SupersawPad.__init__` and `AcidLead.__init__`.
When `gate_mode='cosine'`, use the lifted cosine formula:

```python
gate_period = spb / 1.5   # 1.5 cycles per bar
t = np.arange(n_samples, dtype=np.float32) + bar_offset_samples
phase = 2.0 * np.pi * t / gate_period
gate = (0.3 + 0.7 * (1.0 + np.cos(phase + np.pi)) / 2.0).astype(np.float32)
```

Then in `bad_apple_cover.py`, pass both fixes:
```python
self._pad = SupersawPad(root_midi=ROOT_MIDI, sr=sr,
                        detune_cents=60.0, room_size=0.7, saw_count=5,
                        bpm=BPM, gate_mode='cosine')   # fix both bugs

self._lead = AcidLead(sr=sr, character='smooth', gate_mode='cosine')
```

The default `gate_mode='binary'` preserves current SA trance behaviour — all 213 tests
continue to pass.

---

## How to verify the fix

```bash
# 1. Render with fixed code
python bad_apple_cover.py --bars 32 --wav /tmp/bad_apple_fixed.wav

# 2. Compare spectrogram/RMS against reference
python tools/compare_audio.py \
    research/reference_audio/bad_apple_reference_175bbba.wav \
    /tmp/bad_apple_fixed.wav

# 3. Confirm no test regressions
python -m pytest tests/ --ignore=tests/test_tools/ -q
```

A passing fix should show:
- Smooth RMS envelope on pad/lead (no ~107ms amplitude spikes in the spectrogram)
- No test failures from the `gate_mode` default change
