# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Audio-to-MIDI conversion and MIDI analysis using librosa + pretty_midi.

Uses librosa's PYIN algorithm for monophonic pitch tracking (bass/lead stems)
and chroma features for polyphonic stems (pad/other).

PYIN is the right choice for electronic music: it's purely mathematical
(no neural network), accurate to ±0.1 semitone, and designed for clean
pitched audio. Chroma gives pitch-class distribution for polyphonic content.

Usage::

    from tools.audio_to_midi import audio_to_midi, midi_to_analysis
    midi_path = audio_to_midi("bass.wav", "bass.mid")
    analysis = midi_to_analysis("bass.mid", bpm=140.0)

CLI::

    python tools/audio_to_midi.py bass.wav --out bass.mid --bpm 140 --mono
"""
import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

try:
    import numpy as np
except ImportError:
    sys.exit("numpy required: pip install numpy")

try:
    import librosa
except ImportError:
    sys.exit("librosa required: pip install librosa")

try:
    import pretty_midi
except ImportError:
    sys.exit("pretty_midi required: pip install pretty_midi")

try:
    import mido
except ImportError:
    sys.exit("mido required: pip install mido")


NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

# G natural minor scale pitch classes (0-indexed from C)
G_MINOR_PCS = {7, 9, 10, 0, 2, 3, 5}  # G A Bb C D Eb F


def midi_note_to_name(note: int) -> str:
    return f"{NOTE_NAMES[note % 12]}{note // 12 - 1}"


def audio_to_midi_mono(
    wav_path: str,
    out_path: str,
    bpm: float = 140.0,
    onset_threshold: float = 0.5,
    min_note_length_ms: float = 50.0,
) -> str:
    """Convert monophonic audio to MIDI using PYIN pitch detection.

    Best for: bass stem, lead stem — clean monophonic pitched audio.
    Returns path to written MIDI file.
    """
    y, sr = librosa.load(wav_path, sr=None, mono=True)

    # PYIN: probabilistic YIN — most accurate monophonic pitch detector
    # fmin/fmax tuned for bass (41-500Hz) or lead (200-2000Hz)
    f0, voiced_flag, voiced_prob = librosa.pyin(
        y, sr=sr,
        fmin=librosa.note_to_hz("E1"),   # 41 Hz — below lowest bass note
        fmax=librosa.note_to_hz("C7"),   # 2093 Hz — above highest lead note
        frame_length=2048,
        hop_length=512,
    )

    hop_s = 512 / sr
    min_note_frames = int(min_note_length_ms / 1000 / hop_s)

    # Convert f0 to MIDI notes, grouping consecutive same-pitch frames into notes
    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    instrument = pretty_midi.Instrument(program=0, name=Path(wav_path).stem)

    prev_midi = None
    note_start = None
    frame_count = 0

    for i, (freq, voiced) in enumerate(zip(f0, voiced_flag)):
        t = i * hop_s

        if voiced and freq is not None and not math.isnan(freq):
            midi_note = int(round(librosa.hz_to_midi(freq)))
            midi_note = max(0, min(127, midi_note))
        else:
            midi_note = None

        if midi_note != prev_midi:
            # Close previous note
            if prev_midi is not None and note_start is not None and frame_count >= min_note_frames:
                note = pretty_midi.Note(
                    velocity=80,
                    pitch=prev_midi,
                    start=note_start,
                    end=t,
                )
                instrument.notes.append(note)
            # Start new note
            note_start = t if midi_note is not None else None
            frame_count = 0
            prev_midi = midi_note
        else:
            frame_count += 1

    # Close final note
    if prev_midi is not None and note_start is not None and frame_count >= min_note_frames:
        t_end = len(f0) * hop_s
        note = pretty_midi.Note(velocity=80, pitch=prev_midi,
                                 start=note_start, end=t_end)
        instrument.notes.append(note)

    pm.instruments.append(instrument)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    pm.write(out_path)
    return out_path


def audio_to_midi_chroma(
    wav_path: str,
    out_path: str,
    bpm: float = 140.0,
) -> str:
    """Convert polyphonic audio to approximate MIDI using chroma + onset detection.

    Best for: 'other' stem (pad+lead+pulse mixed) — gives pitch-class distribution.
    Not exact notes, but reliable rhythm and harmonic content.
    Returns path to written MIDI file.
    """
    y, sr = librosa.load(wav_path, sr=None, mono=True)

    # Separate harmonic component (suppress percussion for cleaner chroma)
    y_harm = librosa.effects.harmonic(y, margin=8)

    # Chroma — 12 pitch classes, one frame per hop
    hop_length = 512
    chroma = librosa.feature.chroma_cqt(y=y_harm, sr=sr, hop_length=hop_length,
                                          bins_per_octave=36)

    # Onset detection for rhythm
    onset_frames = librosa.onset.onset_detect(y=y, sr=sr, hop_length=hop_length,
                                               units="frames")

    hop_s = hop_length / sr
    beats_per_s = bpm / 60.0
    samples_per_bar = int(sr * 4 * 60 / bpm)

    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    instrument = pretty_midi.Instrument(program=0, name=Path(wav_path).stem)

    # For each onset, find dominant pitch class in surrounding window
    note_duration = 60.0 / bpm / 4  # 16th note duration
    for onset_frame in onset_frames:
        t_start = onset_frame * hop_s
        t_end = t_start + note_duration

        # Average chroma in 2-frame window around onset
        w_start = max(0, onset_frame - 1)
        w_end = min(chroma.shape[1], onset_frame + 3)
        chroma_window = chroma[:, w_start:w_end].mean(axis=1)

        # Top 2 pitch classes (chord approximation — octave 4 = middle)
        top_pcs = np.argsort(chroma_window)[-2:]
        for pc in top_pcs:
            if chroma_window[pc] > 0.3:  # threshold to suppress noise
                midi_note = pc + 60  # map to octave 4
                note = pretty_midi.Note(velocity=60, pitch=midi_note,
                                         start=t_start, end=t_end)
                instrument.notes.append(note)

    pm.instruments.append(instrument)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    pm.write(out_path)
    return out_path


def midi_to_analysis(midi_path: str, bpm: float = 140.0) -> dict:
    """Parse MIDI and return rhythmic, harmonic, and melodic analysis.

    Returns:
      note_histogram     — {midi_note: count}, most frequent notes
      pitch_class_counts — {pc_name: count}, e.g. {"G": 45, "D": 32, ...}
      rhythm_grid        — list[int] of length 16, how many onsets fall on each
                           16th-note position per bar (averaged across all bars)
      interval_sequence  — list[int] of semitone intervals between consecutive notes
      stepwise_pct       — % of intervals that are ±1 or ±2 semitones (stepwise motion)
      in_scale_pct       — % of notes whose pitch class is in G natural minor
      phrase_lengths_bars — estimated phrase lengths (bars between prominent rests)
      total_notes        — total note count
      warnings           — list of quality warnings
    """
    pm = pretty_midi.PrettyMIDI(midi_path)
    beats_per_s = bpm / 60.0
    bar_s = 4.0 / beats_per_s
    sixteenth_s = bar_s / 16

    all_notes = []
    for inst in pm.instruments:
        all_notes.extend(inst.notes)
    all_notes.sort(key=lambda n: n.start)

    if not all_notes:
        return {"total_notes": 0, "warnings": ["No notes found in MIDI"]}

    # Note histogram
    note_counts = Counter(n.pitch for n in all_notes)
    note_histogram = dict(note_counts.most_common(20))

    # Pitch class distribution
    pc_counts = Counter(NOTE_NAMES[n.pitch % 12] for n in all_notes)
    pitch_class_counts = dict(pc_counts.most_common())

    # Rhythm grid — which 16th positions have onsets
    grid = [0] * 16
    bar_count = 0
    if all_notes:
        total_duration = all_notes[-1].end
        bar_count = max(1, int(total_duration / bar_s))
        for note in all_notes:
            bar_pos = (note.start % bar_s) / sixteenth_s
            step = int(round(bar_pos)) % 16
            grid[step] += 1
        # Normalise to per-bar average
        grid = [round(g / bar_count, 2) for g in grid]

    # Interval analysis
    pitches = [n.pitch for n in all_notes]
    intervals = [pitches[i+1] - pitches[i] for i in range(len(pitches) - 1)]
    stepwise_count = sum(1 for iv in intervals if abs(iv) <= 2)
    stepwise_pct = stepwise_count / len(intervals) if intervals else 0.0

    # Scale adherence (G natural minor)
    in_scale = sum(1 for n in all_notes if (n.pitch % 12) in G_MINOR_PCS)
    in_scale_pct = in_scale / len(all_notes) if all_notes else 0.0

    # Phrase lengths (gaps > 0.5 bar = phrase boundary)
    phrase_lengths = []
    phrase_start = all_notes[0].start
    for i in range(1, len(all_notes)):
        gap = all_notes[i].start - all_notes[i-1].end
        if gap > bar_s * 0.5:
            length_bars = (all_notes[i-1].end - phrase_start) / bar_s
            phrase_lengths.append(round(length_bars, 1))
            phrase_start = all_notes[i].start
    # Final phrase
    phrase_lengths.append(round((all_notes[-1].end - phrase_start) / bar_s, 1))

    # Warnings
    warnings = []
    if in_scale_pct < 0.90:
        warnings.append(f"SCALE: only {in_scale_pct:.0%} of notes in G minor "
                        f"(threshold: 90%)")
    if intervals and stepwise_pct < 0.40:
        warnings.append(f"MELODY: only {stepwise_pct:.0%} stepwise motion "
                        f"(threshold: 40% — melody may wander)")

    return {
        "note_histogram": note_histogram,
        "pitch_class_counts": pitch_class_counts,
        "rhythm_grid": grid,
        "interval_sequence": intervals[:50],  # first 50
        "stepwise_pct": round(stepwise_pct, 3),
        "in_scale_pct": round(in_scale_pct, 3),
        "phrase_lengths_bars": phrase_lengths[:20],
        "total_notes": len(all_notes),
        "bar_count": bar_count,
        "warnings": warnings,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wav", help="Input WAV file")
    parser.add_argument("--out", default=None, help="Output MIDI path")
    parser.add_argument("--bpm", type=float, default=140.0)
    parser.add_argument("--mono", action="store_true",
                        help="Use PYIN monophonic pitch detection (bass/lead stems)")
    parser.add_argument("--analyse", action="store_true",
                        help="Print MIDI analysis after conversion")
    args = parser.parse_args()

    out = args.out or str(Path(args.wav).with_suffix(".mid"))

    print(f"Converting {args.wav} → {out} (bpm={args.bpm}, mode={'mono/PYIN' if args.mono else 'poly/chroma'})")

    if args.mono:
        audio_to_midi_mono(args.wav, out, bpm=args.bpm)
    else:
        audio_to_midi_chroma(args.wav, out, bpm=args.bpm)

    print(f"Written: {out}")

    if args.analyse:
        analysis = midi_to_analysis(out, bpm=args.bpm)
        print(f"\nAnalysis:")
        print(f"  Total notes:    {analysis['total_notes']}")
        print(f"  In G minor:     {analysis['in_scale_pct']:.1%}")
        print(f"  Stepwise:       {analysis['stepwise_pct']:.1%}")
        print(f"  Rhythm grid:    {analysis['rhythm_grid']}")
        print(f"  Top pitches:    {list(analysis['note_histogram'].items())[:8]}")
        print(f"  Pitch classes:  {analysis['pitch_class_counts']}")
        if analysis["warnings"]:
            for w in analysis["warnings"]:
                print(f"  WARNING: {w}")


if __name__ == "__main__":
    main()
