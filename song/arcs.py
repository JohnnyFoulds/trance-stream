# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# song/arcs.py
# Parameter evolution functions for the song arc.
# All values sourced from song/theory.py constants.

from __future__ import annotations
import math


def filter_cutoff_arc(bar: int,
                      pullback_bar: int = 64,
                      pullback_duration: int = 8) -> float:
    """Return rlpf slider value for a given bar.

    Arc: linear rise from FILTER_ARC['start'] to FILTER_ARC['mid'] over
    FILTER_ARC_TIMING['start_to_mid_bars'] bars, then a pullback dip of
    pullback_duration bars at pullback_bar, then ramp to FILTER_ARC['full_open']
    by bar FILTER_ARC_TIMING['final_open_bar'].

    Source: docs/music_theory/02_sa_vocabulary_codified.md §5
    """
    from song.theory import FILTER_ARC, FILTER_ARC_TIMING

    start      = FILTER_ARC['start']
    mid        = FILTER_ARC['mid']
    pullback   = FILTER_ARC['pullback']
    full_open  = FILTER_ARC['full_open']
    ramp_bars  = FILTER_ARC_TIMING['start_to_mid_bars']
    final_bar  = FILTER_ARC_TIMING['final_open_bar']
    pb_end     = pullback_bar + pullback_duration

    if bar < ramp_bars:
        t = bar / ramp_bars
        return start + (mid - start) * t
    elif pullback_bar <= bar < pb_end:
        t = (bar - pullback_bar) / pullback_duration
        if t < 0.5:
            return mid + (pullback - mid) * (t * 2)
        else:
            return pullback + (mid - pullback) * ((t - 0.5) * 2)
    elif bar >= final_bar:
        return full_open
    else:
        if bar >= pb_end:
            t = (bar - pb_end) / max(final_bar - pb_end, 1)
            return mid + (full_open - mid) * t
        return mid


def fm_depth_arc(bar: int) -> float:
    """Return FM depth (0.0–FM_ARC_TARGET) for a given bar.

    Zero until FM_ARC_ONSET_BAR, then linear ramp to FM_ARC_TARGET over 16 bars.
    Source: docs/music_theory/02_sa_vocabulary_codified.md §5
    """
    from song.theory import FM_ARC_ONSET_BAR, FM_ARC_TARGET
    if bar < FM_ARC_ONSET_BAR:
        return 0.0
    ramp_bars = 16
    t = min((bar - FM_ARC_ONSET_BAR) / ramp_bars, 1.0)
    return FM_ARC_TARGET * t


def delay_wet_arc(bar: int, lead_on_bar: int = 24) -> float:
    """Return delay wet amount for the lead.

    0 before lead_melody_on, ramps from 0 to 0.7 over 8 bars after.
    Source: docs/music_theory/02_sa_vocabulary_codified.md §3
    """
    if bar < lead_on_bar:
        return 0.0
    t = min((bar - lead_on_bar) / 8.0, 1.0)
    return 0.7 * t


def hihat_decay_arc(bar: int, hihat_on_bar: int = 112) -> float:
    """Return hihat decay_s for a given bar, modulated by tri LFO.

    SA's .tri.fast(4).range(0.05, 0.12): triangle LFO at 4x bar rate.
    Source: docs/music_theory/03_trance_rhythm.md §2
    """
    from song.theory import HIHAT_DECAY_S_MIN, HIHAT_DECAY_S_MAX
    if bar < hihat_on_bar:
        return 0.08
    lfo_phase = (bar * 4) % 1.0
    tri = 1.0 - abs(2.0 * lfo_phase - 1.0)
    return HIHAT_DECAY_S_MIN + (HIHAT_DECAY_S_MAX - HIHAT_DECAY_S_MIN) * tri


def gain_arc(bar: int, base_gain: float,
             fade_in_bar: int = 0, fade_in_bars: int = 2) -> float:
    """Apply a short fade-in from silence at fade_in_bar."""
    if bar < fade_in_bar:
        return 0.0
    t = min((bar - fade_in_bar) / max(fade_in_bars, 1), 1.0)
    return base_gain * t
