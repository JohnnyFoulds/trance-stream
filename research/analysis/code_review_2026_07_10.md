# Code Review — trance-stream — 2026-07-10

Branch: `sidequest/pluck-arp-analysis`
Reviewer: automated adversarial review
Date: 2026-07-10

---

## Executive Summary

The synthesis core has three runtime bugs that corrupt audio output unconditionally: phantom sidechain ducking from IIR residual amplification, a permanently saturated FM depth on the pulse instrument, and a hey-angel song rendered at 55% gain through the v3 path. The test suite has significant structural weaknesses — multiple tests that pass trivially when the feature under test is completely broken — and the hey-angel arrangement has diverged substantially between `hey_angel_cover.py` and `trance_stream_v3.py --style hey_angel`, with different instrument classes, glide rates, and missing bass events. Recommended priority: fix the three audio-corruption bugs first, then address the test-coverage holes, then tackle the architecture divergence.

---

## Findings

### Critical — fix before merging

**[CORRECTNESS] Sidechain IIR residual amplified to full duck depth on every post-kick block** `synth/effects.py:327`
> The per-block peak normalization divides the smoothed envelope by `max(kick_env_smooth.max(), 1e-9)`. When a kick fires in bar 1, the IIR state decays but never reaches exactly zero. At the start of bar 2 the residual is ~6e-6; line 325 computes `peak = 6e-6`, line 326 divides by `max(6e-6, 1e-9) = 6e-6`, rescaling the residual to 1.0. Line 328 then computes `gain = 1 - 0.6 * 1.0 = 0.4` — full duck depth — even though no kick fired. The `1e-9` floor prevents divide-by-zero but not sub-threshold amplification. Fix: add a threshold guard before normalization, e.g. `if peak < 1e-4: kick_env_norm = np.zeros_like(kick_env_smooth)` instead of normalizing.
> Failure scenario: With `sr=44100`, `attack_s=0.16`, `depth=0.6`, a single kick in bar 1 produces `gain[0]=0.4` at the start of every subsequent bar for the lifetime of the session.

**[CORRECTNESS] FM depth is always 0.5 — session-arc idiom is never realized** `instruments/pulse.py:39`
> `fm_depth = 0.5 * (total_steps / max(total_steps, 1))` simplifies to `0.5 * 1.0 = 0.5` for every call where `total_steps >= 1`. The comment on line 38 says "FM depth increases with session time (fm(time) idiom): 0 → 0.5" — this is false. The denominator equals the numerator for all positive values, so the ratio is always 1.0. Only the unreachable `total_steps=0` case gives `fm_depth=0`. Fix: replace with `fm_depth = 0.5 * (step / max_session_steps)` where `max_session_steps` is a fixed expected session length (e.g. `44100 * 3600 / samples_per_step`).
> Failure scenario: The texture starts maximally FM-modulated from step 1 and never changes, contradicting the design intent for every session of any length.

**[CORRECTNESS] `gain_arc()` with `filter_pb_bar=9999` renders hey-angel at ~55% gain** `song/arcs.py:231`
> `build_hey_angel_song()` sets `filter_pb_bar=9999`. `SongRenderer._render_bar()` unconditionally calls `gain_arc(bar, song)` and multiplies both mix channels by the result. The early-return guard fires only when `bar >= ramp_end`, which never happens in a 128-bar song. The ramp formula `0.55 + 0.45*(bar/9999)` yields 0.550 at bar 0 and only 0.556 at bar 127. The full hey-angel arrangement is rendered at ~55% of intended level through the v3 path. `hey_angel_cover.py` is unaffected because its `HeyAngelRenderer` never calls `gain_arc()`. Fix: add a sentinel check in `build_hey_angel_song()` to set `filter_pb_bar` to the actual song length, or add an explicit override in `SongRenderer` for the hey-angel style.
> Failure scenario: `python trance_stream_v3.py --style hey_angel` outputs audio at 55% amplitude with no warning.

**[CORRECTNESS] `chord_state_at()` phase jump at pullback transition** `song/arcs.py:257`
> Before pullback: `weights=[3,1,3,1]`, `cycle_len=8`. After pullback: `weights=[2,1,2,1]`, `cycle_len=6`. The renderer recomputes `pos = bar % sum(weights)` after `chord_state_at` returns the new weights, with no phase-alignment offset. At `filter_pb_bar=64`: bar 63 → `pos=63%8=7` → chord_idx=3; bar 64 → `pos=64%6=4` → chord_idx=2. A simulation over all 32 possible pullback bars (48–79) confirms 24 of them (75%) produce a discontinuous chord index jump, heard as an abrupt unintended chord change at the pullback moment. Fix: return a phase offset from `chord_state_at()` that aligns `bar % new_cycle` to the current chord position at the transition bar.
> Failure scenario: 75% of seeds produce an audible wrong chord at the pullback transition.

