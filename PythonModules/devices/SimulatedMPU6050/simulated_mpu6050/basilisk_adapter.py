"""
basilisk_adapter.py
Optional bridge from a Basilisk spacecraft-state message to SimulatedMPU6050.

This is the *only* file in the package that imports Basilisk, and it is not
imported by ``__init__`` -- so the sensor model stays usable (and testable)
without Basilisk installed. Import this module explicitly when you want to run
the IMU inside a live sim.

It reads the truth the flight IMU can't know it's being handed -- the body
angular velocity/acceleration and the non-gravitational (specific) force at the
hub -- resolves the specific force at the sensor's mounting offset, optionally
rotates truth into the sensor frame, and drives one sample() per step.

    from simulated_mpu6050 import SimulatedMPU6050, GyroRange
    from simulated_mpu6050.basilisk_adapter import BasiliskMPU6050Adapter

    imu = SimulatedMPU6050(gyro_range=GyroRange.DPS_500)
    bridge = BasiliskMPU6050Adapter(imu, scObject.scStateOutMsg,
                                    mount_offset_m=[0.04, 0.02, 0.03])
    # each task step:
    reading = bridge.step(currentSimNanos)

When lockstep/SITL comms land, this same adapter is where a command interface
would hook in; for now it just executes the core measurement.
"""

import numpy as np

from Basilisk.utilities import macros

from .model import SimulatedMPU6050


class BasiliskMPU6050Adapter:
    def __init__(self, sensor: SimulatedMPU6050, scStateOutMsg,
                 mount_offset_m=(0.0, 0.0, 0.0), dcm_SB=None):
        """
        sensor        : the SimulatedMPU6050 to drive
        scStateOutMsg : Basilisk spacecraft state output message (readable)
        mount_offset_m: sensor position relative to the body point B / CoM,
                        expressed in the body frame [m]
        dcm_SB        : optional 3x3 rotation from body frame to sensor frame;
                        defaults to identity (sensor axes aligned with body).
        """
        self.sensor = sensor
        self.scStateOutMsg = scStateOutMsg
        self.r_offset_body = np.asarray(mount_offset_m, dtype=float)
        self.dcm_SB = np.eye(3) if dcm_SB is None else np.asarray(dcm_SB, dtype=float)

    def step(self, currentSimNanos):
        """Read the live state, feed one sample, return the Reading (or None
        if the state message hasn't been populated yet)."""
        state = self.scStateOutMsg.read()
        if state is None:
            return None

        omega_B = np.array(state.omega_BN_B)
        omega_dot_B = np.array(state.omegaDot_BN_B)
        a_cm_B = np.array(state.nonConservativeAccelpntB_B)

        # Specific force at the mounting point, still in the body frame, then
        # rotate the whole measurement triad into the sensor frame.
        from .kinematics import specific_force_at_offset
        f_B = specific_force_at_offset(omega_B, omega_dot_B,
                                       self.r_offset_body, a_cm_B)

        omega_S = self.dcm_SB @ omega_B
        f_S = self.dcm_SB @ f_B

        return self.sensor.sample(
            omega_rad_s=omega_S,
            specific_force_m_s2=f_S,
            sim_time_s=currentSimNanos * macros.NANO2SEC,
        )
