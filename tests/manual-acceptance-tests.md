# TranceStream — Manual Acceptance Tests

| Test ID | Requirement | Procedure | Pass criterion |
| --- | --- | --- | --- |
| T-001 | FR-1, NFR-7 | Run `python trance_stream.py` with no arguments | Stereo audio begins within 2 seconds. Terminal visualiser prints first bar line. No errors. |
| T-002 | BR-1, NFR-7 | Play output to a listener familiar with trance (without telling them what it is) | Listener identifies it as trance music within 15 seconds. Must mention supersaw lead, kick, or "trance" genre. |
| T-003 | FR-2, FR-5 | Run with `--seed foo --bars 8 --out_midi a.mid`, then repeat identically | MIDI files `a.mid` and second run are byte-identical. |
| T-004 | FR-13 | Run `--bars 32 --out_midi kick_test.mid`, import MIDI, inspect kick channel | Kick fires on steps 0, 4, 8, 12 of every bar during Groove/Drop. Zero kick events in Breakdown bars. |
| T-005 | FR-14 | Inspect bass channel of MIDI export | Every bar in Groove/Drop has at least one note on beat 1 (time = bar_start) on the bass channel. All bass notes below MIDI 60. |
| T-006 | FR-15 | Inspect lead channel of MIDI export | No two consecutive lead notes more than 7 semitones apart, except at phrase boundaries. Any interval > 7 at a phrase boundary is followed by a note moving in the opposite direction. |
| T-007 | FR-16 | Run with `--bars 52`, watch terminal visualiser | Phases progress: Intro (bars 1–4), Groove (5–20), Breakdown (21–36), Build-up (37–52), Drop (53–68). Phase label changes on correct bar. |
| T-008 | FR-17 | Listen to lead voice in isolation (mute others if possible) | Lead voice has audible rhythmic gating — 16th-note on/off rhythm over a sustained supersaw. Not a continuous drone. |
| T-009 | FR-18 | Listen to bass voice | After each kick hit, bass volume dips noticeably then recovers within approximately 0.5 seconds. The pumping rhythm is audible. |
| T-010 | FR-9, FR-10 | Start script; after 10 seconds write `fade_<pid>.flag` (use `touch`) | Script begins fade-out within one bar. Audio is silent within 4 bars. Process exits cleanly. MIDI file written if `--out_midi` set. |
| T-011 | NFR-3 | Configure `stream_dj.py` to include `trance_stream.py` as a synth (via symlink `ca_synth_trance.py`); run DJ | DJ launches trance_stream, plays it, crossfades to next synth. No errors or hangs. |
| T-012 | NFR-6 | Run script, observe terminal | No visualiser line exceeds 80 characters. |
| T-013 | FR-8, FR-7 | Run `python trance_stream.py --bars 32 --out_midi test.mid` | Script generates exactly 32 + 4 (fade-out) bars, writes `test.mid`, exits with code 0. MIDI file opens without errors in GarageBand or equivalent. |
| T-014 | BR-3 | Run for 30 minutes | No crash, no audio glitch, no terminal freeze, no memory growth visible in Activity Monitor. |
| T-015 | NFR-4 | Run script; simultaneously run a code editor and screen-capture (OBS or equivalent) | CPU usage for `trance_stream.py` process does not exceed 30% on a modern laptop (M-series Mac or equivalent). |
