"""
simulated_nsl_eps
Pure-Python model of the NSL Electrical Power System (EPS).

Tracks battery state of charge (SOC), energy, voltage, and operational status.
No Basilisk dependency -- the optional bridge lives in basilisk_adapter.py.
"""

from .model import SimulatedNSLEPS, EPSReading

__all__ = [
    "SimulatedNSLEPS",
    "EPSReading",
]

__version__ = "0.1.0"