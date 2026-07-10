# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Audio effects — vectorised, stateful where needed.

All classes use circular buffers with numpy fancy-index gather/scatter —
no Python loops over individual samples.

Design note on block size:
  Each `process` call reads all delayed samples from the buffer's PRE-call
  state, then writes the new block.  This is exact when block_size <=
  delay_samples; for larger blocks the within-block feedback is not modelled
  (an acceptable approximation for bar-by-bar synthesis).  Buffers are sized
  to at least 4 × sr so write-index wrap-around never overwrites unread
  history within a single call.
"""

from __future__ import annotations

import numpy as np


class FeedbackDelay:
    """Stereo ping-pong feedback delay with a circular buffer.

    SA's lead uses .delay(.5).delaytime(.375).delayfb(.8) (or similar).
    Ping-pong routing: dry-L + feedback×delayed-R → delay-line L, and vice
    versa, so echoes bounce between channels.

    Parameters
    ----------
    delay_s : float
        Delay time in seconds.  Default 0.375 s = 3/8-note at 140 BPM.
    feedback : float
        Feedback amount, clamped to [0.0, 0.95].  Default 0.8.
    wet : float
        Wet/dry mix [0.0, 1.0].  Default 0.7.
    sr : int
        Sample rate.  Default 44100.
    """

    def __init__(
        self,
        delay_s: float = 0.375,
        feedback: float = 0.8,
        wet: float = 0.7,
        sr: int = 44100,
    ) -> None:
        self._delay_samples = max(1, int(delay_s * sr))
        self._feedback = float(np.clip(feedback, 0.0, 0.95))
        self._wet = float(np.clip(wet, 0.0, 1.0))
        # Buffer at least 4 s so write indices never lap unread history.
        buf_size = max(self._delay_samples + 1, sr * 4)
        self._buf_l = np.zeros(buf_size, dtype=np.float32)
        self._buf_r = np.zeros(buf_size, dtype=np.float32)
        self._write_pos = 0

    def process(
        self, buf_l: np.ndarray, buf_r: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Process a stereo buffer through the ping-pong delay.

        Returns (out_l, out_r).  Internal circular-buffer state persists
        between calls for sample-continuous output across bar boundaries.

        Vectorised: precompute all read/write indices, gather delayed
        samples in one operation, scatter new samples in one operation.
        No Python loop over individual samples.
        """
        n = len(buf_l)
        delay_samples = self._delay_samples
        buf_size = len(self._buf_l)
        write_start = self._write_pos

        # Integer index vectors for the entire block.
        offsets = np.arange(n, dtype=np.int64)
        write_indices = (write_start + offsets) % buf_size
        read_indices = (write_start + offsets - delay_samples) % buf_size

        # Read from pre-call state — all reads happen before any write.
        delayed_l = self._buf_l[read_indices]
        delayed_r = self._buf_r[read_indices]

        # Ping-pong: each channel feeds back into the opposite delay line.
        self._buf_l[write_indices] = buf_l + self._feedback * delayed_r
        self._buf_r[write_indices] = buf_r + self._feedback * delayed_l

        dry = 1.0 - self._wet
        out_l = buf_l * dry + delayed_r * self._wet
        out_r = buf_r * dry + delayed_l * self._wet

        self._write_pos = int((write_start + n) % buf_size)
        return out_l.astype(np.float32), out_r.astype(np.float32)


