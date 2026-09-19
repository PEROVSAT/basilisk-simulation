"""Multi-day power budget of the standard PEROVSAT sim (3 days)."""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "PythonModules"))

from sim.simulation import PerovSatSimulation, RunConfig
from sim.plotting import plot_power_history, plot_power_by_sink, plot_detumble_curve


def main():
    sim = PerovSatSimulation(RunConfig(
        name="power",
        duration_s=3 * 86400.0,   # 3 days
        timestep_s=1.0,
        record_period_s=10.0,
    ))
    log = sim.run()
    out = sim.output_dir
    plot_power_history(log, out)
    plot_power_by_sink(log, out)
    plot_detumble_curve(log, out)
    p = log.power
    if p.soc is not None and len(p.soc):
        print(f"SOC {p.soc[0]*100:.1f}% -> {p.soc[-1]*100:.1f}%")
    con = p.consumption_w
    gen = p.generation_w
    if gen is not None and len(gen) and con is not None:
        print(f"Mean generation {gen.mean():.3f} W, mean load {con.mean():.3f} W")


if __name__ == "__main__":
    main()
