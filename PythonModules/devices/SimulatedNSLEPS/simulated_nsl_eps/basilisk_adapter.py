"""
basilisk_adapter.py
Optional bridge from Basilisk power messages to SimulatedNSLEPS.

This is the *only* file that imports Basilisk, kept optional so the core
sensor model stays usable without Basilisk installed.
"""

import numpy as np
from Basilisk.utilities import macros
from .model import SimulatedNSLEPS


class BasiliskEPSAdapter:
    """
    Bridge from Basilisk power management to SimulatedNSLEPS.

    Usage:
        eps = SimulatedNSLEPS(capacity_wh=100.0)
        bridge = BasiliskEPSAdapter(eps, powerInMsg)
        reading = bridge.step(currentSimNanos)
    """

    def __init__(self, eps: SimulatedNSLEPS, powerInMsg, voltageInMsg=None):
        """
        eps          : the SimulatedNSLEPS to drive
        powerInMsg   : Basilisk DoubleMsgReader with net power [W]
        voltageInMsg : optional Basilisk DoubleMsgReader with bus voltage [V]
        """
        self.eps = eps
        self.powerInMsg = powerInMsg
        self.voltageInMsg = voltageInMsg
        self.last_time_ns = 0

    def step(self, currentSimNanos):
        """Read power message, step the EPS, return the reading."""
        power_msg = self.powerInMsg.read()
        if power_msg is None:
            return None

        net_power = power_msg.data

        # Optionally update voltage
        if self.voltageInMsg is not None:
            v_msg = self.voltageInMsg.read()
            if v_msg is not None:
                self.eps.voltage_v = v_msg.data

        dt_s = (currentSimNanos - self.last_time_ns) * macros.NANO2SEC
        self.last_time_ns = currentSimNanos

        return self.eps.step_dt(net_power, dt_s, currentSimNanos * macros.NANO2SEC)