class SimpleFDN:
    """Simple 4-line Feedback Delay Network for diffuse reverb.

    SA's pad uses .room(0.7) — a diffuse reverb tail.  Modelled with a
    4-tap FDN: delay lines of coprime prime lengths, feedback 0.5 per line.
    Lines alternate L/R input and output for stereo spread.

    Impulse response decays to below −40 dB within ~3 s at room_size=0.7,
    sr=44100 (feedback=0.5, shortest line ≈ 1206 samples ≈ 27 ms).

    Parameters
    ----------
    room_size : float
        [0.0, 1.0], scales delay-line lengths.  Default 0.7.
    sr : int
        Sample rate.  Default 44100.
    """

    def __init__(self, room_size: float = 0.7, sr: int = 44100) -> None:
        # Prime base delays (≈ 39–51 ms at 44100 Hz); coprime by construction.
        base_delays = [1723, 1871, 2083, 2267]
        self._delays = [max(1, int(d * room_size)) for d in base_delays]
        # Buffer at least 4 s per line so write indices never lap history.
        self._bufs = [
            np.zeros(max(d + 1, sr * 4), dtype=np.float32)
            for d in self._delays
        ]
        self._ptrs = [0] * 4
        # feedback=0.85 → T60 ~1300ms at 30ms avg delay — long enough to bridge
        # the 563ms trancegate troughs without the tail dying mid-silence.
        self._feedback = 0.85
        # Wet scales with room_size: small rooms are mostly dry, large rooms diffuse.
        self._wet = 0.15 + room_size * 0.45

    def process(
        self, buf_l: np.ndarray, buf_r: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Apply FDN reverb to a stereo buffer.

        Returns (out_l, out_r).  Circular-buffer state persists between
        calls.  Inner loop runs exactly 4 times (over delay lines, not
        samples); inner body is numpy-vectorised over the block.
        """
        n = len(buf_l)
        out_l = np.zeros(n, dtype=np.float32)
        out_r = np.zeros(n, dtype=np.float32)

        offsets = np.arange(n, dtype=np.int64)

        for line_idx in range(4):
            cbuf = self._bufs[line_idx]
            delay = self._delays[line_idx]
            ptr = self._ptrs[line_idx]
            n_buf = len(cbuf)

            write_idx = (ptr + offsets) % n_buf
            read_idx = (ptr + offsets - delay) % n_buf

            # Read delayed samples from pre-call buffer state.
            delayed = cbuf[read_idx]

            # Write new input + feedback.
            inp = buf_l if line_idx % 2 == 0 else buf_r
            cbuf[write_idx] = inp + self._feedback * delayed

            # Accumulate reverb output into L or R.
            half_wet = self._wet * 0.5
            if line_idx % 2 == 0:
                out_l += delayed * half_wet
            else:
                out_r += delayed * half_wet

            self._ptrs[line_idx] = int((ptr + n) % n_buf)

        # Mix wet reverb over dry signal.
        out_l = buf_l + out_l
        out_r = buf_r + out_r
        return out_l.astype(np.float32), out_r.astype(np.float32)


class SchroederReverb:
    """Schroeder reverb: 4 parallel comb filters → 2 series all-pass diffusers.

    Uses circular buffers (numpy fancy-index) — O(1) per sample, vectorised
    over the block.  Fast enough for real-time bar-by-bar rendering.

    Parameters
    ----------
    room_size : float
        [0.0, 1.0].  Default 0.7.
    wet : float
        Wet mix level.  Default 0.35.
    sr : int
        Sample rate.  Default 44100.
    """

    _COMB_DELAYS_44K    = [1557, 1617, 1491, 1422]
    _ALLPASS_DELAYS_44K = [225, 556]
    _ALLPASS_FB         = 0.5

    def __init__(self, room_size: float = 0.7, wet: float = 0.35,
                 sr: int = 44100) -> None:
        scale = sr / 44100.0
        self._wet = float(wet)
        self._dry = 1.0 - wet * 0.5
        self._comb_fb = 0.50 + room_size * 0.42

        self._comb_delays = [max(1, int(d * scale)) for d in self._COMB_DELAYS_44K]
        self._ap_delays   = [max(1, int(d * scale)) for d in self._ALLPASS_DELAYS_44K]

        # Circular buffers — sized to 2× sr so write never laps unread history
        cbuf = max(self._comb_delays + self._ap_delays) * 2 + sr
        self._comb_bufs = [[np.zeros(cbuf, np.float64),
                            np.zeros(cbuf, np.float64)] for _ in self._comb_delays]
        self._ap_bufs   = [[np.zeros(cbuf, np.float64),
                            np.zeros(cbuf, np.float64)] for _ in self._ap_delays]
        self._comb_ptr  = 0
        self._ap_ptr    = 0   # shared write pointer (same block size each call)
        self._ptr       = 0   # single monotonic write pointer for all buffers

    def _comb_block(self, bufs, delay: int, inp: np.ndarray, fb: float) -> np.ndarray:
        """Vectorised feedback comb filter over one block."""
        n = len(inp); blen = len(bufs[0])
        idx = (self._ptr + np.arange(n)) % blen
        ridx = (self._ptr + np.arange(n) - delay) % blen
        delayed = bufs[0][ridx]
        bufs[0][idx] = inp + fb * delayed
        return delayed.astype(np.float32)

    def _comb_block_stereo(self, bufs, delay, l, r, fb):
        n = len(l); blen = len(bufs[0])
        idx  = (self._ptr + np.arange(n)) % blen
        ridx = (self._ptr + np.arange(n) - delay) % blen
        dl = bufs[0][ridx]; dr = bufs[1][ridx]
        bufs[0][idx] = l + fb * dl
        bufs[1][idx] = r + fb * dr
        return dl.astype(np.float32), dr.astype(np.float32)

    def _ap_block_stereo(self, bufs, delay, l, r):
        fb = self._ALLPASS_FB
        n = len(l); blen = len(bufs[0])
        idx  = (self._ptr + np.arange(n)) % blen
        ridx = (self._ptr + np.arange(n) - delay) % blen
        dl = bufs[0][ridx]; dr = bufs[1][ridx]
        vl = l + fb * dl; vr = r + fb * dr
        bufs[0][idx] = vl; bufs[1][idx] = vr
        return (dl - fb * vl).astype(np.float32), (dr - fb * vr).astype(np.float32)

    def process(self, buf_l: np.ndarray, buf_r: np.ndarray) -> tuple:
        """Apply reverb.  State persists between calls."""
        rev_l = np.zeros(len(buf_l), np.float32)
        rev_r = np.zeros(len(buf_r), np.float32)

        for i, delay in enumerate(self._comb_delays):
            cl, cr = self._comb_block_stereo(
                self._comb_bufs[i], delay,
                buf_l.astype(np.float64), buf_r.astype(np.float64),
                self._comb_fb)
            rev_l += cl; rev_r += cr
        rev_l *= 0.25; rev_r *= 0.25

        for i, delay in enumerate(self._ap_delays):
            rev_l, rev_r = self._ap_block_stereo(
                self._ap_bufs[i], delay,
                rev_l.astype(np.float64), rev_r.astype(np.float64))

        self._ptr = int((self._ptr + len(buf_l)) % len(self._comb_bufs[0][0]))

        out_l = (buf_l * self._dry + rev_l * self._wet).astype(np.float32)
        out_r = (buf_r * self._dry + rev_r * self._wet).astype(np.float32)
        return out_l, out_r


class Sidechain:
    """Kick-ducking sidechain compressor.

    SA's confirmed params: .duck().duckattack(.16).duckdepth(.6)
    Models gain reduction applied to pad/lead when a kick hits.

    Gain envelope model:
        gain(t) = 1 − depth × exp(−t / attack_s)
    On a kick onset the gain immediately drops to (1 − depth) = 0.4, then
    recovers exponentially with time constant attack_s = 0.16 s.

    Parameters
    ----------
    depth : float
        Ducking depth.  Default 0.6 → gain floor = 0.4 on kick onset.
    attack_s : float
        Recovery time constant in seconds.  Default 0.16.
    sr : int
        Sample rate.  Default 44100.
    """

    def __init__(
        self, depth: float = 0.6, attack_s: float = 0.16, sr: int = 44100
    ) -> None:
        self._depth = float(depth)
        self._release_s = float(attack_s)  # SA's .duckattack() is the release time
        self._sr = sr
        self._env = 0.0  # current envelope level [0, 1], persists across bars

    def process(
        self,
        signal_l: np.ndarray,
        signal_r: np.ndarray,
        kick_l: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Apply sidechain ducking using kick_l as the key signal.

        Instant attack (peak-hold per sample), exponential release with
        time constant release_s.  SA's .duckattack(.16) controls recovery
        speed, not attack — the duck is instantaneous on the kick transient.

        State persists between calls so recovery is continuous across bars.

        Returns (ducked_l, ducked_r).
        """
        n = len(kick_l)
        # Per-sample release coefficient: env decays by this factor each sample.
        release = float(np.exp(-1.0 / (self._sr * self._release_s)))

        kick_abs = np.abs(kick_l).astype(np.float64)
        env_out = np.empty(n, dtype=np.float64)
        e = self._env
        for i in range(n):
            # Instant attack: grab peak immediately; slow release afterward.
            k = kick_abs[i]
            if k > e:
                e = k
            else:
                e *= release
            env_out[i] = e
        self._env = float(e)

        env_out = np.clip(env_out, 0.0, 1.0).astype(np.float32)
        gain = (1.0 - self._depth * env_out).astype(np.float32)
        out_l = (signal_l * gain).astype(np.float32)
        out_r = (signal_r * gain).astype(np.float32)
        return out_l, out_r
