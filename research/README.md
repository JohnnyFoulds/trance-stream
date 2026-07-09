# Research: Switch Angel Style Analysis

This directory contains all primary research materials used to understand Switch Angel's
music and guide the procedural generator in `trance_stream.py`.

**Goal:** Extract ground truth about her synthesis parameters, drum patterns, arrangement
structures, and musical vocabulary from her live-coding YouTube videos, where the Strudel
REPL is visible and changes in real time as the music evolves.

---

## Directory Structure

```
research/
  videos/          — downloaded source videos (not committed to git — see .gitignore)
  extracted/       — OCR output per video: frame PNGs + code.jsonl + summary.md
  analysis/        — derived analysis: patterns, parameters, vocabulary
  docs/            — written findings (also linked from ../docs/)
```

---

## Reproducibility

All steps are scripted. To reproduce from scratch:

### 1. Download videos

```bash
python tools/download_videos.py
```

Downloads the canonical set of Switch Angel live-coding trance videos from YouTube.
Video IDs and metadata are hardcoded in `tools/download_videos.py` for exact reproducibility.
Output: `research/videos/`

### 2. Extract Strudel code snapshots

```bash
python tools/extract_strudel_code.py research/videos/*.webm --out research/extracted
```

For each video:
- Extracts frames at 2 fps via ffmpeg
- Detects frames where the Strudel REPL is visible (dark background heuristic)
- Detects code changes between successive REPL frames (pixel diff threshold)
- OCRs each changed frame with Tesseract
- Writes `research/extracted/<video_id>/code.jsonl` and `summary.md`

Output: `research/extracted/`

### 3. Analyse extracted code

```bash
python tools/analyse_strudel_code.py research/extracted/*/code.jsonl \
    --out research/analysis/patterns.json
```

Parses OCR'd Strudel code across all videos, extracts:
- Synthesis parameters (supersaw detune, filter cutoffs, orbits)
- Drum patterns (kick, snare, hat steps)
- Trance gate patterns
- Chord progressions and scales
- Arrangement structures (what gets added/removed when)

Output: `research/analysis/`

### 4. Update generator

Findings from step 3 inform constants and logic in `trance_stream.py`.
Every parameter change should cite a video ID and timestamp from `code.jsonl`.

---

## Source Videos

| ID | Title | Duration | Priority |
|---|---|---|---|
| `3fpx7Scysw4` | Coding Trance IV | 6m06s | High |
| `-pDO2RhcGhM` | Coding Trance Music From Scratch YET AGAIN | 8m38s | High |
| `iu5rnQkfO6M` | Coding Trance Music from Scratch (Again) | 5m02s | High |
| `vn9VDbacUgQ` | Coding Trance (Official) | 4m39s | High |
| `GWXCCBsOMSg` | Coding Trance Music (Full Narrated) | 6m19s | High |

Channel: https://www.youtube.com/@Switch-Angel

---

## Dependencies

```
pip install opencv-python pytesseract Pillow numpy yt-dlp
brew install tesseract ffmpeg   # macOS
```

See `tools/requirements-research.txt` for pinned versions.

---

## strudel_debug.html

Browser-based debug utility. Runs Switch Angel's actual Strudel pad code in the browser
so you can hear the target sound directly and compare against what `bad_apple_cover.py` generates.

```bash
cd research
python3 -m http.server 8765
# open http://localhost:8765/strudel_debug.html
```

Must be served over HTTP (not `file://`) because AudioWorklets require a secure context.

**Sections:**

| # | What it plays | Why |
|---|---------------|-----|
| 1 | SA's pad alone — G minor, no kick | Ground truth for pad timbre |
| 2 | SA's pad + kick — G minor | Matches t=40s of video GWXCCBsOMSg |
| 3 | Pad in A minor (our key) | Edit and play to tune parameters live |

Edit any textarea and hit Play again to hear the change immediately.
No dependencies installed locally — loads `@strudel/web@latest` from unpkg at runtime.

---

## reference_audio/

Analysis-only audio samples. **Never used as playback assets in the generator.**

| File | Source | Purpose |
|------|--------|---------|
| `tr909_kick_reference.wav` | audiorealism.se BassDrum909-tune100-attack100-decay025.wav | TR-909 kick parameter fitting |