**[CORRECTNESS] `notearp_to_midi()` crashes with `ZeroDivisionError` on empty chord** `song/renderer.py:514`
> `chord_to_midi([])` returns `[]`. The loop reaches a `SA_NOTEARP_PATTERN` entry `>= 0` and executes `chord_midi[idx % len(chord_midi)]` = `chord_midi[idx % 0]`, raising `ZeroDivisionError`. No guard exists in either `notearp_to_midi` or `chord_to_midi`. Fix: add `if not chord_midi: return []` at the top of `notearp_to_midi()`.
> Failure scenario: Any call path that produces an empty chord degrees list (e.g. a scale lookup failure, an out-of-range root, or a future test) crashes the renderer with a zero-division error.

**[CORRECTNESS] Hey-angel bass in `SongRenderer` missing second half-bar** `song/renderer.py:279`
> The hey-angel bass branch (lines 272–302) renders only the first half of the bar: G1 quarter at step 0, F2 eighth at step 4, F2→G1 sweep at step 6. The second repetition (G1 at step 8, F2 at step 12, F2→G1 sweep at step 14) present in `hey_angel_cover.py`'s `BASS_PATTERN` is never rendered. There is no guard, fallback, or alternative code path that fills the second half.
> Failure scenario: The sub-bass energy under the second kick hit at step 8 is completely absent in the v3 path, making every second beat of every bar audibly thinner than the first.

**[CORRECTNESS] `SupersawPad.render()` hardcodes 140 BPM — trancegate drifts at any other tempo** `instruments/pad.py:91`
> `samples_per_bar()` is called with no arguments, hardcoding BPM=140. At 138 BPM (hey-angel-cover, bad-apple-cover, `build_hey_angel_song`), the correct bar length is 76695 samples but `pad.py` computes `spb=75600`. The gate period error is 1095 samples (~24.83 ms) per bar; after 32 bars the trancegate is ~795 ms out of phase with the kick. The render signature has no `samples_per_bar` parameter, so callers cannot correct it. `instruments/lead.py` already received this fix (line 61, 101). Fix: add a `samples_per_bar: int | None = None` parameter to `SupersawPad.render()` and fall back to `_samples_per_bar()` only when `None`.
> Failure scenario: The pad pump drifts ~25 ms/bar at 138 BPM, becoming audibly out of phase with the kick after ~32 bars.

---

### Major — fix soon

**[CORRECTNESS] Hey-angel glide rate diverges between v3 and cover script** `song/renderer.py:347`
> `SongRenderer` passes `portamento_s=spb/sr` (~1.74s at 138 BPM), spanning the full bar. `hey_angel_cover.py` uses `MELODY_GLIDE_S=1.2` and fills the remaining ~0.54s with silence. Glide rates: ~3.45 sem/s (renderer) vs ~5 sem/s (cover). The comment at line 340 claiming "Rate ~15 sem/sec" matches neither. This divergence is compounded by the instruments being different classes entirely (see architecture section). Fix: unify on a single constant in `song/theory.py` and share it between both entry points.
> Failure scenario: The same Hey Angel arrangement sounds different depending on which script generates it — a debugging and maintenance trap.

**[CORRECTNESS] `portamento_s` float value silently ignored; only truthiness checked** `instruments/bass.py:33`
> `portamento_s > 0.0` enables portamento; the glide always spans `n_samples` regardless of the actual duration passed. All current callers work around this by passing `float(n_samples)/sr`. The same issue exists in `instruments/lead.py:112`. Fix: either rename the parameter to `use_portamento: bool` to make the API honest, or implement the duration correctly by computing `glide_samples = min(int(portamento_s * sr), n_samples)`.
> Failure scenario: A caller passing `portamento_s=0.5` expecting a 0.5s glide silently gets a full-bar glide; the API is documented incorrectly in the docstring at line 53.

