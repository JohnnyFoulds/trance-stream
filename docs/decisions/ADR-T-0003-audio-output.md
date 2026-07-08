# ADR-T-0003 — Audio output uses direct PCM via sounddevice (DJ-compatible)

**Status:** Accepted
**Date:** 2026-07-08

## Context

The script must stream audio continuously to the system output device (FR-1),
participate in the `stream_dj.py` crossfade ecosystem (BR-5), and remain
self-contained with no external audio routing dependencies (NFR-1).

Two output architectures were evaluated:

**Option A — Direct PCM via sounddevice (blocking writes)**
Same approach as `ca_synth.py` and `piano_stream.py`. Write `samples_per_step`
float32 samples to a `sounddevice.OutputStream` each step. All synthesis happens
in the main loop; no threads.

**Option B — JACK / PortAudio routing**
Write to a named audio port; let the OS route to speakers or DAW. More flexible
for studio use but requires JACK or Pipewire server configuration.

## Decision

Use **direct PCM via sounddevice (Option A)**, identical to the existing
`ca_synth.py` and `piano_stream.py` pattern. This is non-negotiable for
DJ compatibility (NFR-3).

Output specification:
- Sample rate: 44,100 Hz (constant `SAMPLE_RATE`)
- Channels: 2 (stereo — see below)
- Format: float32

**Stereo output (unlike piano_stream):** Trance requires stereo for the
characteristic supersaw width. The per-oscillator panning trick (odd oscillators
panned slightly left, even slightly right) produces the stereo spread. Output
is therefore 2-channel float32, not mono. The `sounddevice.OutputStream` is
opened with `channels=2`.

Each voice's stereo position:
- Kick: centre (L=R)
- Bass: centre-wide (slight L/R spread from detuning)
- Lead: wide stereo (oscillators spread ±30° from centre)
- Arp: narrow stereo or mono
- Pad: full stereo (oscillators spread ±45° from centre)

The DJ IPC protocol (flag-file fade-out, `--fade_in`) is inherited unchanged
from `ca_synth.py` and `piano_stream.py`. The stereo channel count does not
affect the IPC protocol.

## Motivation

**DJ compatibility is non-negotiable (NFR-3).** The flag-file IPC and
`sounddevice` blocking-write model are shared infrastructure. Changing the
output architecture would break the DJ crossfade system.

**Stereo is required for the genre.** A mono supersaw lead sounds thin. The
width comes from the slight amplitude and phase differences between detuned
oscillators at slightly different pan positions. Mono output would fail BR-1
for any listener familiar with trance production.

**sounddevice stereo is trivial.** `channels=2` adds negligible complexity —
the mixed buffer is shape `(samples_per_step, 2)` instead of
`(samples_per_step,)`. The blocking write API is identical.

## Consequences

**Enables:**
- Stereo supersaw width (BR-1)
- DJ compatibility (BR-5, NFR-3)
- Self-contained synthesis without external audio routing

**Rules out:**
- JACK / Pipewire routing (not needed; adds setup complexity)
- Multi-bus mixing (single stereo output bus only)

**Watch for:**
- `sounddevice.OutputStream(channels=2)` requires the write buffer to be
  shape `(N, 2)`, not `(N,)`. All voice mix buffers must be 2-column arrays.
  The `mix_and_limit()` function must handle 2-channel input.
- Mono fallback: if `sounddevice` reports `max_output_channels < 2`, fall
  back to mono with a warning to stderr. This handles headless/CI environments.
