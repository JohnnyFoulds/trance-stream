# Reference Audio Stems

Separated from Switch Angel's YouTube session WAV clips using Demucs `htdemucs_6s`.

## Regenerating

Stems are NOT committed to git (large, re-derivable). To regenerate:

```bash
pip install -r requirements-ml.txt   # downloads ~2GB PyTorch; first run only
python tools/reverse_engineer.py --all
```

This also re-generates the MIDI files and analysis docs in `midi/` — though those
ARE committed and do not need regeneration unless you want to re-run with different settings.

## Known limitations of Demucs on electronic/trance music

Demucs was trained primarily on acoustic music (vocals, drums, bass, guitar).
For Switch Angel's trance tracks, quality varies by stem:

| Stem | Quality | Notes |
|------|---------|-------|
| `drums` | Good | Kick and hihat transients extract cleanly. PYIN pitch detection on drums.wav gives approximately Bb1 (kick fundamental ~58Hz → detected as A#2 due to overtones). Rhythm grid is reliable. |
| `bass` | Moderate | Bass line separates reasonably, but kick sub-bass bleeds in. F dominates pitch content (F is scale degree 7 in G minor — consistent with SA's patterns). ~32% of detected notes fall outside G minor due to bleed. |
| `other` | Poor | Contains pad + lead + pulse + all bleed. The chroma-based MIDI is an approximation of harmonic content only. Do NOT use as ground truth for melody or chord analysis — confirm against OCR data in `research/analysis/`. |
| `vocals` | Empty | No vocal content. |
| `guitar` | Bleed | May contain some synth bleed. |
| `piano` | Bleed | May contain some pad bleed. |

## How to use the MIDI outputs

The per-stem MIDI files in `midi/` are the highest-value outputs:

- **`drums.mid`**: Use rhythm_grid from analysis to verify kick step patterns.
  The confirmed SA kick pattern `[0,4,8,11,14]` should appear as high-density
  steps in the grid. Cross-reference with `research/analysis/switch_angel_vocabulary.md`.

- **`bass.mid`**: Use pitch_class_counts to confirm which notes SA's bass plays.
  F (scale degree 7 in G minor) should dominate. Cross-reference dominant notes
  against SA's confirmed `bline` pattern in the vocabulary doc.

- **`other.mid`**: Use pitch_class_counts only as a rough harmonic guide.
  The `rhythm_grid` is more reliable than note pitches for this stem.

## File structure after regeneration

```
stems/
  htdemucs_6s/
    3fpx7Scysw4_90s/
      drums.wav    bass.wav    other.wav    vocals.wav    guitar.wav    piano.wav
    -pDO2RhcGhM_90s/
      ...
    GWXCCBsOMSg_90s/
      ...
    iu5rnQkfO6M_90s/
      ...
    vn9VDbacUgQ_90s/
      ...
```