**[CORRECTNESS] Hihat and clap blocked by `active['kick']` — no independent enable key** `bad_apple_cover.py:447`
> The `active` dict has only four keys: `'kick'`, `'pad'`, `'bass'`, `'lead'`. Hihat (line 447) and clap (line 463) both guard on `active['kick']`. During the intro (bars 0–5), `active['kick']=False` suppresses all percussion texture. There is no way to represent a section where kick plays but hihat does not (or vice versa). Fix: add `'hihat'` and `'clap'` boolean keys to `BAD_APPLE_SECTIONS` and guard accordingly.
> Failure scenario: The intro plays with pad only — no hihat, no clap — because `active['kick']` is `False`. Any future drop section needing kick without hihat is unrepresentable.

**[CORRECTNESS] ASCII video glob is relative — silently finds no files when invoked from outside repo root** `trance_stream_v3.py:140`
> Line 140 uses `glob.glob("ascii_videos/*.txt")` which resolves against the process's cwd, not `REPO_ROOT` (`Path(__file__).parent`, defined at line 32). The `or None` coerces an empty list to `None` silently. No warning is emitted. Fix: replace with `glob.glob(str(REPO_ROOT / "ascii_videos" / "*.txt"))`, consistent with how `REPO_ROOT` is already used at lines 181, 230, 338.
> Failure scenario: `python /abs/path/to/trance_stream_v3.py --stream --viz` from any other directory launches the visualiser without any ASCII overlay with no diagnostic.

**[CORRECTNESS] `write_midi()` produces empty MIDI — `_midi_log` is never populated** `song/renderer.py:489`
> `_midi_log` is initialized in `__init__` but `_render_bar()` never appends to it. `write_midi()` writes only a `set_tempo` and `end_of_track`. The implementation comment at line 493 acknowledges "Minimal implementation" — contradicting the docstring claiming multi-track output. Fix: either populate `_midi_log` in `_render_bar()` with note-on/note-off events, or remove the `--out-midi` flag and `write_midi()` entirely until implemented.
> Failure scenario: `python trance_stream_v3.py --out-midi out.mid` produces a MIDI file with zero note events; no error is raised.

**[CORRECTNESS] `visualiser.py` negative `cells_w` causes end-relative slice overflow** `tools/visualiser.py:685`
> When terminal `cols < 13`, `cells_w = (cols - 6) - len('Rule 30')` goes negative. `raw[:cells_w]` is a Python end-relative slice returning a non-empty string instead of empty, so the label row exceeds its inner width budget and corrupts border alignment. Fix: add `cells_w = max(cells_w, 0)` after the calculation, or add a minimum-cols guard at the top of `_render`.
> Failure scenario: With `cols=12`: inner=6, `cells_w=-1`, `raw[:-1]` returns 5 chars, label becomes 12 chars against a 6-char budget, corrupting all `║` border placement.

**[TEST-COVERAGE] Trancegate RMS variation passes trivially on silent pad** `tests/test_instruments.py:106`
> The `rms_steps` list is filtered to remove values `<= 1e-6`, then the entire assertion block is guarded by `if rms_steps:`. If `SupersawPad.render()` returns all-zeros, `rms_steps=[]`, the guard is `False`, and `assert ratio > 2.0` is never reached. Fix: add `assert rms_steps, "pad produced silence — trancegate test vacuous"` unconditionally before the ratio check.
> Failure scenario: A completely broken pad (all-zero output) causes this test to exit PASS.

**[TEST-COVERAGE] `test_pluck_e5_brightness` passes on 0.001 Hz FP noise — no actual brightness burst measured** `tests/test_hey_angel_synthesis.py:135`
> `HighPluck` has no VCF — only a 2ms linear VCA ramp — so the centroid stays at ~659 Hz (the pure-sine fundamental) throughout. The assertion `c_early > c_late` is satisfied by a 0.000988 Hz artefact from Hanning window asymmetry, not from any 2500→1600 Hz brightness decay. Removing the VCA attack entirely still passes with the right timing. Fix: implement the VCF brightness burst first, then write the test to assert `c_early > 2000` and `c_late < 1800` (absolute bounds).
> Failure scenario: Any sufficiently symmetric sinusoidal output satisfies this test due to floating-point luck. The 2500→1600 Hz target is never verified.

