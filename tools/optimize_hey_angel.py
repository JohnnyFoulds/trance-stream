#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Black-box synthesis parameter optimisation using CLAP as the objective.

Finds the hey_angel_cover.py parameter vector θ that maximises CLAP cosine
similarity to the reference audio. Uses CMA-ES (Hansen 2016).

CLAP internally clips all audio to 10 seconds before embedding. At 140 BPM,
8 bars = 13.7s so CLAP always receives 10s of real content from both ref and
gen — no silence padding, no length-mismatch penalty.

Usage
-----
    pip install cma          # recommended; falls back to scipy DE if absent
    python tools/optimize_hey_angel.py --dry-run
    python tools/optimize_hey_angel.py --iters 500
    python tools/optimize_hey_angel.py --iters 500 --use-scipy

Outputs
-------
    optimize_log.csv     — every evaluation (params + CLAP + scores)
    best_params.json     — best θ found
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
import wave
import itertools

import numpy as np

# ── paths ─────────────────────────────────────────────────────────────────────

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

REF_PATH   = os.path.join(_REPO, 'research/reference_audio/hey_angel_trimmed.wav')
LOG_PATH   = os.path.join(_REPO, 'optimize_log.csv')
BEST_PATH  = os.path.join(_REPO, 'best_params.json')
TMP_WAV    = f'/tmp/ha_opt_{os.getpid()}.wav'

SR      = 44100
N_BARS  = 16  # 16 bars = 27.4s at 140 BPM ≈ 26.6s reference; fusion CLAP processes full duration

# ── parameter space ───────────────────────────────────────────────────────────

# Each entry: (name, lo, hi, current_best)
_SPACE = [
    ('lead_cutoff_hz',   300.0,  8000.0, 2400.0),
    ('lead_gain',          0.05,    0.70,    0.35),
    ('pad_cutoff_slider',  0.35,    0.75,  0.593),
    ('pad_gain',           0.30,    3.50,    1.50),
    ('hihat_gain',         0.20,    3.00,    1.40),
    ('bass_cutoff_g1',     0.18,    0.60,    0.38),
    ('reverb_room',        0.20,    0.90,    0.45),
    ('reverb_wet',         0.05,    0.45,    0.20),
    ('sidechain_depth',    0.30,    0.95,   0.721),
    ('gain_kick',          0.15,    0.80,    0.40),
    ('gain_bass',          0.15,    0.70,   0.303),
    ('gain_pluck',         0.03,    0.50,    0.16),
    ('kick_decay_s',       0.10,    0.50,    0.25),
    ('kick_pitch_floor',  30.0,    80.0,    50.0),
    ('hihat_decay_s',      0.02,    0.15,    0.06),
]

NAMES   = [s[0] for s in _SPACE]
LOWS    = np.array([s[1] for s in _SPACE], dtype=np.float64)
HIGHS   = np.array([s[2] for s in _SPACE], dtype=np.float64)
CURRENT = np.array([s[3] for s in _SPACE], dtype=np.float64)
NDIM    = len(_SPACE)


def encode(d: dict) -> np.ndarray:
    """Raw param dict → [0, 1]^N normalised vector."""
    v = np.array([d[n] for n in NAMES], dtype=np.float64)
    return (v - LOWS) / (HIGHS - LOWS)


def decode(x: np.ndarray) -> dict:
    """[0, 1]^N normalised vector → raw param dict (clamped to bounds)."""
    x = np.clip(x, 0.0, 1.0)
    v = LOWS + x * (HIGHS - LOWS)
    return dict(zip(NAMES, v.tolist()))


# ── CLAP singleton ────────────────────────────────────────────────────────────

class _ClapSingleton:
    def __init__(self):
        import laion_clap
        print("Loading CLAP model (first time only)…", flush=True)
        t0 = time.time()
        self._model = laion_clap.CLAP_Module(enable_fusion=True, amodel='HTSAT-tiny')
        self._model.load_ckpt()
        print(f"CLAP loaded in {time.time()-t0:.1f}s", flush=True)
        # Cache reference embedding — it never changes
        emb = self._model.get_audio_embedding_from_filelist([REF_PATH], use_tensor=False)
        self._ref_emb = emb[0]

    def score(self, gen_path: str) -> float:
        emb = self._model.get_audio_embedding_from_filelist([gen_path], use_tensor=False)
        return float(np.dot(self._ref_emb, emb[0]))


_clap: _ClapSingleton | None = None

def clap_score(gen_path: str) -> float:
    global _clap
    if _clap is None:
        _clap = _ClapSingleton()
    return _clap.score(gen_path)


# ── WAV writer ────────────────────────────────────────────────────────────────

def write_wav(path: str, audio_l: np.ndarray, audio_r: np.ndarray) -> None:
    stereo = np.stack([audio_l, audio_r], axis=1)
    stereo = np.clip(stereo, -1.0, 1.0)
    pcm    = (stereo * 32767).astype(np.int16)
    with wave.open(path, 'w') as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SR)
        wf.writeframes(pcm.tobytes())


# ── cheap spectral guard (no CLAP) ────────────────────────────────────────────

