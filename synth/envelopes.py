# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# synth/envelopes.py
# Envelope generators — all numpy-vectorised, no Python sample loops.

import numpy as np


def acidenv(n_samples: int, sr: int, amount: float = 0.55,
            decay_s: float = None) -> np.ndarray:
    """SA's exact acid envelope: fast attack, exponential decay on LP filter cutoff.

    SA's confirmed params from switch_angel_vocabulary.md:
      lpf(100).lpenv(x*9).lps(.2).lpd(.12).lpq(2)
    where x=amount.

    decay_s overrides the tau computed from amount. Used by lead character variants:
      'acid'   → decay_s=0.08  (tight, fast)
      'smooth' → decay_s=0.15  (slower, more legato)
      'stab'   → decay_s=0.04  (very short, percussive)

    Returns an array of shape (n_samples,) in [0, 1] representing the LP filter
    modulation amount. Caller multiplies by (target_hz - base_hz) and adds
    base_hz to get actual cutoff.
    """
    t = np.arange(n_samples, dtype=np.float32) / sr
    attack_s = 0.003
    tau = decay_s if decay_s is not None else 0.08 * (0.3 + amount * 1.4)
    attack_mask = t < attack_s
    decay_mask = ~attack_mask
    env = np.zeros(n_samples, dtype=np.float32)
    env[attack_mask] = t[attack_mask] / attack_s
    t_decay = t[decay_mask] - attack_s
    env[decay_mask] = np.exp(-t_decay / tau)
    return env


def lpenv(
    n_samples: int,
    sr: int,
    amount: float = 2.0,
    decay_s: float = 0.3,
) -> np.ndarray:
    """SA's pad LP envelope: lpenv(2) — slow filter sweep per note trigger.

    amount controls how wide the filter opens (in octaves, as in Strudel).
    decay_s: time for filter to decay from peak. SA's pad uses a slow decay (~0.3s).

    Returns envelope in [0, 1] representing filter modulation amount.
    """
    t = np.arange(n_samples, dtype=np.float32) / sr
    attack_s = 0.005
    env = np.zeros(n_samples, dtype=np.float32)
    attack_mask = t < attack_s
    decay_mask = ~attack_mask
    env[attack_mask] = t[attack_mask] / attack_s
    t_decay = t[decay_mask] - attack_s
    env[decay_mask] = np.exp(-t_decay / decay_s)
    return env * min(amount / 9.0, 1.0)


def trancegate(
    n_samples: int,
    sr: int,
    samples_per_bar: int,
    bar_offset_samples: int = 0,
    density: float = 0.667,
    floor: float = 0.3,
    seed: int = 45,
) -> np.ndarray:
    """SA's trancegate: probabilistic binary gate, 16 steps per bar.

    Models SA's Strudel expression:
        rand.mul(density+0.5).round().seg(16).rib(seed, length)
    Each of 16 slots per bar is independently switched on (gain=1.0) or off
    (gain=floor) based on a seeded random draw: P(on) = density.

    Per-bar patterns are reproducible given the same seed + bar index, matching
    Strudel's .rib(seed, length) behaviour.

    SA's gate triggers note events rather than multiplying a continuous audio
    stream, so transitions are naturally smooth (envelope attack/release).  We
    approximate this with a 5 ms linear crossfade at each slot boundary to
    eliminate broadband click transients from hard amplitude steps.

    floor=0.3 is a deliberate departure from SA's .clip(.7) = 0.7 amplitude on
    open slots; our lower floor avoids hard transients into the FDN reverb.

    Returns envelope in [floor, 1.0], shape (n_samples,).
    """
    n_slots  = 16
    slot_len = max(1, samples_per_bar // n_slots)
    bar_offset = bar_offset_samples % samples_per_bar
    bar_index  = bar_offset_samples // samples_per_bar

    rng    = np.random.default_rng(seed + bar_index)
    on_off = (rng.random(n_slots) < density).astype(np.float32)
    pattern = np.where(on_off, 1.0, floor)

    env = np.full(samples_per_bar, floor, dtype=np.float32)
    for i in range(n_slots):
        s = i * slot_len
        e = min((i + 1) * slot_len, samples_per_bar)
        env[s:e] = pattern[i]

    # 5 ms linear crossfade at each slot boundary to eliminate click transients.
    fade_len = min(int(0.005 * sr), slot_len // 4)
    if fade_len > 1:
        for i in range(1, n_slots):
            boundary = i * slot_len
            if boundary >= samples_per_bar:
                break
            v_prev = pattern[i - 1]
            v_next = pattern[i]
            if v_prev != v_next:
                fade_start = max(0, boundary - fade_len // 2)
                fade_end   = min(samples_per_bar, boundary + (fade_len - fade_len // 2))
                n_fade = fade_end - fade_start
                env[fade_start:fade_end] = np.linspace(v_prev, v_next, n_fade, dtype=np.float32)

    tiles_needed = (bar_offset + n_samples) // samples_per_bar + 2
    full = np.tile(env, tiles_needed)
    return full[bar_offset: bar_offset + n_samples].copy()
