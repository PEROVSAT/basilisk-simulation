"""
detumble_full.py
The full PEROVSAT detumble run: 8-rod HyMu80 PMAC layout, permanent magnet,
power system and I-V payload, with every diagnostic plot.

This reproduces what base.py used to do directly, now as a BaseExperiment
subclass -- it is the reference example of the experiment pattern.
"""

import os
import sys

# Make sims/ importable so `import base` / `import plots` resolve when this
# file is run directly (python sims/experiments/detumble_full.py).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from base import BaseExperiment
import plots


class DetumbleFull(BaseExperiment):
    def configure(self):
        # Defaults already describe the full run (all subsystems on). Switch
        # to the long detumble study by uncommenting the line below.
        # self.config.sim_duration_s = 3600.0 * 24 * 18   # 18-day run
        pass

    def analyze(self, r):
        plots.print_rod_torque_verification(r.torque_recorders)

        r.power_system.print_summary()
        r.power_system.plot_history("power_system.png")

        r.payload.print_sample_sweep()
        r.payload.print_summary()
        r.payload.plot("iv_curves.png")

        plots.plot_hysteresis_loops(r.hystRecorders)
        plots.plot_detumble_curve(r.scStateRec)
        plots.plot_rod_torques(r.torque_recorders)
        plots.plot_magnetic_field(r.magRec)
        plots.plot_permanent_magnet_torque(r.pmTorqueRec)


if __name__ == "__main__":
    DetumbleFull().main()
