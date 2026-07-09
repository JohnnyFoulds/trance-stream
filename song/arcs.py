# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

# song/arcs.py
# Parameter evolution functions for the song arc.
# All values sourced from song/theory.py constants.

from __future__ import annotations
import math

# ---------------------------------------------------------------------------
# Macro cycle engine
# ---------------------------------------------------------------------------
# After the initial build phase (bars 0 → CYCLE_START), the song enters a
# repeating 64-bar cycle. Each cycle has the same shape as the opening arc:
#   - 32 bars: filter rises from mid to full_open
#   - 4 bars:  breakdown (all voices except kick+pad drop out)
#   - 8 bars:  filter dips to pullback (tension / dark section)
#   - 20 bars: filter reopens to full_open (release, energy returns)
#
# This means every 64 bars the listener hears: brightness build → strip back
# → darkness → full release. Identical to what SA does manually — she just
# moves the slider and mutes voices in real time.

CYCLE_LENGTH    = 64   # bars per macro cycle
CYCLE_BREAKDOWN = 4    # bars of breakdown within each cycle (voices strip out)
CYCLE_DIP_BARS  = 8    # bars the filter spends at pullback depth
CYCLE_RISE_BARS = 32   # bars before the dip where filter climbs to full_open


def _cycle_filter(cycle_bar: int) -> float:
    """Filter slider value for position within a 64-bar macro cycle.

    cycle_bar 0..31:  rises mid (0.60) → full_open (0.877)
    cycle_bar 32..35: breakdown window (no voices — filter stays at full_open)
    cycle_bar 36..43: filter dips to pullback (0.35) and returns to mid
    cycle_bar 44..63: filter rises mid (0.60) → full_open (0.877)
    """
    from song.theory import FILTER_ARC
    mid       = FILTER_ARC['mid']
    pullback  = FILTER_ARC['pullback']
    full_open = FILTER_ARC['full_open']

    if cycle_bar < CYCLE_RISE_BARS:
        # Rise: mid → full_open over 32 bars
        t = cycle_bar / CYCLE_RISE_BARS
        return mid + (full_open - mid) * t

    dip_start = CYCLE_RISE_BARS + CYCLE_BREAKDOWN   # bar 36
    dip_end   = dip_start + CYCLE_DIP_BARS           # bar 44
    rise2_end = CYCLE_LENGTH                         # bar 64

    if cycle_bar < dip_start:
        # Breakdown window: filter stays bright to let the silence speak
        return full_open

    if cycle_bar < dip_end:
        # Dip: full_open → pullback → mid over 8 bars (triangle)
        t = (cycle_bar - dip_start) / CYCLE_DIP_BARS
        if t < 0.5:
            return full_open + (pullback - full_open) * (t * 2)
        else:
            return pullback + (mid - pullback) * ((t - 0.5) * 2)

    # Recovery: mid → full_open over remaining bars
    t = (cycle_bar - dip_end) / max(rise2_end - dip_end, 1)
    return mid + (full_open - mid) * t


def _cycle_fm(cycle_bar: int) -> float:
    """FM depth for position within a macro cycle.

    FM dims during the breakdown/dip (0.15 at minimum) then returns to 0.55.
    This gives the dark section a cleaner, less busy timbre.
    """
    from song.theory import FM_ARC_TARGET
    dip_start = CYCLE_RISE_BARS + CYCLE_BREAKDOWN   # 36
    dip_end   = dip_start + CYCLE_DIP_BARS           # 44

    if cycle_bar < dip_start:
        return FM_ARC_TARGET   # full depth in bright section

    if cycle_bar < dip_end:
        # Dim during the dip
        t = (cycle_bar - dip_start) / CYCLE_DIP_BARS
        if t < 0.5:
            return FM_ARC_TARGET + (0.10 - FM_ARC_TARGET) * (t * 2)
        else:
            return 0.10 + (FM_ARC_TARGET - 0.10) * ((t - 0.5) * 2)

    return FM_ARC_TARGET


def _cycle_breakdown(cycle_bar: int) -> bool:
    """True during the 4-bar breakdown window of each macro cycle."""
    return CYCLE_RISE_BARS <= cycle_bar < CYCLE_RISE_BARS + CYCLE_BREAKDOWN


def _cycle_pad_segs(cycle_bar: int) -> int:
    """Pad retrigger count for a cycle position.

    16 when fully open, drops to 4 during the dark dip to reduce busyness.
    """
    dip_start = CYCLE_RISE_BARS + CYCLE_BREAKDOWN
    dip_end   = dip_start + CYCLE_DIP_BARS
    if dip_start <= cycle_bar < dip_end:
        return 4
    return 16


# ---------------------------------------------------------------------------
# Public arc functions
# ---------------------------------------------------------------------------

