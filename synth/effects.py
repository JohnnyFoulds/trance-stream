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
from scipy.signal import lfilter


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
        self._attack_s = float(attack_s)
        self._sr = sr
        self._env_state = np.zeros(1, dtype=np.float64)  # IIR filter state

    def process(
        self,
        signal_l: np.ndarray,
        signal_r: np.ndarray,
        kick_l: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Apply sidechain ducking using kick_l as the key signal.

        Rectifies kick_l to obtain an envelope, smooths it with a stateful
        one-pole IIR (scipy lfilter with zi — state persists between calls
        so sidechain recovery is continuous across bar boundaries).

        Returns (ducked_l, ducked_r).
        """
        kick_env = np.abs(kick_l).astype(np.float64)

        # One-pole exponential follower: α = 1 − exp(−1 / (sr × τ)).
        alpha = 1.0 - np.exp(-1.0 / (self._sr * self._attack_s))
        b_coef = [alpha]
        a_coef = [1.0, -(1.0 - alpha)]
        kick_env_smooth, self._env_state = lfilter(
            b_coef, a_coef, kick_env, zi=self._env_state)
        kick_env_smooth = kick_env_smooth.astype(np.float32)

        # Normalise so peak kick = full ducking depth.
        peak = kick_env_smooth.max()
        kick_env_smooth = np.clip(kick_env_smooth / max(float(peak), 1e-9), 0.0, 1.0)

        gain = (1.0 - self._depth * kick_env_smooth).astype(np.float32)
        out_l = (signal_l * gain).astype(np.float32)
        out_r = (signal_r * gain).astype(np.float32)
        return out_l, out_r