**[TEST-COVERAGE] `test_lead_melody_c4_nondiscrete` is a non-silence check dressed as a pitch-variation test** `tests/test_hey_angel_synthesis.py:113`
> The only assertion is `rms > 0.01`. The docstring claims to verify "C4→F#3 melody (not stuck at one pitch)" — the module docstring at line 11 even admits "verified by lead render non-silence". No pitch estimation, frequency spread, spectral centroid shift, or note-count check is performed. Fix: use `pyin` or FFT-based pitch estimation over 16ths to confirm at least two distinct pitches are present.
> Failure scenario: A broken arp that plays a single sustained C4 passes this test.

**[TEST-COVERAGE] `test_kick_tail_not_truncated_at_bar_boundary` cannot distinguish spill from step-0 kick** `tests/test_seamless.py:236`
> The test asserts `spill_region_rms > 0.01` in samples `[0:8190]` of bar `kick_sync_bar+1`. The step-0 kick fires at sample 0 of that same bar and produces RMS ~0.46 on its own, far above the 0.01 threshold. The test comment at lines 212–213 acknowledges the overlap but never compensates. Fix: render two versions (with and without the step-14 spill mechanism) and assert `rms_with_spill > rms_without_spill + threshold`, or isolate a time window guaranteed to fall between step-0 onset and the spill region.
> Failure scenario: Removing the spill accumulation block entirely still produces `RMS ~0.46 > 0.01` from the step-0 kick, so the test gives a false green.

**[TEST-COVERAGE] `test_sawtooth_phase_continuity` currently fails for the correct PolyBLEP implementation** `tests/test_synth/test_oscillators.py:52`
> At 440 Hz with `n=22050` samples (exactly 220 cycles), `end_phase=0.0` and `seam_diff=0.98` for the correct implementation — the test fails right now. The 0.1 threshold also allows up to ~5 samples of phase drift at 440 Hz (audible). Fix: change the test approach — compare a concatenated chunked render against a single continuous render and assert `max_diff < 1e-5`, using a non-exact-cycle frequency to avoid the wrap-coincidence.
> Failure scenario: The test currently fails for the correct implementation and would silently pass a broken one at exact-cycle parameter points.

**[TEST-COVERAGE] No state-continuity test for `lpf2`** `tests/test_synth/test_filters.py:88`
> `lpf` has `test_lpf_state_continuity` (lines 100–114). `lpf2` has only `test_lpf2_attenuates_high_frequency` which discards the returned `zi`. The bass instrument's 64-segment acidenv filter loop in `instruments/bass.py` depends entirely on `lpf2` correctly forwarding `zi`. Fix: add a test mirroring `test_lpf_state_continuity` for `lpf2`, asserting that `single_call_output ≈ segmented_call_output` to within `~1e-5`.
> Failure scenario: A regression that silently resets `zi` in `lpf2` would cause transients at all 64 segment boundaries in `AcidBass.render` with no test catching it.

**[TEST-COVERAGE] `test_bass_portamento_pitch_shift` only checks non-silence** `tests/test_hey_angel_synthesis.py:103`
> The docstring claims to verify "frequency content should span G1→F2 range (49–87 Hz)" but the body only asserts `max > 0.01`. No FFT or frequency-domain measurement exists. Fix: measure the dominant frequency in the first 10ms (should be ~49 Hz, G1) and the last 10ms (should be ~87 Hz, F2) of the rendered segment.
> Failure scenario: A fixed-pitch bass at any audible frequency passes this test; portamento can be completely broken without detection.

---

### Minor — low priority

**[TEST-COVERAGE] `test_wide_detune_pad_has_higher_spectral_spread` passes trivially when detune is broken** `tests/test_genuine_variation.py:364`
> `centroid_wide >= centroid_tight * 0.95` and `mid_wide > mid_tight * 0.8` both pass when `wide == tight` (broken detune). Fix: change assertions to strict `>` with a meaningful epsilon (e.g. `centroid_wide > centroid_tight * 1.05`).
> Failure scenario: If `detune_cents` is silently ignored, both assertions pass with `1.0 >= 0.95` and `1.0 > 0.8`.

**[TEST-COVERAGE] `test_fast_arc_has_earlier_stages_than_slow` uses trivially weak `min <= max` comparison** `tests/test_genuine_variation.py:327`
> `min(fast_lead_on) <= max(slow_lead_on)` is true even when both sets are identical. Fix: use `max(fast_lead_on) < min(slow_lead_on)` (strict separation), or use a seed-controlled paired comparison.
> Failure scenario: If `arc_shape` has no effect and all songs produce the same `lead_melody_on` value, `min(X) <= max(X)` is trivially satisfied.

