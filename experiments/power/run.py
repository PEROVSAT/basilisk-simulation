"""Multi-day power budget of the standard PEROVSAT sim (3 days)."""

from pathlib import Path

from perovsat.simulation import PerovSatSimulation, RunConfig
from experiments.plotting import plot_power_history, plot_power_by_sink, plot_detumble_curve

_HERE = Path(__file__).resolve().parent


def main():
    sim = PerovSatSimulation(RunConfig(
        name="power",
        duration_s=3 * 86400.0,
        timestep_s=1.0,
        record_period_s=10.0,
        output_dir=_HERE / "output",
    ))
    log = sim.run()
    out = sim.output_dir
    plot_power_history(log, out)
    plot_power_by_sink(log, out)
    plot_detumble_curve(log, out)
    p = log.power
    if p.soc is not None and len(p.soc):
        print(f"SOC {p.soc[0]*100:.1f}% -> {p.soc[-1]*100:.1f}%")
    gen, con = p.generation_w, p.consumption_w
    if gen is not None and len(gen) and con is not None:
        print(f"Mean generation {gen.mean():.3f} W, mean load {con.mean():.3f} W")


if __name__ == "__main__":
    main()
