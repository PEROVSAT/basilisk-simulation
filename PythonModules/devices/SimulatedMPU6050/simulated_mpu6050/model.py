"""
model.py
SimulatedMPU6050 -- a register-level model of the InvenSense MPU-6050 IMU.

Core measurement (the whole point of this device): given the *true* motion of
the body it is bolted to, produce the same 16-bit accelerometer, gyroscope and
temperature register values a real MPU-6050 would report over I2C -- including
full-scale-range quantisation, saturation, zero-rate bias and Gaussian noise.

The model is deliberately Basilisk-free: it takes truth in SI units and hands
back counts + engineering values. Anything that produces truth (a Basilisk
sim, a bench replay, a unit test) can drive it; see ``basilisk_adapter.py`` for
the optional bridge to a live spacecraft state message.

Typical use:

    imu = SimulatedMPU6050(gyro_range=GyroRange.DPS_500)
    reading = imu.sample(omega_rad_s=[0.0, 0.0, 0.09],      # ~5 deg/s spin
                         specific_force_m_s2=[0.0, 0.0, 0.0])
    reading.gyro_dps        # -> array, what a driver would decode
    imu.read_block(...)     # -> raw bytes, what the I2C bus would return
"""

from dataclasses import dataclass, field

import numpy as np

from . import registers as reg


@dataclass
class Reading:
    """One MPU-6050 sample, both as raw counts and decoded engineering units."""
    sim_time_s: float
    accel_raw: np.ndarray          # int16 counts, shape (3,)
    gyro_raw: np.ndarray           # int16 counts, shape (3,)
    temp_raw: int                  # int16 counts
    accel_g: np.ndarray            # g, shape (3,)
    accel_m_s2: np.ndarray         # m/s^2, shape (3,)
    gyro_dps: np.ndarray           # deg/s, shape (3,)
    gyro_rad_s: np.ndarray         # rad/s, shape (3,)
    temp_c: float                  # deg C
    saturated: bool = field(default=False)   # any axis clipped to +/-32k

    def __repr__(self):
        gx, gy, gz = self.gyro_dps
        ax, ay, az = self.accel_g
        sat = "  [SATURATED]" if self.saturated else ""
        return (f"Reading(t={self.sim_time_s:.3f}s  "
                f"gyro=[{gx:+.3f}, {gy:+.3f}, {gz:+.3f}] deg/s  "
                f"accel=[{ax:+.4f}, {ay:+.4f}, {az:+.4f}] g  "
                f"temp={self.temp_c:.2f} C{sat})")


