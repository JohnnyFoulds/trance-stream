#!/usr/bin/env python3
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""Plot CMA-ES optimisation progress from optimize_log.csv.

Generates:
  1. Learning curve: CLAP and score vs eval, with cumulative-best overlay
  2. Penalty analysis: scatter of CLAP vs score (penalty = CLAP - score)
  3. Parameter evolution: final best-params vs search bounds (bar chart)

Usage
-----
    python tools/plot_optimization.py                     # saves to /tmp/opt_plots.png
    python tools/plot_optimization.py --out opt_plots.png
    python tools/plot_optimization.py --log path/to/optimize_log.csv
"""
from __future__ import annotations

import argparse
import os
import sys

import numpy as np

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _REPO)

DEFAULT_LOG  = os.path.join(_REPO, 'optimize_log.csv')
DEFAULT_OUT  = '/tmp/opt_plots.png'

TIER1_CLAP   = 0.70   # target gate

PARAM_NAMES = [
    'lead_cutoff_hz', 'lead_gain', 'pad_cutoff_slider', 'pad_gain', 'hihat_gain',
    'bass_cutoff_g1', 'reverb_room', 'reverb_wet', 'sidechain_depth', 'gain_kick',
    'gain_bass', 'gain_pluck', 'kick_decay_s', 'kick_pitch_floor', 'hihat_decay_s',
]
PARAM_LO = np.array([300.0,0.05,0.35,0.30,0.20, 0.18,0.20,0.05,0.30,0.15, 0.15,0.03,0.10,30.0,0.02])
PARAM_HI = np.array([8000.,0.70,0.75,3.50,3.00, 0.60,0.90,0.45,0.95,0.80, 0.70,0.50,0.50,80.0,0.15])


def load_log(path: str):
    import csv
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                rows.append({k: float(v) for k, v in row.items()})
            except ValueError:
                pass
    return rows


def rolling_best(values):
    best = -np.inf
    out = []
    for v in values:
        if v > best:
            best = v
        out.append(best)
    return np.array(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument('--log', default=DEFAULT_LOG)
    ap.add_argument('--out', default=DEFAULT_OUT)
    args = ap.parse_args()

    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
    except ImportError:
        print("ERROR: matplotlib not installed — pip install matplotlib")
        sys.exit(1)

    rows = load_log(args.log)
    if not rows:
        print(f"ERROR: no data in {args.log}")
        sys.exit(1)

    iters  = np.array([r['iter']  for r in rows])
    clap   = np.array([r['clap']  for r in rows])
    score  = np.array([r['score'] for r in rows])
    best_clap  = rolling_best(clap)
    best_score = rolling_best(score)

    # Best row (by CLAP)
    best_idx  = int(np.argmax(clap))
    best_row  = rows[best_idx]
    best_params_norm = np.array([
        (best_row[n] - lo) / (hi - lo)
        for n, lo, hi in zip(PARAM_NAMES, PARAM_LO, PARAM_HI)
    ])

    penalty = clap - score

    fig = plt.figure(figsize=(16, 14))
    gs  = gridspec.GridSpec(3, 2, figure=fig, hspace=0.45, wspace=0.35)

    # ── Panel 1: learning curve (full) ─────────────────────────────────────────
    ax1 = fig.add_subplot(gs[0, :])
    ax1.plot(iters, clap,  alpha=0.3, color='steelblue', linewidth=0.6, label='CLAP per eval')
    ax1.plot(iters, score, alpha=0.3, color='coral',     linewidth=0.6, label='Score per eval')
    ax1.plot(iters, best_clap,  color='steelblue', linewidth=2.0, label='Best CLAP so far')
    ax1.plot(iters, best_score, color='coral',     linewidth=2.0, label='Best score so far')
    ax1.axhline(TIER1_CLAP, color='green', linestyle='--', linewidth=1.5,
                label=f'Target CLAP ≥ {TIER1_CLAP}')
    ax1.set_xlabel('Evaluation #')
    ax1.set_ylabel('CLAP / Score')
    ax1.set_title(f'CMA-ES Learning Curve  (n={len(rows)} evals, best CLAP={best_clap[-1]:.4f})')
    ax1.legend(loc='lower right', fontsize=8)
    ax1.set_ylim(0, 1.0)
    ax1.grid(alpha=0.3)

    # ── Panel 2: zoomed last 1000 evals ────────────────────────────────────────
    ax2 = fig.add_subplot(gs[1, 0])
    zoom = max(0, len(iters) - 1000)
    ax2.plot(iters[zoom:], clap[zoom:],  alpha=0.4, color='steelblue', linewidth=0.7)
    ax2.plot(iters[zoom:], best_clap[zoom:], color='steelblue', linewidth=2.0, label='Best CLAP')
    ax2.axhline(TIER1_CLAP, color='green', linestyle='--', linewidth=1.2, label='Target 0.70')
    ax2.set_xlabel('Evaluation #')
    ax2.set_ylabel('CLAP')
    ax2.set_title('CLAP — last 1000 evals')
    ax2.legend(fontsize=8)
    ax2.grid(alpha=0.3)

    # ── Panel 3: penalty scatter ────────────────────────────────────────────────
    ax3 = fig.add_subplot(gs[1, 1])
    mask_penalised = penalty > 1e-4
    ax3.scatter(clap[~mask_penalised], score[~mask_penalised],
                alpha=0.3, s=4, color='steelblue', label='No penalty')
    ax3.scatter(clap[mask_penalised],  score[mask_penalised],
                alpha=0.5, s=8, color='red',       label=f'Penalised ({mask_penalised.sum()})')
    ax3.plot([0, 1], [0, 1], 'k--', linewidth=0.8, alpha=0.5, label='score=CLAP line')
    ax3.set_xlabel('CLAP')
    ax3.set_ylabel('Score (CLAP − band_energy penalty)')
    ax3.set_title('Penalty analysis\n(red = spectral penalty applied)')
    ax3.legend(fontsize=8)
    ax3.grid(alpha=0.3)

    # ── Panel 4: parameter positions at best eval (normalised 0–1) ─────────────
    ax4 = fig.add_subplot(gs[2, :])
    x = np.arange(len(PARAM_NAMES))
    colors = ['forestgreen' if 0.15 < v < 0.85 else 'tomato' for v in best_params_norm]
    bars = ax4.bar(x, best_params_norm, color=colors, alpha=0.8, edgecolor='black', linewidth=0.5)
    ax4.axhline(0.5, color='gray', linestyle=':', linewidth=1.0, alpha=0.6)
    ax4.set_xticks(x)
    ax4.set_xticklabels(
        [n.replace('_', '\n') for n in PARAM_NAMES],
        fontsize=7, rotation=0, ha='center'
    )
    ax4.set_ylim(0, 1)
    ax4.set_ylabel('Normalised value [0=lo, 1=hi]')
    ax4.set_title(
        f'Best-eval parameters (CLAP={clap[best_idx]:.4f}, eval={int(iters[best_idx])})\n'
        f'Green = interior of bounds; Red = near bound (may need wider search)'
    )
    # Annotate raw values
    for xi, (pname, norm) in enumerate(zip(PARAM_NAMES, best_params_norm)):
        raw = best_row[pname]
        ax4.text(xi, norm + 0.03, f'{raw:.3g}', ha='center', va='bottom', fontsize=6)
    ax4.grid(axis='y', alpha=0.3)

    fig.suptitle(
        f'CMA-ES Optimisation — hey_angel_cover.py  '
        f'({len(rows)} evals, best={best_clap[-1]:.4f}, target=0.70)',
        fontsize=13, fontweight='bold', y=1.01
    )

    plt.savefig(args.out, dpi=150, bbox_inches='tight')
    print(f"Saved → {args.out}")
    print(f"Total evals: {len(rows)}")
    print(f"Best CLAP:   {best_clap[-1]:.4f}  at eval {int(iters[best_idx])}")
    print(f"Penalised:   {mask_penalised.sum()} / {len(rows)} evals ({100*mask_penalised.mean():.1f}%)")
    print(f"\nBest params (raw):")
    for pname in PARAM_NAMES:
        norm = (best_row[pname] - PARAM_LO[PARAM_NAMES.index(pname)]) / (PARAM_HI[PARAM_NAMES.index(pname)] - PARAM_LO[PARAM_NAMES.index(pname)])
        flag = '  ← near bound!' if norm < 0.05 or norm > 0.95 else ''
        print(f"  {pname:<22} = {best_row[pname]:.5f}  ({norm:.2f}){flag}")


if __name__ == '__main__':
    main()
