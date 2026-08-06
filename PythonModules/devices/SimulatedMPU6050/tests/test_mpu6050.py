"""
test_mpu6050.py
Unit tests for the register-level MPU-6050 model. Pure-Python, no Basilisk.

Runs two ways:
  * pytest tests/                (functions are named test_*)
  * python tests/test_mpu6050.py (a tiny runner at the bottom, no pytest dep)
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulated_mpu6050 import (SimulatedMPU6050, GyroRange, AccelRange,
                               specific_force_at_offset)
from simulated_mpu6050 import registers as reg


def _noiseless(**kw):
    """A deterministic sensor: no noise, no bias."""
    return SimulatedMPU6050(gyro_noise_rms_dps=0.0, accel_noise_rms_g=0.0,
                            **kw)


def test_who_am_i():
    imu = _noiseless()
    assert imu.who_am_i() == reg.WHO_AM_I_VALUE == 0x68


def test_gyro_sensitivity_roundtrip():
    # 100 deg/s about z at the 250 dps range -> 100 * 131 = 13100 counts.
    imu = _noiseless(gyro_range=GyroRange.DPS_250)
    r = imu.sample(omega_rad_s=np.radians([0.0, 0.0, 100.0]),
                   specific_force_m_s2=[0.0, 0.0, 0.0])
    assert r.gyro_raw[2] == 13100
    assert np.isclose(r.gyro_dps[2], 100.0, atol=1.0 / 131.0)


def test_accel_sensitivity_roundtrip():
    # 1 g about x at +/-2g range -> 16384 counts.
    imu = _noiseless(accel_range=AccelRange.G_2)
    r = imu.sample(omega_rad_s=[0.0, 0.0, 0.0],
                   specific_force_m_s2=[reg.STANDARD_GRAVITY_M_S2, 0.0, 0.0])
    assert r.accel_raw[0] == 16384
    assert np.isclose(r.accel_g[0], 1.0, atol=1.0 / 16384.0)


def test_range_switch_changes_sensitivity():
    imu = _noiseless(gyro_range=GyroRange.DPS_250)
    r250 = imu.sample(np.radians([0.0, 0.0, 100.0]), [0, 0, 0])
    imu.configure_gyro_range(GyroRange.DPS_2000)
    r2000 = imu.sample(np.radians([0.0, 0.0, 100.0]), [0, 0, 0])
    # Same physical rate, coarser range -> far fewer counts (131 vs 16.4 LSB/dps).
    assert r250.gyro_raw[2] == 13100
    assert r2000.gyro_raw[2] == round(100 * 16.4)
    # Config register reflects AFS/FS select bits.
    assert imu.read_register(reg.REG_GYRO_CONFIG) == (int(GyroRange.DPS_2000) << 3)


def test_gyro_saturation():
    # 5000 deg/s at +/-2000 range must clip to int16 max, flag saturation.
    imu = _noiseless(gyro_range=GyroRange.DPS_2000)
    r = imu.sample(np.radians([0.0, 0.0, 5000.0]), [0, 0, 0])
    assert r.gyro_raw[2] == reg.INT16_MAX == 32767
    assert r.saturated is True


def test_temperature_roundtrip():
    imu = _noiseless(temp_c=36.53)      # -> exactly 0 counts by the transfer fn
    r = imu.sample([0, 0, 0], [0, 0, 0])
    assert r.temp_raw == 0
    r2 = imu.sample([0, 0, 0], [0, 0, 0], temp_c=25.0)
    assert np.isclose(r2.temp_c, 25.0, atol=1.0 / 340.0)


def test_bias_offsets_output():
    imu = SimulatedMPU6050(gyro_noise_rms_dps=0.0, accel_noise_rms_g=0.0,
                           gyro_bias_dps=[2.0, 0.0, 0.0])
    r = imu.sample([0.0, 0.0, 0.0], [0.0, 0.0, 0.0])
    # Zero true rate + 2 deg/s bias at 131 LSB/dps -> 262 counts.
    assert r.gyro_raw[0] == round(2.0 * 131.0)


def test_measurement_block_matches_registers():
    imu = _noiseless()
    imu.sample(np.radians([10.0, -20.0, 30.0]),
               [0.0, reg.STANDARD_GRAVITY_M_S2, 0.0])
    block = imu.read_measurement_block()
    assert len(block) == reg.MEASUREMENT_BLOCK_LEN == 14
    # First two bytes are accel X, big-endian signed -> decode and compare.
    ax = int(np.int16((block[0] << 8) | block[1]))
    assert ax == imu.last_reading.accel_raw[0]


def test_centripetal_specific_force():
    # Pure spin omega about +z, sensor offset r along +x:
    # centripetal accel = omega x (omega x r) = -omega^2 * r (points to axis).
    omega = np.array([0.0, 0.0, 4.0])          # rad/s
    r_off = np.array([0.05, 0.0, 0.0])         # 5 cm along x
    f = specific_force_at_offset(omega, [0, 0, 0], r_off)
    assert np.isclose(f[0], -(4.0 ** 2) * 0.05)
    assert np.allclose(f[1:], 0.0)


def test_noise_has_expected_scale():
    # With a known noise RMS and zero truth, the sample std should be close.
    imu = SimulatedMPU6050(gyro_noise_rms_dps=1.0, accel_noise_rms_g=0.0,
                           seed=1234)
    samples = np.array([imu.sample([0, 0, 0], [0, 0, 0]).gyro_dps[0]
                        for _ in range(4000)])
    assert abs(np.std(samples) - 1.0) < 0.1
    assert abs(np.mean(samples)) < 0.1


def _run_all():
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return failed


if __name__ == "__main__":
    sys.exit(1 if _run_all() else 0)
