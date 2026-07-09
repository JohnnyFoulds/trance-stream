#!/usr/bin/env python3
"""Download and save the Bad Apple!! MIDI reference file.

Source: https://github.com/Handhule90/badapple-midi
Tracks: Drums, sub bass, synth 1, synth 2, vocals, guitar, arp, bass 1, bass 2, perc 1, perc 2
Tempo:  138 BPM

Run once to (re)populate research/reference_audio/midi/bad_apple.mid:
    python tools/fetch_bad_apple_midi.py
"""
import pathlib
import urllib.request

URL  = "https://raw.githubusercontent.com/Handhule90/badapple-midi/main/badapple!!midifull.mid"
DEST = pathlib.Path(__file__).parent.parent / "research/reference_audio/midi/bad_apple.mid"


def main() -> None:
    DEST.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading Bad Apple!! MIDI from GitHub…")
    urllib.request.urlretrieve(URL, DEST)
    size = DEST.stat().st_size
    print(f"Saved → {DEST}  ({size:,} bytes)")


if __name__ == "__main__":
    main()
