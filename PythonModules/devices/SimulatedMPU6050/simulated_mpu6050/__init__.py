"""
simulated_mpu6050
Register-level model of the InvenSense MPU-6050 6-axis IMU (3-axis gyro +
3-axis accelerometer + temperature). Pure Python/numpy, no Basilisk dependency
-- feed it truth motion, get back the counts a real part would report.

The optional Basilisk bridge lives in ``basilisk_adapter`` and is intentionally
not imported here, so importing this package never requires Basilisk.
"""

from .model import SimulatedMPU6050, Reading
from .registers import GyroRange, AccelRange
from .kinematics import specific_force_at_offset

__all__ = [
    "SimulatedMPU6050",
    "Reading",
    "GyroRange",
    "AccelRange",
    "specific_force_at_offset",
]

__version__ = "0.1.0"
