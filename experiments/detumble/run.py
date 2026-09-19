"""PMAC detumble analysis of the standard PEROVSAT sim (1 hour)."""

from pathlib import Path

from perovsat.simulation import PerovSatSimulation, RunConfig
from experiments.plotting import (
    plot_detumble_curve,
    plot_magnetic_field,
    plot_hysteresis_loops,
    plot_rod_torques,
    plot_power_history,
)

_HERE = Path(__file__).resolve().parent


def main():
    sim = PerovSatSimulation(RunConfig(
        name="detumble",
        duration_s=3600.0,
        timestep_s=0.5,
        record_period_s=1.0,
        output_dir=_HERE / "output",
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
