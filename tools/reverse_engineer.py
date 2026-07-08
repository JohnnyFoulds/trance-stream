# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Phase 0b: Source separation + MIDI extraction pipeline.

Takes Switch Angel's extracted reference WAV clips and:
1. Separates each into stems (drums, bass, other) using Demucs htdemucs_6s
2. Converts each stem to MIDI using librosa PYIN (mono stems) or chroma (poly)
3. Assembles per-stem MIDIs into a single multi-track MIDI file
4. Runs MIDI analysis and writes a human-readable analysis markdown document

Outputs for each video_id:
  research/reference_audio/stems/<video_id>/drums.wav
  research/reference_audio/stems/<video_id>/bass.wav
  research/reference_audio/stems/<video_id>/other.wav
  research/reference_audio/midi/<video_id>/drums.mid
  research/reference_audio/midi/<video_id>/bass.mid
  research/reference_audio/midi/<video_id>/other.mid
  research/reference_audio/midi/<video_id>_full.mid     (multi-track)
  research/reference_audio/midi/<video_id>_analysis.md  (committed)

The stems/ outputs are NOT committed (large, re-derivable).
The midi/ outputs ARE committed (small, high-value, not trivially re-derivable).

Usage::

    python tools/reverse_engineer.py research/reference_audio/3fpx7Scysw4_90s.wav
    python tools/reverse_engineer.py --all

    --all        Process all 5 reference clips
    --skip-sep   Skip stem separation (if already done)
    --skip-midi  Skip MIDI conversion (if already done)
    --bpm        BPM for MIDI timing (default: 140.0)
