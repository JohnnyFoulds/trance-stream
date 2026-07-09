# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at https://mozilla.org/MPL/2.0/.

"""TDD tests for FM modulation timbre quality on the lead instrument.

SA reference: fm .5 in Strudel = modulator at 0.5× carrier (ratio 1:2),
mod_index ≈ 0.5. This produces warm sub-harmonic enrichment. It must NOT
produce the reed/harmonica sound caused by ratio 4:1 + high mod_index,
which creates dominant odd-partial sidebands at 3×, 5×, 7× carrier.

Measured bug (current code, mod_freq = carrier*4, mod_index = fm_depth*4):
  - 3× carrier (1320 Hz for A4) holds 37% of FM-voice spectral energy
  - 5× carrier (2200 Hz) holds 20%
  - RMS nearly doubles when FM enabled (fraction = 0.49)
  These three properties encode "sounds like a harmonica". Each test
  is RED against current code, GREEN after the fix.
"""

from __future__ import annotations

import sys
import pathlib

import numpy as np
import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

SR = 44100
SPB = int(SR * 4 * 60 / 140.0)
TEST_NOTE = 69          # A4 = 440 Hz — easy to reason about sidebands
CARRIER_HZ = 440.0


def _render_lead_fm(fm_depth: float) -> tuple:
    """Render one bar of lead, return (l, r) at given fm_depth."""
    from instruments.lead import AcidLead
    lead = AcidLead(root_midi=48, sr=SR, character='acid')
    return lead.render([TEST_NOTE], SPB, fm_depth=fm_depth)


def _fm_only(fm_depth: float = 0.55) -> np.ndarray:
    """Return the FM contribution in isolation (mono: with_fm - without_fm)."""
    l_base, _ = _render_lead_fm(0.0)
    l_fm,   _ = _render_lead_fm(fm_depth)
    return l_fm - l_base


def _bin_energy_fraction(buf: np.ndarray, target_hz: float,
                          tol_hz: float = 35.0) -> float:
    """Fraction of total spectral energy within tol_hz of target_hz."""
    spec  = np.abs(np.fft.rfft(buf * np.hanning(len(buf)))) ** 2
    freqs = np.fft.rfftfreq(len(buf), 1.0 / SR)
    total = spec.sum()
    if total == 0:
        return 0.0
    return float(spec[np.abs(freqs - target_hz) < tol_hz].sum() / total)


def _rms(buf: np.ndarray) -> float:
    return float(np.sqrt(np.mean(buf ** 2)))


# ---------------------------------------------------------------------------
# Tests — RED against current code (ratio 4:1, index 2.2), GREEN after fix
# ---------------------------------------------------------------------------

class TestFMNotReedTimbre:
    """FM must not produce the reed/harmonica odd-partial spectrum."""

    def test_3x_carrier_not_dominant(self):
        """3× carrier (1320 Hz for A4) must not dominate the FM voice.

        Ratio 4:1 FM places its strongest sideband at carrier + mod_freq - mod_freq
        = 3× carrier via Bessel J1 term. Measured at 37% of energy — the primary
        cause of the reed/harmonica timbre.

        Fix: ratio 1:2 puts no energy at 3× carrier.
        Threshold: < 0.10 (current code: ~0.37) — 3× sideband not dominant.
        """
        fm_only = _fm_only(0.55)
        energy_3x = _bin_energy_fraction(fm_only, CARRIER_HZ * 3.0)
        assert energy_3x < 0.10, (
            f"FM sideband at 3× carrier ({CARRIER_HZ*3:.0f} Hz) = {energy_3x:.3f} "
            f"of FM energy (must be < 0.10). "
            f"This is the reed/harmonica partial from ratio 4:1 FM. "
            f"Fix: set mod_freq = carrier_freq * 0.5"
        )

    def test_5x_carrier_not_dominant(self):
        """5× carrier (2200 Hz for A4) must not be a significant peak.

        Ratio 4:1 FM places energy at 5× carrier (Bessel J2 sideband).
        Measured at 20% of FM-voice energy — contributes to nasal quality.

        Threshold: < 0.08 (current code: ~0.20).
        """
        fm_only = _fm_only(0.55)
        energy_5x = _bin_energy_fraction(fm_only, CARRIER_HZ * 5.0)
        assert energy_5x < 0.08, (
            f"FM sideband at 5× carrier ({CARRIER_HZ*5:.0f} Hz) = {energy_5x:.3f} "
            f"of FM energy (must be < 0.08). "
            f"Fix: set mod_freq = carrier_freq * 0.5"
        )


class TestFMEnrichesWithoutDominating:
    """FM voice must enrich the supersaw, not overpower it."""

    def test_fm_rms_contribution_bounded(self):
        """FM must not nearly double the lead RMS.

        Current code: RMS fraction = 0.49 (FM adds as much energy as the saw).
        SA's fm .5 at index 0.55 should contribute < 25% of total RMS.

        Threshold: < 0.25 (current code: ~0.49).
        """
        l_base, _ = _render_lead_fm(0.0)
        l_fm,   _ = _render_lead_fm(0.55)

        rms_base = _rms(l_base)
        rms_fm   = _rms(l_fm)

        if rms_base == 0:
            pytest.skip("base render silent")

        fm_fraction = (rms_fm - rms_base) / max(rms_fm, 1e-9)
        assert fm_fraction < 0.25, (
            f"FM raises RMS by {fm_fraction:.2%} (must be < 25%). "
            f"FM is overpowering the supersaw. "
            f"Fix: reduce mod_index multiplier from *4.0 to *1.0"
        )
