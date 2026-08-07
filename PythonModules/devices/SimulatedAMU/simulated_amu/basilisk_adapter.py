"""
basilisk_adapter.py
Optional bridge from Basilisk spacecraft state to SimulatedAMU.
"""

import numpy as np
from Basilisk.utilities import macros, RigidBodyKinematics as rbk
from .model import SimulatedAMU


class BasiliskAMUAdapter:
    def __init__(self, amu, scStateOutMsg, sunStateMsg,
                 device_normal, temp_sensor=None):
        """
        amu              : the SimulatedAMU to drive
        scStateOutMsg    : Basilisk spacecraft state message
        sunStateMsg      : SPICE sun state message
        device_normal    : device normal in body frame
        temp_sensor      : optional temperature reading
        """
        self.amu = amu
        self.scStateOutMsg = scStateOutMsg
        self.sunStateMsg = sunStateMsg
        self.device_normal = np.array(device_normal) / np.linalg.norm(device_normal)
        self.temp_sensor = temp_sensor

    def step(self, currentSimNanos):
        scState = self.scStateOutMsg.read()
        sunState = self.sunStateMsg.read()
        if scState is None or sunState is None:
            return None

        # Sun direction in inertial frame
        r_sc = np.array(scState.r_BN_N)
        r_sun = np.array(sunState.PositionVector)
        s = r_sun - r_sc
        if np.linalg.norm(s) == 0:
            return None
        sun_dir_inertial = s / np.linalg.norm(s)

        # Body frame
        dcm_BN = np.array(rbk.MRP2C(scState.sigma_BN)).reshape(3, 3)
        sun_dir_body = dcm_BN @ sun_dir_inertial

        # Temperature
        temp = 25.0
        if self.temp_sensor is not None:
            temp = self.temp_sensor.get_temp()

        return self.amu.sample(
            sun_dir_body, self.device_normal, temp,
            sim_time_s=currentSimNanos * macros.NANO2SEC
        )