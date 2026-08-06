"""
tumble_demo.py
Standalone demo of SimulatedMPU6050 executing its core measurement -- no
Basilisk required. It fakes a CubeSat tumble that decays over time (as a
detumbler would produce) and prints what the IMU reports each step: the gyro
tracks the body rate, and because the sensor is mounted a few cm off the centre
of mass, the accelerometer picks up the centripetal signature of the spin even
though the spacecraft is in free fall (specific force at the CoM ~ 0).

Run:  python examples/tumble_demo.py
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from simulated_mpu6050 import SimulatedMPU6050, GyroRange, AccelRange


def main():
    imu = SimulatedMPU6050(
        gyro_range=GyroRange.DPS_500,     # headroom over an initial ~5-10 deg/s tumble
        accel_range=AccelRange.G_2,
        gyro_bias_dps=[0.3, -0.2, 0.15],  # a small, realistic zero-rate offset
        seed=42,
    )

    mount_offset_m = np.array([0.04, 0.02, 0.03])   # sensor ~5 cm off CoM in a 1U
    dt = 1.0
    total_s = 30.0

    # A tumble about a tilted axis, magnitude decaying like a damped detumble.
    axis = np.array([0.3, -0.6, 1.0])
    axis = axis / np.linalg.norm(axis)
    omega0_dps = 8.0
    tau = 20.0        # decay time constant [s]

    print("t[s]   |omega|      gyro (deg/s)               accel (mg)            temp")
    print("-" * 84)

    prev_omega = None
    for k in range(int(total_s / dt) + 1):
        t = k * dt
        rate_dps = omega0_dps * np.exp(-t / tau)
        omega = np.radians(rate_dps) * axis                       # rad/s

        # Finite-difference the truth to get angular acceleration for the
        # Euler term (a real sim would hand this over directly).
        omega_dot = np.zeros(3) if prev_omega is None else (omega - prev_omega) / dt
        prev_omega = omega

        r = imu.sample_from_motion(
            omega_rad_s=omega,
            omega_dot_rad_s2=omega_dot,
            r_offset_m=mount_offset_m,
            temp_c=22.0,
            sim_time_s=t,
        )

        g = r.gyro_dps
        a_mg = r.accel_g * 1000.0
        print(f"{t:4.0f}   {np.degrees(np.linalg.norm(omega)):6.3f}   "
              f"[{g[0]:+7.3f} {g[1]:+7.3f} {g[2]:+7.3f}]   "
              f"[{a_mg[0]:+6.2f} {a_mg[1]:+6.2f} {a_mg[2]:+6.2f}]   {r.temp_c:5.2f}C")

    print("\nWHO_AM_I = 0x%02X   raw measurement block = %s"
          % (imu.who_am_i(), imu.read_measurement_block().hex(" ")))


if __name__ == "__main__":
    main()