**[TEST-COVERAGE] `test_lead_fm_raises_sub_harmonic_energy` uses `>=` — passes trivially when FM is broken** `tests/test_instruments.py:248`
> `lo_with >= lo_no` passes when `fm_depth=0.55` is ignored and both renders are identical (`lo_with == lo_no`). Fix: use strict `>` with a minimum delta (e.g. `lo_with > lo_no * 1.05`).
> Failure scenario: `AcidLead` ignoring the `fm_depth` kwarg produces identical renders; `== satisfies >=`.

**[TEST-COVERAGE] `test_pad_centroid_within_reference_range` covers nearly the entire audible spectrum** `tests/test_instruments.py:314`
> The assertion is `100 Hz < centroid < 18000 Hz`. The test's own comment states reference session centroids are 425–929 Hz. Fix: tighten to `300 Hz < centroid < 1500 Hz` for the default filter setting, matching the measured reference.
> Failure scenario: Band-limited noise centered at 5 kHz or a barely-working oscillator passes this test.

**[TEST-COVERAGE] `test_audio_rms_differs_across_seeds` threshold of `> 0.0` is semantically vacuous** `tests/test_variation.py:275`
> Any two seeds that differ by even a single sample value satisfy `rms_range > 0.0`. Fix: use `rms_range > 0.01` or add a structural diversity check that confirms different harmony, BPM, or melody across seeds.
> Failure scenario: Two seeds with identical structure but different random noise seeds produce `rms_range ~1e-5` — strictly positive but perceptually identical.

**[TEST-COVERAGE] Source-inspection test checks literal text, not behavior** `tests/test_ascii_video_discovery.py:187`
> `inspect.getsource()` + string match for `'_av_color(src_ch)'` — passes if the string is inside an unreachable branch, fails if the helper is renamed. Fix: render a short clip with a known ASCII frame and assert that the output bytes match expected ANSI color codes for specific pixel positions.
> Failure scenario: Renaming `_av_color` to `_apply_av_color` breaks the test despite correct behavior; placing the call in dead code passes the test despite broken behavior.

