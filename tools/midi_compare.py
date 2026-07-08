# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""MIDI comparison: generated output vs Switch Angel reference.

Compares rhythm patterns, pitch content, and harmonic similarity between
a generated MIDI track and SA's extracted reference MIDI.

Usage::

    from tools.midi_compare import compare_midi
    result = compare_midi("generated/kick.mid", "reference/drums.mid")
    print(result["rhythm_similarity"])  # 0.0–1.0

CLI::

    python tools/midi_compare.py generated.mid reference.mid --bpm 140
"""
import argparse
import math
import sys
from collections import Counter
from pathlib import Path

try:
    import numpy as np
except ImportError:
    sys.exit("numpy required: pip install numpy")

try:
    import pretty_midi
except ImportError:
    sys.exit("pretty_midi required: pip install pretty_midi")

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
G_MINOR_PCS = {7, 9, 10, 0, 2, 3, 5}  # G A Bb C D Eb F


def _load_notes(midi_path: str) -> list:
    pm = pretty_midi.PrettyMIDI(midi_path)
    notes = []
    for inst in pm.instruments:
        notes.extend(inst.notes)
    notes.sort(key=lambda n: n.start)
    return notes


def _rhythm_grid(notes: list, bpm: float, n_steps: int = 16) -> list[float]:
    """Return per-16th-note onset density, averaged across all bars."""
    if not notes:
        return [0.0] * n_steps
    bar_s = 4.0 * 60.0 / bpm
    step_s = bar_s / n_steps
    total_duration = notes[-1].end
    n_bars = max(1, total_duration / bar_s)
    grid = [0] * n_steps
    for note in notes:
        pos = (note.start % bar_s) / step_s
        step = int(round(pos)) % n_steps
        grid[step] += 1
    return [g / n_bars for g in grid]


def _pitch_class_vector(notes: list) -> np.ndarray:
    """Return a 12-element pitch-class histogram (normalised)."""
    vec = np.zeros(12)
    for n in notes:
        vec[n.pitch % 12] += 1
    total = vec.sum()
    return vec / total if total > 0 else vec


def compare_midi(generated_path: str, reference_path: str, bpm: float = 140.0) -> dict:
    """Compare generated MIDI against SA reference MIDI.

    Returns:
      rhythm_similarity  — cosine similarity of 16th-note onset grids (0–1)
      pitch_similarity   — cosine similarity of pitch-class histograms (0–1)
      note_overlap_pct   — % of generated pitch classes that appear in reference
      key_match          — True if both files' top pitch classes are in G minor
      gen_stats          — summary of generated file
      ref_stats          — summary of reference file
      warnings           — list of specific mismatches
    """
    gen_notes = _load_notes(generated_path)
    ref_notes = _load_notes(reference_path)

    warnings = []

    if not gen_notes:
        warnings.append("Generated MIDI has no notes")
        return {"rhythm_similarity": 0.0, "pitch_similarity": 0.0,
                "note_overlap_pct": 0.0, "key_match": False,
                "warnings": warnings}

    # Rhythm grids
    gen_grid = np.array(_rhythm_grid(gen_notes, bpm))
    ref_grid = np.array(_rhythm_grid(ref_notes, bpm))

    def cosine_sim(a, b):
        denom = (np.linalg.norm(a) * np.linalg.norm(b))
        return float(np.dot(a, b) / denom) if denom > 0 else 0.0

    rhythm_sim = cosine_sim(gen_grid, ref_grid)

    # Pitch class analysis
    gen_pc = _pitch_class_vector(gen_notes)
    ref_pc = _pitch_class_vector(ref_notes)
    pitch_sim = cosine_sim(gen_pc, ref_pc)

    # Note overlap: pitch classes that appear in both
    gen_active_pcs = set(i for i, v in enumerate(gen_pc) if v > 0.02)
    ref_active_pcs = set(i for i, v in enumerate(ref_pc) if v > 0.02)
    overlap = gen_active_pcs & ref_active_pcs
    note_overlap_pct = len(overlap) / len(gen_active_pcs) if gen_active_pcs else 0.0

    # Key match: do both tracks' dominant pitch classes fall in G minor?
    gen_top_pcs = set(np.argsort(gen_pc)[-4:])
    ref_top_pcs = set(np.argsort(ref_pc)[-4:])
    gen_in_key = len(gen_top_pcs & G_MINOR_PCS) / len(gen_top_pcs) if gen_top_pcs else 0
    key_match = gen_in_key >= 0.75

    # Warnings
    if rhythm_sim < 0.5:
        gen_steps = [i for i, v in enumerate(gen_grid) if v > 0.1]
        ref_steps = [i for i, v in enumerate(ref_grid) if v > 0.1]
        warnings.append(f"RHYTHM: similarity {rhythm_sim:.2f} < 0.50. "
                        f"Generated fires on steps {gen_steps}, "
                        f"reference on steps {ref_steps}")
    if pitch_sim < 0.5:
        gen_notes_str = [NOTE_NAMES[i] for i in sorted(gen_active_pcs)]
        ref_notes_str = [NOTE_NAMES[i] for i in sorted(ref_active_pcs)]
        warnings.append(f"PITCH: similarity {pitch_sim:.2f} < 0.50. "
                        f"Generated uses {gen_notes_str}, "
                        f"reference uses {ref_notes_str}")
    if not key_match:
        dominant_pc = NOTE_NAMES[int(np.argmax(gen_pc))]
        warnings.append(f"KEY: generated dominant pitch class is {dominant_pc}, "
                        f"expected G minor (G, A, Bb, C, D, Eb, F)")

    gen_stats = {
        "total_notes": len(gen_notes),
        "active_steps": [i for i, v in enumerate(gen_grid) if v > 0.1],
        "dominant_pc": NOTE_NAMES[int(np.argmax(gen_pc))],
    }
    ref_stats = {
        "total_notes": len(ref_notes),
        "active_steps": [i for i, v in enumerate(ref_grid) if v > 0.1],
        "dominant_pc": NOTE_NAMES[int(np.argmax(ref_pc))],
    }

    return {
        "rhythm_similarity": round(rhythm_sim, 3),
        "pitch_similarity": round(pitch_sim, 3),
        "note_overlap_pct": round(note_overlap_pct, 3),
        "key_match": key_match,
        "gen_stats": gen_stats,
        "ref_stats": ref_stats,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("generated", help="Generated MIDI file")
    parser.add_argument("reference", help="Reference MIDI file")
    parser.add_argument("--bpm", type=float, default=140.0)
    args = parser.parse_args()

    result = compare_midi(args.generated, args.reference, bpm=args.bpm)
    print(f"Rhythm similarity:  {result['rhythm_similarity']:.3f}")
    print(f"Pitch similarity:   {result['pitch_similarity']:.3f}")
    print(f"Note overlap:       {result['note_overlap_pct']:.1%}")
    print(f"Key match (Gm):     {result['key_match']}")
    print(f"Generated:  notes={result['gen_stats']['total_notes']}  "
          f"steps={result['gen_stats']['active_steps']}  "
          f"dominant={result['gen_stats']['dominant_pc']}")
    print(f"Reference:  notes={result['ref_stats']['total_notes']}  "
          f"steps={result['ref_stats']['active_steps']}  "
          f"dominant={result['ref_stats']['dominant_pc']}")
    if result["warnings"]:
        print("\nWarnings:")
        for w in result["warnings"]:
            print(f"  {w}")


if __name__ == "__main__":
    main()
