"""
sim_state.py
Wraps the live Basilisk messages that devices/power management need each
step -- the Sun geometry, eclipse shadowing, and sim time -- so devices and
the power manager can consume "simulation state" without touching Basilisk
messages directly. This is the object passed as `simulation` into every
SimulatedDevice.onMessage() call, and the thing a new environment feature
(e.g. an RTD temperature feed) would get a new attribute on.
"""

import numpy as np

from Basilisk.utilities import macros, RigidBodyKinematics as rbk

from power_system import eclipse_shadow_factor, sun_distance_factor


class SimulationState:
    def __init__(self, scStateOutMsg, sunStateInMsg):
        self.scStateOutMsg = scStateOutMsg
        self.sunStateInMsg = sunStateInMsg

        self.sim_time_s = 0.0
        self.sun_direction_body = np.array([0.0, 0.0, 1.0])
        self.shadow_factor = 1.0
        self.sun_distance_factor = 1.0
        self._last_time_ns = 0

    def update(self, currentSimNanos):
        """Refresh cached Sun geometry from the live messages. Returns the
        elapsed time [s] since the previous call to update() (0.0 if there
        isn't yet enough data to compute one, e.g. before SPICE populates
        the Sun position)."""
        scState = self.scStateOutMsg.read()
        sunState = self.sunStateInMsg.read()
        self.sim_time_s = currentSimNanos * macros.NANO2SEC
        if scState is None or sunState is None:
            return 0.0

        r_sc_N = np.array(scState.r_BN_N)
        r_sun_N = np.array(sunState.PositionVector)
        if not np.any(r_sun_N):
            return 0.0

        s = r_sun_N - r_sc_N
        dist = np.linalg.norm(s)
        if dist == 0.0:
            return 0.0

        # sigma_BN -> [BN]; MRP2C returns [BN], so v_B = [BN] v_N.
        dcm_BN = np.array(rbk.MRP2C(scState.sigma_BN)).reshape(3, 3)
        self.sun_direction_body = dcm_BN @ (s / dist)
        self.shadow_factor = eclipse_shadow_factor(r_sc_N, r_sun_N)
        self.sun_distance_factor = sun_distance_factor(s)

        dt_s = (currentSimNanos - self._last_time_ns) * macros.NANO2SEC
        self._last_time_ns = currentSimNanos
        return dt_s
