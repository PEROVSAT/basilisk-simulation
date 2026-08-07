"""
kinematics.py
Rigid-body helpers for turning a spacecraft's motion into what an IMU that is
*not* mounted at the centre of mass actually feels. Pure numpy, no Basilisk.

An accelerometer measures specific force (proper acceleration), not coordinate
acceleration. A body in orbit is in free fall, so the specific force at the
centre of mass is ~0 (microgravity) -- only non-gravitational forces like drag
show up there, and for a CubeSat those are tiny. The signal an accelerometer
sees during a tumble comes almost entirely from its offset r from the centre
of mass: the centripetal term omega x (omega x r) and the Euler/tangential
term omega_dot x r. This module builds that vector so the sensor model can
stay a pure "specific force in -> counts out" device.
"""

import numpy as np


def specific_force_at_offset(omega, omega_dot, r_offset,
                             specific_force_cm=None):
    """
    Specific force felt at a point offset ``r_offset`` from the centre of mass
    of a rigid body rotating at ``omega`` with angular acceleration
    ``omega_dot``. All vectors are expressed in the same (body) frame.

    omega             : angular velocity [rad/s], shape (3,)
    omega_dot         : angular acceleration [rad/s^2], shape (3,)
    r_offset          : sensor position relative to CoM [m], shape (3,)
    specific_force_cm : specific force at the CoM [m/s^2], shape (3,); defaults
                        to zero (free fall / negligible drag).

    Returns the specific force [m/s^2] at the sensor, shape (3,).
    """
    omega = np.asarray(omega, dtype=float)
    omega_dot = np.asarray(omega_dot, dtype=float)
    r_offset = np.asarray(r_offset, dtype=float)

    centripetal = np.cross(omega, np.cross(omega, r_offset))
    euler = np.cross(omega_dot, r_offset)

    total = centripetal + euler
    if specific_force_cm is not None:
        total = total + np.asarray(specific_force_cm, dtype=float)
    return total