def _band_energy_cosine(path: str) -> float:
    import librosa
    from scipy.spatial.distance import cosine as cosine_dist
    SR2 = 22050; HOP = 512
    bands = [(0,200),(200,500),(500,1000),(1000,2000),(2000,4000),(4000,SR2//2)]
    ref_vec = np.array([0.498, 0.136, 0.087, 0.083, 0.103, 0.093])  # EXP-000 reference
    y, _ = librosa.load(path, sr=SR2, mono=True)
    S = np.abs(librosa.stft(y, hop_length=HOP)) ** 2
    freqs = librosa.fft_frequencies(sr=SR2, n_fft=(S.shape[0]-1)*2)
    total = S.sum() + 1e-12
    gen_vec = np.array([
        S[np.logical_and(freqs >= lo, freqs < hi)].sum() / total
        for lo, hi in bands
    ])
    if gen_vec.sum() < 1e-9:
        return 0.0
    return float(1.0 - cosine_dist(ref_vec, gen_vec))


# ── objective ─────────────────────────────────────────────────────────────────

_eval_counter = itertools.count(1)
_best_clap    = [-999.0]
_log_writer   = None
_log_file     = None


def _open_log():
    global _log_writer, _log_file
    exists = os.path.exists(LOG_PATH)
    _log_file   = open(LOG_PATH, 'a', newline='')
    _log_writer = csv.DictWriter(_log_file, fieldnames=['iter','clap','score']+NAMES)
    if not exists:
        _log_writer.writeheader()


def objective(x: np.ndarray, n_bars: int = N_BARS) -> float:
    from hey_angel_cover import HeyAngelRenderer
    i = next(_eval_counter)
    params = decode(x)
    try:
        renderer = HeyAngelRenderer.from_params(params, n_bars=n_bars)
        audio_l, audio_r = renderer.render_bars(n_bars)
        write_wav(TMP_WAV, audio_l, audio_r)
        clap  = clap_score(TMP_WAV)
        band_e = _band_energy_cosine(TMP_WAV)
        penalty = max(0.0, 0.70 - band_e) * 0.4
        score = clap - penalty
    except Exception as exc:
        print(f"  [eval {i}] ERROR: {exc}")
        clap = -1.0; score = -1.5

    if _log_writer:
        row = {'iter': i, 'clap': round(clap, 5), 'score': round(score, 5)}
        row.update({n: round(params[n], 5) for n in NAMES})
        _log_writer.writerow(row)
        _log_file.flush()

    if clap > _best_clap[0]:
        _best_clap[0] = clap
        print(f"  iter {i:4d}  CLAP={clap:.4f}  score={score:.4f}  *** new best ***",
              flush=True)
    elif i % 20 == 0:
        print(f"  iter {i:4d}  CLAP={clap:.4f}  score={score:.4f}  best={_best_clap[0]:.4f}",
              flush=True)

    return -score   # minimise


# ── run CMA-ES ────────────────────────────────────────────────────────────────

def run_cma(maxiter: int) -> np.ndarray:
    import cma
    x0 = encode(dict(zip(NAMES, CURRENT.tolist())))
    opts = {
        'maxiter':  maxiter,
        'popsize':  8,
        'bounds':   [[0.0]*NDIM, [1.0]*NDIM],
        'verbose':  -9,   # suppress cma's own output; we print our own
        'tolx':     1e-4,
        'tolfun':   1e-4,
    }
    es = cma.CMAEvolutionStrategy(x0.tolist(), 0.25, opts)
    print(f"CMA-ES: σ₀=0.25, popsize=8, maxiter={maxiter}, ndim={NDIM}")
    while not es.stop():
        solutions = es.ask()
        fitnesses = [objective(np.array(s)) for s in solutions]
        es.tell(solutions, fitnesses)
    return np.array(es.result.xbest)


# ── run scipy Differential Evolution (fallback) ───────────────────────────────

def run_de(maxiter: int) -> np.ndarray:
    from scipy.optimize import differential_evolution
    print(f"Differential Evolution: popsize=8, maxiter={maxiter}, ndim={NDIM}")
    x0 = encode(dict(zip(NAMES, CURRENT.tolist())))
    result = differential_evolution(
        objective,
        bounds=[(0.0, 1.0)] * NDIM,
        maxiter=maxiter,
        popsize=8,
        seed=42,
        x0=x0,
        tol=1e-4,
        mutation=(0.5, 1.0),
        recombination=0.7,
    )
    return result.x


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--iters',     type=int, default=500)
    ap.add_argument('--dry-run',   action='store_true',
                    help='Run one evaluation and exit (verify setup)')
    ap.add_argument('--use-scipy', action='store_true',
                    help='Use scipy differential_evolution instead of cma')
    args = ap.parse_args()

    if not os.path.exists(REF_PATH):
        print(f"ERROR: reference not found: {REF_PATH}")
        sys.exit(1)

    global _clap
    _clap = _ClapSingleton()

    _open_log()

    if args.dry_run:
        print("Dry run: one evaluation…")
        x0 = encode(dict(zip(NAMES, CURRENT.tolist())))
        val = objective(x0)
        print(f"Objective = {val:.4f}  (CLAP = {_best_clap[0]:.4f})")
        print("Dry run OK.")
        return

    t_start = time.time()
    use_scipy = args.use_scipy
    if not use_scipy:
        try:
            import cma as _cma_test  # noqa
        except ImportError:
            print("cma not installed — falling back to scipy differential_evolution")
            print("  (run `pip install cma` for faster convergence)")
            use_scipy = True

    if use_scipy:
        xbest = run_de(args.iters)
    else:
        xbest = run_cma(args.iters)

    elapsed = time.time() - t_start
    print(f"\nOptimisation finished in {elapsed/60:.1f} min  "
          f"({next(_eval_counter)-1} evaluations)")
    print(f"Best CLAP ({N_BARS}-bar): {_best_clap[0]:.4f}")

    best_params = decode(xbest)
    print(f"\nBest parameters:")
    for n, v in best_params.items():
        print(f"  {n:<22} = {v:.5f}")

    with open(BEST_PATH, 'w') as f:
        json.dump({'clap': _best_clap[0], 'n_bars': N_BARS, 'params': best_params}, f, indent=2)
    print(f"\nSaved → {BEST_PATH}")
    print(f"Log   → {LOG_PATH}")


if __name__ == '__main__':
    main()