class SimulatedMPU6050:
    """
    Register-level MPU-6050 model.

    Parameters
    ----------
    gyro_range, accel_range : GyroRange / AccelRange
        Full-scale ranges (set the LSB sensitivity and saturation limits).
    gyro_bias_dps, accel_bias_g : array-like (3,)
        Constant zero-rate / zero-g offsets added before quantisation. Real
        parts ship with substantial, part-to-part offsets; default is zero so
        tests are deterministic.
    gyro_noise_rms_dps, accel_noise_rms_g : float
        Per-axis Gaussian noise (RMS) in engineering units. Defaults are
        representative of the datasheet output noise at default bandwidth.
    temp_c : float
        Ambient/die temperature reported when a sample doesn't override it.
    seed : int or None
        Seeds the internal RNG for reproducible noise.
    """

    def __init__(self,
                 gyro_range=reg.GyroRange.DPS_250,
                 accel_range=reg.AccelRange.G_2,
                 gyro_bias_dps=(0.0, 0.0, 0.0),
                 accel_bias_g=(0.0, 0.0, 0.0),
                 gyro_noise_rms_dps=0.05,
                 accel_noise_rms_g=0.008,
                 temp_c=25.0,
                 seed=None):
        self._bank = bytearray(reg.REGISTER_BANK_SIZE)
        self._bank[reg.REG_WHO_AM_I] = reg.WHO_AM_I_VALUE

        self.gyro_bias_dps = np.asarray(gyro_bias_dps, dtype=float)
        self.accel_bias_g = np.asarray(accel_bias_g, dtype=float)
        self.gyro_noise_rms_dps = float(gyro_noise_rms_dps)
        self.accel_noise_rms_g = float(accel_noise_rms_g)
        self.default_temp_c = float(temp_c)
        self._rng = np.random.default_rng(seed)

        self.last_reading = None
        self.configure_gyro_range(gyro_range)
        self.configure_accel_range(accel_range)

    # ------------------------------------------------------------------
    # Configuration (writes the same config registers a driver would)
    # ------------------------------------------------------------------
    def configure_gyro_range(self, gyro_range):
        self.gyro_range = reg.GyroRange(gyro_range)
        self._gyro_lsb_per_dps = reg.GYRO_SENSITIVITY_LSB_PER_DPS[self.gyro_range]
        self._gyro_fs_dps = reg.GYRO_FULL_SCALE_DPS[self.gyro_range]
        self._bank[reg.REG_GYRO_CONFIG] = int(self.gyro_range) << 3

    def configure_accel_range(self, accel_range):
        self.accel_range = reg.AccelRange(accel_range)
        self._accel_lsb_per_g = reg.ACCEL_SENSITIVITY_LSB_PER_G[self.accel_range]
        self._accel_fs_g = reg.ACCEL_FULL_SCALE_G[self.accel_range]
        self._bank[reg.REG_ACCEL_CONFIG] = int(self.accel_range) << 3

    # ------------------------------------------------------------------
    # Core measurement
    # ------------------------------------------------------------------
    def sample(self, omega_rad_s, specific_force_m_s2,
               temp_c=None, sim_time_s=0.0):
        """
        Take one measurement from truth and update the register bank.

        omega_rad_s         : true angular velocity in the sensor frame [rad/s]
        specific_force_m_s2 : true specific force at the sensor [m/s^2]
                              (see kinematics.specific_force_at_offset for the
                              off-CoM case)
        temp_c              : die temperature [deg C]; default falls back to the
                              configured ambient
        sim_time_s          : timestamp carried through onto the Reading

        Returns a Reading and stores it as ``self.last_reading``.
        """
        temp_c = self.default_temp_c if temp_c is None else float(temp_c)

        gyro_dps_true = np.degrees(np.asarray(omega_rad_s, dtype=float))
        accel_g_true = np.asarray(specific_force_m_s2, dtype=float) / \
            reg.STANDARD_GRAVITY_M_S2

        # Sensor chain: truth -> + bias -> + noise -> quantise -> saturate.
        gyro_dps = gyro_dps_true + self.gyro_bias_dps
        accel_g = accel_g_true + self.accel_bias_g
        if self.gyro_noise_rms_dps > 0.0:
            gyro_dps = gyro_dps + self._rng.normal(0.0, self.gyro_noise_rms_dps, 3)
        if self.accel_noise_rms_g > 0.0:
            accel_g = accel_g + self._rng.normal(0.0, self.accel_noise_rms_g, 3)

        gyro_raw, gyro_sat = self._quantise(gyro_dps, self._gyro_lsb_per_dps)
        accel_raw, accel_sat = self._quantise(accel_g, self._accel_lsb_per_g)
        temp_raw = self._quantise_scalar(
            (temp_c - reg.TEMP_OFFSET_DEGC) * reg.TEMP_SENSITIVITY_LSB_PER_DEGC)

        self._write_block(reg.REG_ACCEL_XOUT_H, accel_raw)
        self._write_i16(reg.REG_TEMP_OUT_H, temp_raw)
        self._write_block(reg.REG_GYRO_XOUT_H, gyro_raw)

        # Decode straight back from counts so the engineering values reflect
        # exactly what a driver reading the registers would compute.
        reading = Reading(
            sim_time_s=sim_time_s,
            accel_raw=accel_raw,
            gyro_raw=gyro_raw,
            temp_raw=temp_raw,
            accel_g=accel_raw / self._accel_lsb_per_g,
            accel_m_s2=(accel_raw / self._accel_lsb_per_g) * reg.STANDARD_GRAVITY_M_S2,
            gyro_dps=gyro_raw / self._gyro_lsb_per_dps,
            gyro_rad_s=np.radians(gyro_raw / self._gyro_lsb_per_dps),
            temp_c=temp_raw / reg.TEMP_SENSITIVITY_LSB_PER_DEGC + reg.TEMP_OFFSET_DEGC,
            saturated=bool(gyro_sat or accel_sat),
        )
        self.last_reading = reading
        return reading

    def sample_from_motion(self, omega_rad_s, omega_dot_rad_s2, r_offset_m,
                           specific_force_cm_m_s2=None, temp_c=None,
                           sim_time_s=0.0):
        """
        Convenience wrapper: derive the specific force at a sensor mounted
        ``r_offset_m`` from the centre of mass (centripetal + Euler terms), then
        sample. Lets a caller pass raw rigid-body motion instead of already
        having resolved the specific force at the sensor.
        """
        from .kinematics import specific_force_at_offset
        f = specific_force_at_offset(omega_rad_s, omega_dot_rad_s2, r_offset_m,
                                     specific_force_cm_m_s2)
        return self.sample(omega_rad_s, f, temp_c=temp_c, sim_time_s=sim_time_s)

    # ------------------------------------------------------------------
    # I2C-style read access (what the bus / a driver would see)
    # ------------------------------------------------------------------
    def who_am_i(self):
        return self._bank[reg.REG_WHO_AM_I]

    def read_register(self, address):
        return self._bank[address]

    def read_block(self, address, length):
        """Burst read, mimicking an I2C multi-byte read starting at address."""
        return bytes(self._bank[address:address + length])

    def read_measurement_block(self):
        """The 14 raw bytes accel(6)+temp(2)+gyro(6), as a real burst read."""
        return self.read_block(reg.MEASUREMENT_BLOCK_START,
                               reg.MEASUREMENT_BLOCK_LEN)

    # ------------------------------------------------------------------
    # Internals: quantisation + register packing
    # ------------------------------------------------------------------
    def _quantise(self, values, lsb_per_unit):
        """Vectorised float -> saturated int16 counts. Returns (counts, sat)."""
        counts = np.rint(np.asarray(values) * lsb_per_unit).astype(np.int64)
        clipped = np.clip(counts, reg.INT16_MIN, reg.INT16_MAX)
        saturated = bool(np.any(clipped != counts))
        return clipped.astype(np.int64), saturated

    def _quantise_scalar(self, value):
        count = int(round(value))
        return max(reg.INT16_MIN, min(reg.INT16_MAX, count))

    def _write_i16(self, address, value):
        """Store one signed 16-bit value big-endian (high byte first)."""
        packed = int(value) & 0xFFFF
        self._bank[address] = (packed >> 8) & 0xFF
        self._bank[address + 1] = packed & 0xFF

    def _write_block(self, address, counts3):
        for i, value in enumerate(counts3):
            self._write_i16(address + 2 * i, int(value))
