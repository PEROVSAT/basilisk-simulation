#!/usr/bin/env python3
"""
iv_sweep_demo.py
Standalone demo of SimulatedAMU -- no Basilisk required.
"""

import sys
import os

# Add parent directory to path so we can import simulated_amu
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib.pyplot as plt

# Now import from simulated_amu
from simulated_amu import SimulatedAMU


def main():
    amu = SimulatedAMU()

    # Sun along +Z, device normal along +Z (normal incidence, 1 sun)
    sun_dir = np.array([0.0, 0.0, 1.0])
    normal = np.array([0.0, 0.0, 1.0])

    reading = amu.sample(sun_dir, normal, temp_c=25.0, sim_time_s=0.0)

    print(f"Sun angle: {reading.sun_angle_deg:.1f}°")
    print(f"Irradiance: {reading.irradiance_w_m2:.0f} W/m²")
    print(f"Voc: {reading.voc:.4f} V")
    print(f"Isc: {reading.isc*1e3:.3f} mA")
    print(f"Pmax: {reading.pmax*1e3:.3f} mW")
    print(f"FF: {reading.ff:.3f}")

    # Plot I-V and P-V
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    ax1.plot(reading.voltage_V, reading.current_A * 1e3, 'b-')
    ax1.plot(reading.vmp, reading.imp * 1e3, 'ro', label='MPP')
    ax1.set_xlabel('Voltage (V)')
    ax1.set_ylabel('Current (mA)')
    ax1.set_title('I-V Curve')
    ax1.grid(True)
    ax1.legend()

    P = reading.voltage_V * reading.current_A * 1e3
    ax2.plot(reading.voltage_V, P, 'r-')
    ax2.plot(reading.vmp, reading.pmax * 1e3, 'ro', label=f'Pmax={reading.pmax*1e3:.2f}mW')
    ax2.set_xlabel('Voltage (V)')
    ax2.set_ylabel('Power (mW)')
    ax2.set_title('P-V Curve')
    ax2.grid(True)
    ax2.legend()

    plt.tight_layout()
    plt.savefig('iv_sweep.png', dpi=150)
    print("\nSaved iv_sweep.png")


if __name__ == "__main__":
    main()