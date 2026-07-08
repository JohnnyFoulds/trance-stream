# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""Pre-rendered drum kit — kick, hi-hat, clap."""

from __future__ import annotations


class DrumKit:
    """Pre-rendered drum instruments.

    All buffers are rendered once at init for determinism and performance.
    Seeded via numpy.random.default_rng(seed) — same seed = same sound.

    Usage
    -----
        kit = DrumKit(seed=42, sr=44100)
        kick_l, kick_r   = kit.render_kick(gain=1.0)
        hh_l, hh_r       = kit.render_hihat(decay_s=0.08, gain=0.5)
        clap_l, clap_r   = kit.render_clap(gain=0.7)
    """

    def __init__(self, seed: int = 42, sr: int = 44100,
                 kick_decay_s: float = 0.25, kick_pitch_floor: float = 50.0):
        from synth.drums import kick, hihat, clap

        self._sr   = sr
        self._seed = seed
        self._kick_decay_s     = kick_decay_s
        self._kick_pitch_floor = kick_pitch_floor

        self._kick_l,  self._kick_r  = kick(sr=sr, seed=seed,
                                            decay_s=kick_decay_s,
                                            pitch_floor=kick_pitch_floor)
        self._hihat_l, self._hihat_r = hihat(sr=sr, decay_s=0.08, seed=seed)
        self._clap_l,  self._clap_r  = clap(sr=sr, seed=seed)

    # ------------------------------------------------------------------
    # Public render methods
    # ------------------------------------------------------------------

    def render_kick(self, gain: float = 1.0) -> tuple:
        """Return (buf_l, buf_r) for one kick hit at the given gain."""
        return (self._kick_l * gain, self._kick_r * gain)

    def render_hihat(self, decay_s: float = 0.08, gain: float = 0.5) -> tuple:
        """Return (buf_l, buf_r) for one hi-hat hit, trimmed to decay_s.

        Re-renders only when decay differs by more than 5 ms from the cached value.
        """
        import numpy as np
        from synth.drums import hihat

        if abs(decay_s - 0.08) > 0.005:
            l, r = hihat(sr=self._sr, decay_s=decay_s, seed=self._seed)
        else:
            l, r = self._hihat_l, self._hihat_r

        # Trim to the length implied by the decay (5× decay gives ~-40 dB tail)
        target_len = int(max(decay_s * 5.0, 0.1) * self._sr)
        n = min(len(l), target_len)
        return (l[:n] * gain, r[:n] * gain)

    def render_clap(self, gain: float = 0.7) -> tuple:
        """Return (buf_l, buf_r) for one clap hit at the given gain."""
        return (self._clap_l * gain, self._clap_r * gain)

    # ------------------------------------------------------------------
    # Length helpers (samples)
    # ------------------------------------------------------------------

    def kick_length(self) -> int:
        return len(self._kick_l)

    def hihat_length(self) -> int:
        return len(self._hihat_l)

    def clap_length(self) -> int:
        return len(self._clap_l)