def filter_cutoff_arc(bar: int,
                      pullback_bar: int = 64,
                      pullback_duration: int = 8) -> float:
    """Return rlpf slider value for a given bar.

    Opening phase (bar 0 → CYCLE_START): classic linear rise with single
    pullback dip. After CYCLE_START the macro cycle engine takes over and
    the filter sweeps through a new 64-bar cycle every time.

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

    # Opening phase: bars 0 through (final_bar + CYCLE_LENGTH)
    cycle_start = final_bar + CYCLE_LENGTH   # e.g. bar 96 + 64 = 160

    if bar < cycle_start:
        # Original opening arc
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

    # Macro cycle phase: repeating 64-bar cycles
    cycle_bar = (bar - cycle_start) % CYCLE_LENGTH
    return _cycle_filter(cycle_bar)


def fm_depth_arc(bar: int) -> float:
    """Return FM depth (0.0–FM_ARC_TARGET) for a given bar.

    Opening phase: zero until FM_ARC_ONSET_BAR, ramps over 16 bars.
    Macro cycle phase: follows cycle shape — dims during dark sections.
    Source: docs/music_theory/02_sa_vocabulary_codified.md §5
    """
    from song.theory import FM_ARC_ONSET_BAR, FM_ARC_TARGET, FILTER_ARC_TIMING

    final_bar   = FILTER_ARC_TIMING['final_open_bar']
    cycle_start = final_bar + CYCLE_LENGTH

    if bar < FM_ARC_ONSET_BAR:
        return 0.0

    if bar < cycle_start:
        ramp_bars = 16
        t = min((bar - FM_ARC_ONSET_BAR) / ramp_bars, 1.0)
        return FM_ARC_TARGET * t

    # Macro cycle phase
    cycle_bar = (bar - cycle_start) % CYCLE_LENGTH
    return _cycle_fm(cycle_bar)


def delay_wet_arc(bar: int, lead_on_bar: int = 24) -> float:
    """Delay wet for the lead — kept for API compatibility; renderer uses CA density."""
    if bar < lead_on_bar:
        return 0.0
    return min((bar - lead_on_bar) / 8.0, 1.0) * 0.7


def hihat_decay_arc(bar: int, hihat_on_bar: int = 112) -> float:
    """Return hihat decay_s for a given bar, modulated by tri LFO.

    SA's .tri.fast(4).range(0.05, 0.12): triangle LFO at 4x bar rate.
    Source: docs/music_theory/03_trance_rhythm.md §2
    """
    from song.theory import HIHAT_DECAY_S_MIN, HIHAT_DECAY_S_MAX
    if bar < hihat_on_bar:
        return 0.08
    # Use fractional bar counter to avoid (int * 4) % 1.0 = 0 bug
    lfo_phase = (bar * 0.25) % 1.0   # 0.25 cycles per bar = 4 bars per cycle
    tri = 1.0 - abs(2.0 * lfo_phase - 1.0)
    return HIHAT_DECAY_S_MIN + (HIHAT_DECAY_S_MAX - HIHAT_DECAY_S_MIN) * tri


def breakdown_at(bar: int, song: 'Song') -> bool:
    """True during any breakdown window — opening or recurring macro cycle."""
    from song.theory import FILTER_ARC_TIMING
    final_bar   = FILTER_ARC_TIMING['final_open_bar']
    cycle_start = final_bar + CYCLE_LENGTH

    # Opening breakdown: 4 bars before the initial pullback
    pb = song.filter_pb_bar
    if pb - 4 <= bar < pb:
        return True

    # Recurring breakdown: once per 64-bar cycle after cycle_start
    if bar >= cycle_start:
        cycle_bar = (bar - cycle_start) % CYCLE_LENGTH
        return _cycle_breakdown(cycle_bar)

    return False


def gain_arc(bar: int, song: 'Song') -> float:
    """Master gain multiplier that builds over the opening (0.55 → 1.0)."""
    ramp_end = song.filter_pb_bar
    if bar >= ramp_end:
        return 1.0
    return 0.55 + 0.45 * (bar / max(ramp_end, 1))


def pad_seg_count(bar: int, song: 'Song') -> int:
    """Number of times the pad filter envelope retriggers per bar.

    1 until pad_chord_on (drone). 16 when bright/open.
    Drops to 4 during macro cycle dip sections to reduce busyness.
    """
    from song.theory import FILTER_ARC_TIMING
    if bar < song.stage_bars.get('pad_chord_on', 9999):
        return 1

    final_bar   = FILTER_ARC_TIMING['final_open_bar']
    cycle_start = final_bar + CYCLE_LENGTH
    if bar >= cycle_start:
        cycle_bar = (bar - cycle_start) % CYCLE_LENGTH
        return _cycle_pad_segs(cycle_bar)

    return 16


def chord_state_at(bar: int, song: 'Song') -> tuple:
    """Return (chord_prog, chord_weights, effective_root_midi) for a given bar.

    Before the pullback bar: progression A, weights [3,1,3,1], original root.
    After the pullback: progression B, tightened weights [2,1,2,1], root+shift.

    This is a pure function — no side effects. Used by both the renderer
    and the visualiser so both agree on which chord is playing.
    """
    from song.theory import PAD_CHORD_WEIGHTS

    if bar < song.filter_pb_bar:
        prog    = song.chord_prog
        weights = song.chord_weights if song.chord_weights else PAD_CHORD_WEIGHTS
        root    = song.root_midi
    else:
        prog    = song.chord_prog_b if song.chord_prog_b else song.chord_prog
        # Tighten weights after pullback: [3,1,3,1] → [2,1,2,1]
        base_w  = song.chord_weights if song.chord_weights else PAD_CHORD_WEIGHTS
        weights = [max(1, w - 1) for w in base_w]
        root    = song.root_midi + (song.root_shift if song.root_shift else 0)

    return prog, weights, root