"""
import argparse
import json
import sys
from pathlib import Path

# Allow importing sibling tools without package install
sys.path.insert(0, str(Path(__file__).parent))

REPO_ROOT = Path(__file__).parent.parent
REF_DIR = REPO_ROOT / "research" / "reference_audio"
STEMS_DIR = REF_DIR / "stems"
MIDI_DIR = REF_DIR / "midi"

VIDEO_IDS = [
    "3fpx7Scysw4",
    "-pDO2RhcGhM",
    "GWXCCBsOMSg",
    "iu5rnQkfO6M",
    "vn9VDbacUgQ",
]

# Which stems to convert to MIDI and how
STEM_MODES = {
    "drums": "mono",   # kick/hihat rhythmic content — PYIN will detect pitch hits
    "bass":  "mono",   # monophonic bass line — PYIN gives accurate notes
    "other": "poly",   # pad+lead+pulse mixed — chroma gives approximate harmony
}


def process_wav(wav_path: Path, bpm: float = 140.0,
                skip_sep: bool = False, skip_midi: bool = False):
    video_id = wav_path.stem.replace("_90s", "")
    print(f"\n{'='*60}")
    print(f"Processing {video_id}")
    print(f"{'='*60}")

    # Demucs outputs to stems/<model>/<input_stem>/
    stem_dir = STEMS_DIR / "htdemucs_6s" / f"{video_id}_90s"
    midi_subdir = MIDI_DIR / video_id
    full_midi_path = MIDI_DIR / f"{video_id}_full.mid"
    analysis_path = MIDI_DIR / f"{video_id}_analysis.md"

    # 1. Stem separation
    if not skip_sep:
        print(f"\n[1/3] Stem separation (Demucs htdemucs_6s)...")
        print(f"      Note: first run downloads ~1GB model to ~/.cache/torch/hub/")
        try:
            from stem_separation import separate_stems
            stems = separate_stems(str(wav_path), str(STEMS_DIR))
            print(f"      Separated into: {list(stems.keys())}")
        except RuntimeError as e:
            print(f"      FAILED: {e}")
            return
    else:
        # Find existing stems
        stems = {}
        for stem_name in STEM_MODES:
            candidate = stem_dir / f"{stem_name}.wav"
            if candidate.exists():
                stems[stem_name] = str(candidate)
        if not stems:
            print(f"      Skipping separation but no stems found in {stem_dir}")
            return
        print(f"\n[1/3] Stem separation: skipped (using existing stems)")

    # 2. MIDI conversion
    midi_subdir.mkdir(parents=True, exist_ok=True)
    midi_paths = {}

    if not skip_midi:
        print(f"\n[2/3] MIDI conversion...")
        from audio_to_midi import audio_to_midi_mono, audio_to_midi_chroma

        for stem_name, mode in STEM_MODES.items():
            stem_wav = stems.get(stem_name)
            if stem_wav is None:
                print(f"      {stem_name}: not found, skipping")
                continue

            out_midi = str(midi_subdir / f"{stem_name}.mid")
            print(f"      {stem_name} ({mode})... ", end="", flush=True)
            try:
                if mode == "mono":
                    audio_to_midi_mono(stem_wav, out_midi, bpm=bpm)
                else:
                    audio_to_midi_chroma(stem_wav, out_midi, bpm=bpm)
                midi_paths[stem_name] = out_midi
                print("ok")
            except Exception as e:
                print(f"FAILED: {e}")
    else:
        print(f"\n[2/3] MIDI conversion: skipped (using existing MIDIs)")
        for stem_name in STEM_MODES:
            p = midi_subdir / f"{stem_name}.mid"
            if p.exists():
                midi_paths[stem_name] = str(p)

    if not midi_paths:
        print("No MIDI files produced, skipping assembly and analysis")
        return

    # 3. Assemble multi-track MIDI
    print(f"\n[3/3] Assembling multi-track MIDI...")
    import mido
    try:
        mid = mido.MidiFile(type=1)
        for stem_name in STEM_MODES:
            midi_path = midi_paths.get(stem_name)
            if midi_path is None:
                continue
            src = mido.MidiFile(midi_path)
            # pretty_midi writes track 0 as metadata; track 1 has the actual notes
            note_track = None
            for t in src.tracks:
                note_ons = sum(1 for m in t if m.type == 'note_on' and m.velocity > 0)
                if note_ons > 0:
                    note_track = t
                    break
            if note_track is None:
                print(f"      {stem_name}: no note events found, skipping")
                continue
            note_track.name = stem_name
            mid.tracks.append(note_track)
            note_count = sum(1 for m in note_track if m.type == 'note_on' and m.velocity > 0)
            print(f"      Added track: {stem_name} ({note_count} notes)")

        if mid.tracks:
            mid.save(str(full_midi_path))
            print(f"      Saved: {full_midi_path}")
    except Exception as e:
        print(f"      Assembly failed: {e}")

    # 4. Analysis
    print(f"\n[+] Running MIDI analysis...")
    from audio_to_midi import midi_to_analysis
    analyses = {}
    for stem_name, midi_path in midi_paths.items():
        try:
            analyses[stem_name] = midi_to_analysis(midi_path, bpm=bpm)
        except Exception as e:
            print(f"      {stem_name} analysis failed: {e}")

    # Write analysis markdown
    _write_analysis_markdown(analysis_path, video_id, analyses, bpm)
    print(f"      Written: {analysis_path}")


def _write_analysis_markdown(path: Path, video_id: str, analyses: dict, bpm: float):
    lines = [
        f"# MIDI Analysis: {video_id}",
        f"",
        f"Source: `research/reference_audio/{video_id}_90s.wav`",
        f"BPM: {bpm}",
        f"Generated by: `tools/reverse_engineer.py`",
        f"",
        f"> **Note on accuracy**: Demucs was designed for acoustic music.",
        f"> In trance: `drums` stem is reliable, `bass` is usable, `other` is approximate.",
        f"> Confirm findings against OCR data in `research/analysis/` before treating as ground truth.",
        f"",
    ]

    for stem_name, analysis in analyses.items():
        lines += [
            f"## {stem_name.capitalize()} stem",
            f"",
            f"- Total notes: {analysis.get('total_notes', 0)}",
            f"- Bars analysed: {analysis.get('bar_count', 0)}",
        ]

        if analysis.get("in_scale_pct") is not None:
            lines.append(f"- In G minor: {analysis['in_scale_pct']:.1%}")
        if analysis.get("stepwise_pct") is not None:
            lines.append(f"- Stepwise motion: {analysis['stepwise_pct']:.1%}")

        # Rhythm grid
        grid = analysis.get("rhythm_grid", [])
        if grid:
            active_steps = [i for i, v in enumerate(grid) if v > 0.1]
            grid_str = " ".join(
                f"[{i}]" if v > 0.1 else " . " for i, v in enumerate(grid)
            )
            lines += [
                f"",
                f"**Rhythm grid (16th-note positions, avg hits/bar):**",
                f"```",
                f"Steps: 0  1  2  3  4  5  6  7  8  9  10 11 12 13 14 15",
                f"       {grid_str}",
                f"```",
                f"Active steps: {active_steps}",
            ]

        # Top pitch classes
        pc = analysis.get("pitch_class_counts", {})
        if pc:
            top_pcs = sorted(pc.items(), key=lambda x: -x[1])[:6]
            lines += [
                f"",
                f"**Dominant pitch classes:** {', '.join(f'{k}({v})' for k,v in top_pcs)}",
            ]

        # Warnings
        if analysis.get("warnings"):
            lines += ["", "**Warnings:**"]
            for w in analysis["warnings"]:
                lines.append(f"- {w}")

        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wav", nargs="?", help="Single WAV file to process")
    parser.add_argument("--all", action="store_true", help="Process all 5 reference clips")
    parser.add_argument("--skip-sep", action="store_true", help="Skip stem separation")
    parser.add_argument("--skip-midi", action="store_true", help="Skip MIDI conversion")
    parser.add_argument("--bpm", type=float, default=140.0)
    args = parser.parse_args()

    if args.all:
        wavs = [REF_DIR / f"{vid}_90s.wav" for vid in VIDEO_IDS]
    elif args.wav:
        wavs = [Path(args.wav)]
    else:
        parser.print_help()
        sys.exit(1)

    for wav in wavs:
        if not wav.exists():
            print(f"WARNING: {wav} not found, skipping")
            continue
        process_wav(wav, bpm=args.bpm,
                    skip_sep=args.skip_sep, skip_midi=args.skip_midi)

    print(f"\nDone. MIDI files in: {MIDI_DIR}")
    print(f"Committed analysis docs:")
    for f in sorted(MIDI_DIR.glob("*_analysis.md")):
        print(f"  {f}")


if __name__ == "__main__":
    main()
