"""
simulated_amu
Pure-Python model of the PEROVSAT AMU (Aerospace Measurement Unit).

Given the Sun direction, a PV device normal, and the current temperature,
produces a realistic I-V curve using a single-diode model.

No Basilisk dependency -- the optional bridge lives in basilisk_adapter.py.
"""

from .model import SimulatedAMU, AMUReading
from .pv_model import PVDevice

# Remove IVCurve from import if it doesn't exist

__all__ = [
    "SimulatedAMU",
    "AMUReading",
    "PVDevice",
]

__version__ = "0.1.0"