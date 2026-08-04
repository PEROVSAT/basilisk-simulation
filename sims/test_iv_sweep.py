"""
test_iv_sweep.py
Standalone device test -- no Basilisk sim needed. Fakes an onMessage() call
to a SimulatedAMU with a hand-built "simulation state" and plots the
resulting I-V curve. This is the fast-iteration workflow the devices/
design is meant to enable: exercise a single device in isolation before
wiring it into a full experiment.
"""

import os
import sys
from types import SimpleNamespace

import numpy as np
import matplotlib.pyplot as plt

# This file doesn't import base.py (that's the point -- no Basilisk sim
# needed), so it has to set up its own path to PythonModules/, using an
# absolute path derived from this file's location rather than a relative
# string (which only works if the CWD happens to be sims/).
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, "PythonModules"))

from devices.amu import SimulatedAMU
from payload_iv import PVDevice


def fake_simulation_state(sun_direction_body, shadow_factor=1.0, sun_distance_factor=1.0, sim_time_s=0.0):
    """A minimal stand-in for sim_state.SimulationState -- onMessage() only
    reads these four attributes, so a real Basilisk sim isn't needed to
    test a device's command handling."""
    return SimpleNamespace(
        sun_direction_body=np.array(sun_direction_body, dtype=float),
        shadow_factor=shadow_factor,
        sun_distance_factor=sun_distance_factor,
        sim_time_s=sim_time_s,
    )


def run():
    pv = PVDevice('perovskite_pixel_A', '+Z', (0, 0, 1), area_m2=1.0e-4)
    amu = SimulatedAMU(amu_id=1, pv_device=pv)

    sim = fake_simulation_state(sun_direction_body=(0, 0, 1), shadow_factor=1.0,
                                sun_distance_factor=1.0, sim_time_s=0.0)

    result = amu.onMessage({'command': 'IV_SWEEP', 'temp_c': 25.0}, sim)

    V, I = result['V'], result['I']
    s = result['summary']
    print(f"Voc={s['voc']:.4f} V  Isc={s['isc']*1e3:.4f} mA  "
          f"Pmax={s['pmax']*1e3:.4f} mW  FF={s['ff']:.3f}")

    fig, ax = plt.subplots(figsize=(7, 5))
    ax.plot(V, I * 1e3, '-o', ms=3)
    ax.set_xlabel('Voltage (V)')
    ax.set_ylabel('Current (mA)')
    ax.set_title(f"{amu.name} I-V sweep of {pv.name}")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig('test_iv_sweep.png', dpi=150)
    print("Saved test_iv_sweep.png")


if __name__ == "__main__":
    run()
