"""
sysmodels.py
Basilisk SysModels that base.py attaches to simulation tasks: a console
orientation monitor and the power/payload driver. Kept out of base.py so the
experiment framework there stays focused on assembly and lifecycle.
"""

import os
import sys

import numpy as np

from Basilisk.architecture import sysModel
from Basilisk.utilities import macros
from Basilisk.utilities import RigidBodyKinematics as rbk

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "PythonModules"))
from power_system import eclipse_shadow_factor, sun_distance_factor


class OrientationMonitor(sysModel.SysModel):
    """Prints sim time, attitude MRP and body rate on a coarse task."""

    def __init__(self, scStateOutMsg):
        super().__init__()
        self.ModelTag = "OrientationMonitor"
        self.scStateOutMsg = scStateOutMsg

    def UpdateState(self, currentSimNanos):
        state = self.scStateOutMsg.read()
        t_s = currentSimNanos * macros.NANO2SEC
        sigma = state.sigma_BN
        omega_deg = np.degrees(state.omega_BN_B)
        omega_mag_deg = np.degrees(np.linalg.norm(state.omega_BN_B))
        print(
            f"t={t_s:10.1f}s  sigma_BN=[{sigma[0]:+.4f}, {sigma[1]:+.4f}, {sigma[2]:+.4f}]"
            f"  omega_BN_B=[{omega_deg[0]:+.4f}, {omega_deg[1]:+.4f}, {omega_deg[2]:+.4f}] deg/s"
            f"  |omega|={omega_mag_deg:.4f} deg/s"
        )


class PowerManager(sysModel.SysModel):
    """
    Drives the PowerSystem (and optional payload) from the live simulation
    state: reads the real Sun position from SPICE and the spacecraft
    position/attitude, computes the body-frame Sun direction, the eclipse
    shadow factor, and the 1/r^2 irradiance scaling, then advances the power
    model each task step.
    """

    def __init__(self, power_system, scStateOutMsg, sunStateInMsg, payload=None):
        super().__init__()
        self.ModelTag = "PowerManager"
        self.power_system = power_system
        self.scStateOutMsg = scStateOutMsg
        self.sunStateInMsg = sunStateInMsg
        self.payload = payload
        self.last_time_ns = 0

    def UpdateState(self, currentSimNanos):
        scState = self.scStateOutMsg.read()
        sunState = self.sunStateInMsg.read()
        if scState is None or sunState is None:
            return

        # Earth-centred inertial positions [m] (zeroBase="earth" in the SPICE
        # setup, so both are relative to Earth's centre).
        r_sc_N = np.array(scState.r_BN_N)
        r_sun_N = np.array(sunState.PositionVector)
        if not np.any(r_sun_N):        # SPICE not populated yet (first tick guard)
            return

        s = r_sun_N - r_sc_N           # spacecraft -> Sun
        dist = np.linalg.norm(s)
        if dist == 0.0:
            return

        # sigma_BN -> [BN]; MRP2C returns [BN], so v_B = [BN] v_N.
        dcm_BN = np.array(rbk.MRP2C(scState.sigma_BN)).reshape(3, 3)
        sun_dir_body = dcm_BN @ (s / dist)

        shadow = eclipse_shadow_factor(r_sc_N, r_sun_N)
        sdf = sun_distance_factor(s)

        dt_s = (currentSimNanos - self.last_time_ns) * macros.NANO2SEC
        if dt_s > 0:
            self.power_system.step(dt_s, sun_direction_body=sun_dir_body,
                                   shadow_factor=shadow, sun_distance_factor=sdf)
            if self.payload is not None:
                self.payload.step(dt_s, sun_direction_body=sun_dir_body,
                                  shadow_factor=shadow, sun_distance_factor=sdf)
            self.last_time_ns = currentSimNanos
