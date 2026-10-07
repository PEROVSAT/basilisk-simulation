from pathlib import Path

from perovsat.simulation import PerovSatSimulation, RunConfig
from experiments.plotting import (
    plot_detumble_curve,
    plot_magnetic_field,
    plot_hysteresis_loops,
    plot_rod_torques,
)

_HERE = Path(__file__).resolve().parent


def main():
    sim = PerovSatSimulation(RunConfig(
        name="detumble",
        duration_s=22 * 24 * 3600,
        timestep_s=10,
        record_period_s=20.0,
        output_dir=_HERE / "output",
        vizard=True,
    ))
    log = sim.run()
    out = sim.output_dir
    plot_detumble_curve(log, out)
    plot_magnetic_field(log, out)
    plot_hysteresis_loops(log, out)
    plot_rod_torques(log, out)


if __name__ == "__main__":
    main()
