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
    speed: float = 1.5,
    amount: float = 1.0,
) -> np.ndarray:
    """SA's trancegate: smooth cosine amplitude gate at speed x bar rate.

    SA's confirmed params: trancegate(1.5, 45, 1)
    speed=1.5 creates a 3/2 polyrhythm against a 4/4 kick. The 45-degree angle
    parameter in SA's trancegate corresponds to equal rise/fall time, modelled
    as a raised cosine: (1 + cos(theta)) / 2.

    bar_offset_samples: how many samples into the current bar we are,
    for phase continuity when called bar-by-bar.

    Returns envelope in [0, 1], shape (n_samples,).
    """
    gate_period_samples = samples_per_bar / speed
    t = np.arange(n_samples, dtype=np.float64) + bar_offset_samples
    phase = 2.0 * np.pi * t / gate_period_samples
    # Raised cosine from 0→1. amount=1.0 means trough=0 (full silence).
    # SA's gate with .room(0.7) reverb fills those silences with reverb tail.
    # Our FDN is shorter, so we lift the trough floor: trough = 1 - amount.
    # amount=0.7 → trough=0.3 → gate breathes between 0.3 and 1.0 (never silent).
    cosine_01 = (1.0 + np.cos(phase + np.pi)) / 2.0
    floor = 1.0 - amount
    env = floor + cosine_01 * amount
    return env.astype(np.float32)