**[TEST-COVERAGE] `test_trancegate_smooth` threshold 0.05 allows a 21-step staircase** `tests/test_synth/test_envelopes.py:95`
> The real raised-cosine produces max adjacent-sample jump ~0.000062; the threshold of 0.05 is 802x looser. A 21-step staircase (step size ~0.0476) passes while producing audible amplitude stepping. Fix: tighten to `<= 0.0006` (10x the real implementation's max jump).
> Failure scenario: A staircase gate with 21 discrete levels produces clearly audible stepping artifacts and passes the assertion.

**[DEAD-CODE] `SchroederReverb._comb_block` (mono variant) is never called** `synth/effects.py:218`
> Only `_comb_block_stereo` is invoked (at line 252). The mono variant writes only `bufs[0]`, which would silently collapse the right reverb channel to silence if accidentally used in a future refactor. Fix: delete `_comb_block` entirely.

**[DEAD-CODE] `SchroederReverb._comb_ptr` and `_ap_ptr` are assigned but never read** `synth/effects.py:214`
> Two stale fields co-exist with `_ptr`, suggesting a three-pointer design that does not exist. Fix: delete both lines from `__init__`.

**[DEAD-CODE] `SongRenderer._chord_index()` has zero callers** `song/renderer.py:460`
> The method body is `_, _, _, idx = self._chord_state(bar); return idx` — pure delegation with no unique logic. Confirmed zero callers across all source files. Fix: delete the method.

**[EFFICIENCY] `half_wet = self._wet * 0.5` recomputed 4× per `process()` call inside the FDN loop** `synth/effects.py:164`
> `self._wet` is set once in `__init__` and never mutated. Fix: hoist the assignment to just before the loop (between lines 145 and 147).

**[EFFICIENCY] Redundant `float64` casts inside comb and allpass loops** `synth/effects.py:252`
> `buf_l.astype(np.float64)` and `buf_r.astype(np.float64)` are called on each of 4 comb iterations; `rev_l/rev_r` are cast to `float32` by `_ap_block_stereo` then immediately re-cast to `float64`. Internal buffers are already `float64`. Fix: cast `buf_l/buf_r` to `float64` once before the comb loop; keep `rev_l/rev_r` as `float64` throughout; convert to `float32` only at the final return.

**[EFFICIENCY] `_get_track('kick')` called three times per bar** `song/renderer.py` (attributed incorrectly to `synth/effects.py:190`)
> `kick_track` (line 144), `kick_track2` (line 190), `kick_track3` (line 213) each perform a linear scan of `song.tracks`. `kick_track` is in scope at both later sites. Fix: replace `kick_track2` and `kick_track3` with `kick_track`.

**[CORRECTNESS/DOCSTRING] `gen_starfield.py` star wrap does not re-randomize `(x, y)`** `tools/gen_starfield.py:73`
> Docstring claims the star wraps "back to z=1.0 at a fresh random (x, y)". Lines 87–89 only add 1.0 to the local variable `z` — `(sx, sy)` are never modified and no RNG call occurs in `_render_frame`. Every star repeats its full screen trajectory with period ~55.56 frames (1/speed). Fix: on wrap, call `rand()` twice to reassign `sx` and `sy`, and reset `z` to exactly 1.0.
> Failure scenario: A 120-frame animation contains two near-identical 55-frame loops, producing a repeating stutter.

**[CORRECTNESS] LCG `rand()` divisor is `0xFFFFFFFF` instead of `0x100000000`** `tools/gen_starfield.py:54`
> Produces a closed `[0, 1]` interval; `rand()` can return exactly 1.0 when `rng == 0xFFFFFFFF`. With seed=42 the bug is latent (never fires in 540 steps). Fix: change divisor to `0x100000000` for a proper half-open `[0, 1)` interval.

---

## Architecture Observations

**Hey-angel arrangement split across two incompatible entry points.** `hey_angel_cover.py` uses `SmoothLead` (single filtered sawtooth, `render(midi_note: int)`) while `trance_stream_v3.py --style hey_angel` via `song/builder.py` uses `AcidLead(character='smooth')` (multi-voice supersaw, `render(midi_notes: list)`). These are structurally different synthesis classes with incompatible call signatures — a drop-in swap is impossible without also updating the call sites. The two paths already produce measurably different audio (different glide rates, missing bass half-bar, different gain). Any work on the hey-angel sound must be applied to both classes independently, with no type-system link to enforce consistency. A clean resolution would be to designate one path as canonical and delete the other, or to converge on a shared instrument class with a unified `render()` API.

**Three concurrent entry-point scripts with no deprecation notices.** `trance_stream.py`, `trance_stream_v2.py`, and `trance_stream_v3.py` coexist with no cross-references or deprecation markers. v1 and v2 import `sounddevice` unconditionally at module level (unguarded `ImportError` on systems without it); v3 wraps all sounddevice imports in `try/except`. Bug fixes to v3's instrument stack do not flow to v1/v2. CLAUDE.md provides no guidance on which script is current. Fix: add deprecation headers to v1 and v2 pointing to v3, and guard their `sounddevice` imports.

**Hey-angel MIDI note constants duplicated across files.** G1=43, F2=53, MELODY_START=60, MELODY_END=54, E5=76 appear as local variables in `renderer.py:276–277, 343–344, 428` and as module-level constants in `hey_angel_cover.py:38, 79–95`. F2=53 appears only as an inline literal in `BASS_PATTERN` tuples — no named constant at all. `song/theory.py` defines none of these. A measurement revision requires finding and updating two files with no static link between them.

**Monotonic stage-bars ordering pass duplicated verbatim.** `song/builder.py` contains the identical 7-line monotonic enforcement pass at lines 231–237 and 284–290. If a new stage key (e.g. `pluck_on`) is added, both copies must be updated independently. CLAUDE.md's "write everything down" principle applies here — this is the kind of silent divergence that causes `pluck_on` to be sorted correctly in the `arc_scale == 1.0` path but not the other.

**CLAUDE.md synthesis measurement requirement not fully enforced.** The FM depth constant (`instruments/pulse.py:39`) is wrong in a way that would have been caught immediately by measuring it from `research/strudel_debug.html` as required. The sidechain depth bug (`synth/effects.py:327`) similarly contradicts the stated target of `duck ratio ~0.40` from `prebake.strudel`. Measurement-first discipline would have prevented both.

---

## Test Coverage Summary

**Well-covered:**
- `synth/envelopes.py` — shape, timing, peak/trough, gate boundaries
- `synth/filters.py` — attenuation, state continuity for `lpf` (but not `lpf2`)
- `instruments/kick.py` — pitch sweep, RMS decay, timing
- `song/builder.py` — arc ordering, seed variation
- `tools/visualiser.py` — border rendering, color modes, contain mode

**Under-tested / structurally weak:**
- `synth/effects.py` — no test for sidechain residual amplification; `SchroederReverb` has only smoke tests
- `song/arcs.py` — `chord_state_at()` phase alignment across pullback is untested; `gain_arc()` with sentinel value is untested
- `song/renderer.py` — `notearp_to_midi()` with empty chord is untested; `write_midi()` output content is untested; hey-angel bass second half-bar is untested
- `instruments/pad.py` — BPM dependency of trancegate phase is untested; the one trancegate RMS variation test has a vacuous-pass bug
- `instruments/bass.py` / `instruments/lead.py` — `portamento_s` float value behavior is untested; `lpf2` state continuity is untested
- `tests/test_hey_angel_synthesis.py` — three of four tests are non-silence checks masquerading as feature tests

**Most important missing tests (in impact order):**
1. Sidechain residual amplification: render two consecutive bars with a kick only in bar 1; assert `gain[0]` in bar 2 `> 0.95`.
2. `chord_state_at()` phase continuity: assert `chord_idx(pb_bar-1) == chord_idx(pb_bar)` for a set of pullback values.
3. `notearp_to_midi()` with empty input: assert returns `[]` and does not raise.
4. `lpf2` state continuity: assert single-call and 64-segment-call outputs are within `1e-5`.
5. Hey-angel bass completeness: assert non-zero energy in second half of bar (samples `spb//2` to `spb`) for v3 path.
6. `write_midi()` output contains note events: assert `MidiFile` has `note_on` messages.
7. Pluck brightness: assert `c_early > 2000` and `c_late < 1800` (requires VCF implementation first).

---

## Recommended Next Steps

1. **Fix sidechain phantom ducking** (`synth/effects.py:327`) — add `if peak < 1e-4: skip normalization`. This corrupts every bar after the first kick in every render.

2. **Fix FM depth arc** (`instruments/pulse.py:39`) — replace `total_steps/max(total_steps,1)` with `step/max_session_steps` using a fixed denominator. The instrument has been maximally FM-modulated from step 1 in every session to date.

3. **Fix hey-angel gain** (`song/arcs.py:231`) — set `filter_pb_bar` to actual song length in `build_hey_angel_song()`, or add an explicit full-gain override for the hey-angel style.

4. **Fix `notearp_to_midi()` crash** (`song/renderer.py:514`) — add empty-chord guard. This is a latent crash in a hot path.

5. **Fix chord phase jump at pullback** (`song/arcs.py:257`) — add phase-alignment offset when changing chord weights.

6. **Fix hey-angel bass second half-bar** (`song/renderer.py:279`) — add the three missing bass events at steps 8, 12, 14.

7. **Fix `SupersawPad` BPM hardcoding** (`instruments/pad.py:91`) — add `samples_per_bar` parameter to `render()`, consistent with the lead instrument fix already applied.

8. **Fix the three vacuous test-coverage holes** (`test_instruments.py:106`, `test_seamless.py:236`, `test_oscillators.py:52`) — these give false confidence in features that may be silently broken.

9. **Add `lpf2` state-continuity test and `notearp_to_midi` empty-input test** — guard the two highest-impact untested paths.

10. **Unify hey-angel constants into `song/theory.py`** — eliminate the dual-file duplication of G1, F2, MELODY_START, MELODY_END, E5. Prerequisite for safely aligning the two entry points.

11. **Add deprecation notices to `trance_stream.py` and `trance_stream_v2.py`** — guard their `sounddevice` imports and add a header pointing to v3.

12. **Fix ASCII video relative glob** (`trance_stream_v3.py:140`) — one-line fix with high usability impact for non-cwd invocations.

13. **Extract monotonic ordering helper in `song/builder.py`** — prevents silent stage-ordering divergence when new instruments (e.g. pluck) are added.

14. **Clean up dead code** — `_comb_block`, `_comb_ptr`, `_ap_ptr`, `_chord_index()` — low risk, improves readability and prevents misleading future refactors.

15. **Converge hey-angel entry points** — designate `trance_stream_v3.py --style hey_angel` as canonical, migrate `HeyAngelRenderer` to use `AcidLead`, unify glide constant, implement second-half bass. This is the largest architectural debt item and will require coordination with ongoing sidequest work.
