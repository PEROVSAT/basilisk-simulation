"""
model.py
SimulatedAMU -- a register-level model of the PEROVSAT AMU.

Core measurement: given the Sun direction and a PV device normal, generate
a realistic I-V curve using the single-diode model with temperature correction.
"""

from dataclasses import dataclass
import numpy as np

from .pv_model import PVDevice
from . import registers as reg  


@dataclass
class AMUReading:
    """One AMU measurement: I-V curve and summary metrics."""
    sim_time_s: float
    irradiance_w_m2: float
    temp_c: float
    sun_angle_deg: float
    voltage_V: np.ndarray
    current_A: np.ndarray
    voc: float
    isc: float
    pmax: float
    vmp: float
    imp: float
    ff: float

    def __repr__(self):
        return (f"AMUReading(t={self.sim_time_s:.3f}s  "
                f"G={self.irradiance_w_m2:.0f} W/m²  T={self.temp_c:+.1f}°C  "
                f"Voc={self.voc:.4f}V  Isc={self.isc:.2e}A  FF={self.ff:.3f})")


class SimulatedAMU:
    """
    Simulated PEROVSAT AMU.

    Parameters
    ----------
    cell_area_m2 : float
        PV cell area in m²
    voc_ref : float
        Reference open-circuit voltage at 25°C, 1 sun
    isc_ref : float
        Reference short-circuit current at 25°C, 1 sun
    n_diode : float
        Diode ideality factor (1-2)
    rs : float
        Series resistance (Ω)
    rsh : float
        Shunt resistance (Ω)
    temp_coeff_voc : float
        Voc temperature coefficient (1/K)
    temp_coeff_isc : float
        Isc temperature coefficient (1/K)
    eg_ev : float
        Bandgap energy (eV)
    """

    def __init__(self,
                 cell_area_m2=1e-4,
                 voc_ref=reg.VOC_REF,
                 isc_ref=reg.ISC_REF,
                 n_diode=reg.N_DIODE,
                 rs=reg.RS,
                 rsh=reg.RSH,
                 temp_coeff_voc=reg.TEMP_COEFF_VOC,
                 temp_coeff_isc=reg.TEMP_COEFF_ISC,
                 eg_ev=reg.EG_EV):
        self.cell_area_m2 = cell_area_m2
        self.voc_ref = voc_ref
        self.isc_ref = isc_ref
        self.n = n_diode
        self.rs = rs
        self.rsh = rsh
        self.temp_coeff_voc = temp_coeff_voc
        self.temp_coeff_isc = temp_coeff_isc
        self.eg_ev = eg_ev

        self.last_reading = None

    def sample(self, sun_direction_body, device_normal,
               temp_c=25.0, sim_time_s=0.0):
        """
        Take one measurement.

        sun_direction_body : unit vector from the device to the Sun
        device_normal      : unit normal of the PV device face
        temp_c             : device temperature [°C]
        sim_time_s         : timestamp for the reading
        """
        # Compute sun angle and irradiance
        cos_angle = np.dot(sun_direction_body, device_normal)
        cos_angle = max(0.0, min(1.0, cos_angle))
        irradiance = reg.SOLAR_CONSTANT * cos_angle
        sun_angle_deg = np.degrees(np.arccos(cos_angle))

        # Generate I-V curve
        pv = PVDevice(self.cell_area_m2, self.voc_ref, self.isc_ref,
                      self.n, self.rs, self.rsh,
                      self.temp_coeff_voc, self.temp_coeff_isc,
                      self.eg_ev)
        V, I, summary = pv.curve(irradiance, temp_c, num=reg.IV_CURVE_POINTS)

        reading = AMUReading(
            sim_time_s=sim_time_s,
            irradiance_w_m2=irradiance,
            temp_c=temp_c,
            sun_angle_deg=sun_angle_deg,
            voltage_V=V,
            current_A=I,
            voc=summary['voc'],
            isc=summary['isc'],
            pmax=summary['pmax'],
            vmp=summary['vmp'],
            imp=summary['imp'],
            ff=summary['ff'],
        )
        self.last_reading = reading
        return reading