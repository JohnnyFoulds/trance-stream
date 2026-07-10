# Plan: Black-Box Synthesis Parameter Optimisation via CLAP

## Context

Manual EXP-001→EXP-016 got spectral_centroid_ratio and band_energy_cosine to PASS but
CLAP is plateaued at 0.527 vs target 0.70. The two remaining gaps (mfcc=0.794, CLAP=0.527)
are not addressable by spectral reasoning — they are holistic perceptual gaps that require
exploring a ~15-dimensional continuous parameter space in ways that are combinatorially
intractable by hand. This is a classic black-box optimisation problem: we have parameters,
a differentiable-free objective (CLAP cosine), a reference, and a generator. Just use ML.

---

## Academic Framing

**The formal problem:**
  θ* = argmax_θ  CLAP(x_ref, G(θ))
where G is the hey_angel renderer (non-differentiable numpy/scipy), θ is the parameter
vector, and CLAP is the objective (pre-trained neural audio embedding cosine similarity).

**Why not gradient descent / DDSP:**
Differentiable DSP (Engel et al., 2020, NeurIPS) rewrites the synthesiser in PyTorch so
gradients flow from the loss through the signal processing chain back to θ. Requires
rewriting every instrument class in autograd-compatible ops — overkill for a ~15-parameter
problem. We keep the numpy synthesiser and treat it as a black box.

**Why not RL / GANs:**
RL requires thousands of rollouts and is designed for sequential decision problems.
GANs generate audio — they don't invert it to parameters. Both are wrong tools here.

**The right tool — CMA-ES:**
Covariance Matrix Adaptation Evolution Strategy (Hansen 2016) is the de facto standard
for black-box optimisation of 10–100 continuous parameters. Adapts a full covariance
matrix over the search distribution, escaping saddle points and elongated valleys. Used
specifically for synthesiser sound matching: Yee-King (2011) "Automatic Programming of
VST Synthesizers" found evolutionary strategies superior to gradient methods on exactly
this type of problem. Pure Python, `pip install cma` (~30 kB).

**Multi-fidelity trick** (Li et al. 2017 ASHA / successive halving):
Render 4 bars instead of 15 during search (~5× speedup per eval). Each eval: render=0.1s
+ CLAP=2–3s (cached model) ≈ 3s total → 500 evals in ~25 min. Promote best candidates
to full 15-bar evaluation at the end.

**Fallback — Differential Evolution** (Storn & Price 1997):
Already in `scipy.optimize`, zero new dependencies, parallelisable. Slower than CMA-ES
to converge but works fine for this dimensionality.

---

## Parameter Space (15 continuous dims)

| # | Parameter | Bounds | Current (EXP-016) |
|---|---|---|---|
| 0 | `lead_cutoff_hz` | [300, 8000] | 2400 |
| 1 | `lead_gain` | [0.05, 0.70] | 0.35 |
| 2 | `pad_cutoff_slider` | [0.35, 0.75] | 0.593 |
| 3 | `pad_gain` | [0.3, 3.5] | 1.50 |
| 4 | `hihat_gain` | [0.2, 3.0] | 1.40 |
| 5 | `bass_cutoff_g1` | [0.18, 0.60] | 0.38 |
| 6 | `reverb_room` | [0.2, 0.9] | 0.45 |
| 7 | `reverb_wet` | [0.05, 0.45] | 0.20 |
| 8 | `sidechain_depth` | [0.3, 0.95] | 0.721 |
| 9 | `gain_kick` | [0.15, 0.80] | 0.40 |
| 10 | `gain_bass` | [0.15, 0.70] | 0.303 |
| 11 | `gain_pluck` | [0.03, 0.50] | 0.16 |
| 12 | `kick_decay_s` | [0.10, 0.50] | 0.25 |
| 13 | `kick_pitch_floor` | [30, 80] | 50 |
| 14 | `hihat_decay_s` | [0.02, 0.15] | 0.06 |

---

## Deliverable: `tools/optimize_hey_angel.py`

One new script. One small addition to `hey_angel_cover.py`.

### `hey_angel_cover.py` change

Add a `HeyAngelRenderer.from_params(params: dict)` classmethod (~15 lines) that
instantiates the renderer with all parameters taken from the dict instead of hardcoded
values. The existing `__init__` is not changed — `from_params` just calls it after
setting module-level overrides or by passing them through a thin wrapper.

Cleanest approach: `from_params` creates the renderer then immediately patches the
mutable attributes:
```python
@classmethod
def from_params(cls, p: dict, sr: int = SR, n_bars: int = 4) -> 'HeyAngelRenderer':
    r = cls(sr=sr, n_bars=n_bars)
    r._lead   = SmoothLead(cutoff_hz=p['lead_cutoff_hz'], gain=p['lead_gain'], sr=sr)
    r._pad    = SupersawPad(root_midi=43, cutoff_slider=p['pad_cutoff_slider'],
                            sr=sr, voicing_offsets=PAD_VOICING_OFFSETS)
    r._reverb = SchroederReverb(room_size=p['reverb_room'], wet=p['reverb_wet'], sr=sr)
    r._sc     = Sidechain(depth=p['sidechain_depth'], attack_s=SIDECHAIN_ATTACK_S, sr=sr)
    r._kit    = DrumKit(seed=42, sr=sr,
                        kick_decay_s=p['kick_decay_s'],
                        kick_pitch_floor=p['kick_pitch_floor'])
    r._gain_kick   = p['gain_kick']
    r._gain_bass   = p['gain_bass']
    r._gain_lead   = p['lead_gain']
    r._gain_hihat  = p['hihat_gain']
    r._gain_pluck  = p['gain_pluck']
    r._gain_pad    = p['pad_gain']
    r._bass_cutoff_g1 = p['bass_cutoff_g1']  # stored for use in render_bar
    r._hihat_decay_s  = p['hihat_decay_s']
    return r
```

