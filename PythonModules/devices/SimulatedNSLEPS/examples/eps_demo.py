#!/usr/bin/env python3
"""
eps_demo.py
Standalone demo of SimulatedNSLEPS -- no Basilisk required.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import matplotlib.pyplot as plt
from simulated_nsl_eps import SimulatedNSLEPS


def main():
    eps = SimulatedNSLEPS(capacity_wh=100.0, initial_soc=0.8)

    print("\n" + "=" * 70)
    print("NSL EPS DEMO")
    print("=" * 70)

    dt = 60.0  # 1 minute steps
    total = 600.0  # 10 minutes
    times = []
    socs = []
    powers = []
    statuses = []

    print(f"{'t(s)':>6} {'SOC(%)':>7} {'Energy(Wh)':>11} {'Status':>10} {'Power(W)':>10} {'Charging':>8}")
    print("-" * 70)

    for t in np.arange(0, total, dt):
        # Simulate: charging at 5W for 0-3 min, idle 3-5 min, discharging -10W 5-8 min, idle 8-10 min
        if t < 180:
            power = 5.0  # charging
        elif t < 300:
            power = 0.0  # idle
        elif t < 480:
            power = -10.0  # discharging
        else:
            power = 0.0  # idle

        reading = eps.step(power, sim_time_s=t)

        times.append(t / 60.0)  # minutes
        socs.append(reading.soc * 100)
        powers.append(power)
        statuses.append(reading.status)

        print(f"{t:6.0f} {reading.soc*100:7.1f} {reading.energy_wh:11.2f} {reading.status:10s} {power:10.1f} {'Yes' if reading.charging else 'No':>8}")

    eps.print_summary()

    # Plot results
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))

    ax1.plot(times, socs, 'b-', linewidth=1.5)
    ax1.axhline(y=20, color='r', linestyle='--', label='SAFE threshold (20%)')
    ax1.axhline(y=40, color='orange', linestyle='--', label='LOW threshold (40%)')
    ax1.set_xlabel('Time (minutes)')
    ax1.set_ylabel('State of Charge (%)')
    ax1.set_title('Battery SOC')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    ax1.set_ylim(0, 105)

    ax2.plot(times, powers, 'g-', linewidth=1.5)
    ax2.axhline(y=0, color='k', linestyle='-', linewidth=0.5)
    ax2.set_xlabel('Time (minutes)')
    ax2.set_ylabel('Net Power (W)')
    ax2.set_title('Net Power Into Battery')
    ax2.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig('eps_demo.png', dpi=150)
    print("\nSaved eps_demo.png")
    plt.show()


if __name__ == "__main__":
    main()