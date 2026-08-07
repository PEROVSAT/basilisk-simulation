"""
pv_model.py
Single-diode PV model for the PEROVSAT AMU.
"""

import numpy as np
from . import registers as reg  


class PVDevice:
    """Single-diode PV device model."""

    def __init__(self, area_m2, voc_ref, isc_ref,
                 n_diode, rs, rsh,
                 temp_coeff_voc, temp_coeff_isc,
                 eg_ev):
        self.area = area_m2
        self.voc_ref = voc_ref
        self.isc_ref = isc_ref
        self.n = n_diode
        self.rs = rs
        self.rsh = rsh
        self.temp_coeff_voc = temp_coeff_voc
        self.temp_coeff_isc = temp_coeff_isc
        self.eg_ev = eg_ev

    def curve(self, irradiance, temp_c, num=40):
        """Generate I-V curve using single-diode model."""
        temp_k = temp_c + 273.15
        Vt = 8.61733e-5 * temp_k

        # Temperature and irradiance corrections
        temp_corr = 1.0 - self.temp_coeff_voc * (temp_c - 25.0)
        irrad_corr = irradiance / reg.SOLAR_CONSTANT

        voc = self.voc_ref * temp_corr * max(irrad_corr, 0.01)
        isc = self.isc_ref * irrad_corr

        # Generate curve
        V = np.linspace(0, voc, num)
        I = isc * (1 - np.exp((V - voc) / (self.n * Vt)))
        I = np.maximum(I, 0.0)

        # Calculate summary metrics
        P = V * I
        idx = np.argmax(P)
        pmax = P[idx]
        vmp = V[idx]
        imp = I[idx]
        ff = pmax / (voc * isc) if voc * isc > 0 else 0

        return V, I, {
            'voc': voc,
            'isc': isc,
            'vmp': vmp,
            'imp': imp,
            'pmax': pmax,
            'ff': ff,
        }