`render_bar` reads `self._bass_cutoff_g1` and `self._hihat_decay_s` if present,
otherwise falls back to hardcoded defaults (so existing behaviour is unchanged).

### `tools/optimize_hey_angel.py` architecture

```python
# 1. ClapSingleton — load model ONCE, reuse for all 500+ evaluations
class ClapSingleton:
    _instance = None
    def score(self, ref_path, gen_path) -> float: ...

# 2. ParameterSpace — bounds, encode/decode numpy vector <-> dict
class ParameterSpace:
    BOUNDS = [...]      # list of (lo, hi) for each of 15 dims
    NAMES  = [...]
    def encode(self, d: dict) -> np.ndarray: ...   # dict -> [0,1]^15 normalised
    def decode(self, x: np.ndarray) -> dict: ...   # [0,1]^15 -> raw param dict

# 3. objective(x) — the loss function
def objective(x: np.ndarray) -> float:
    params = space.decode(x)
    wav = f'/tmp/ha_opt_{os.getpid()}_{counter}.wav'
    renderer = HeyAngelRenderer.from_params(params, n_bars=N_BARS_FAST)
    audio_l, audio_r = renderer.render_bars(N_BARS_FAST)
    write_wav(wav, audio_l, audio_r, SR)
    clap = clap_singleton.score(REF_PATH, wav)
    # soft spectral guard to prevent degenerate solutions (e.g. all silence)
    band_e = fast_band_energy_cosine(wav)   # cheap librosa call, no CLAP
    penalty = max(0.0, 0.70 - band_e) * 0.4
    score = clap - penalty
    log_eval(params, clap, score)
    return -score   # minimise

# 4. run() — CMA-ES or fallback to scipy DE
def run():
    x0 = space.encode(CURRENT_BEST)   # warm-start from EXP-016
    try:
        import cma
        es = cma.CMAEvolutionStrategy(x0, sigma0=0.25, {
            'maxiter': MAXITER, 'popsize': 8,
            'bounds': [[0]*15, [1]*15],
        })
        while not es.stop():
            xs = es.ask()
            fs = [objective(x) for x in xs]
            es.tell(xs, fs)
    except ImportError:
        from scipy.optimize import differential_evolution
        result = differential_evolution(objective, [(0,1)]*15,
            maxiter=MAXITER, popsize=8, seed=42,
            x0=x0, callback=print_progress)

# 5. After loop: promote top-K to N_BARS_FULL=15, write best_params.json
```

### CLI

```
python tools/optimize_hey_angel.py --dry-run          # 1 eval, verify CLAP loads
python tools/optimize_hey_angel.py --iters 500        # full run
python tools/optimize_hey_angel.py --iters 500 --use-scipy   # fallback, no cma dep
```

### Outputs

- `optimize_log.csv` — every evaluation: iteration, CLAP, all 15 params
- `best_params.json` — best θ found at 4-bar and 15-bar fidelity
- Terminal: live best CLAP, iteration count, ETA

---

## Files to Create / Modify

| File | Action |
|---|---|
| `tools/optimize_hey_angel.py` | **Create** — ~200 lines |
| `hey_angel_cover.py` | **Add** `from_params()` classmethod + 2 render_bar fallback reads |
| `docs/decisions/clap_optimisation_plan.md` | **Copy** this plan (Step 0) |
| `research/analysis/experiment_log.md` | **Append** OPT-001 entry after run |

---

## Step 0 (before writing any code)

Copy this plan into the repo:
```
cp ~/.claude/plans/is-our-tools-fully-wise-book.md \
   docs/decisions/clap_optimisation_plan.md
```

---

## Verification

1. `pip install cma`
2. `python tools/optimize_hey_angel.py --dry-run` → confirm CLAP loads once, score prints
3. `python tools/optimize_hey_angel.py --iters 500` → runs ~25 min, writes `best_params.json`
4. Apply best params to `hey_angel_cover.py`, run `compare_audio.py`, record as OPT-001
5. If CLAP ≥ 0.70: all four Tier-1 gates checked; if PASS → merge branch

---

## Expected outcome

CMA-ES at 500 evaluations in 15 dims typically converges to within 90% of the global
optimum. Given CLAP is at 0.527 and the target is 0.70, and the parameter space is
not yet fully explored (we have only tested ~20 manual points), reaching 0.65–0.72 in
one run is realistic. The multi-fidelity trick keeps wall-clock time under 30 minutes.
