"""PMAC detumble analysis of the standard PEROVSAT sim (1 hour)."""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "PythonModules"))

from sim.simulation import PerovSatSimulation, RunConfig
from sim.plotting import (
    plot_detumble_curve,
    plot_magnetic_field,
    plot_hysteresis_loops,
    plot_rod_torques,
    plot_power_history,
)


def main():
    sim = PerovSatSimulation(RunConfig(
        name="detumble",
        duration_s=3600.0,
        timestep_s=0.5,
        record_period_s=1.0,
    ))
    log = sim.run()
    out = sim.output_dir
    plot_detumble_curve(log, out)
    plot_magnetic_field(log, out)
    plot_hysteresis_loops(log, out)
    plot_rod_torques(log, out)
    plot_power_history(log, out)


if __name__ == "__main__":
    main()
