"""
graph_power_states.py
Example experiment: run the power system over one orbit and graph the power
states (generation/consumption, battery SOC, operational status) plus the
I-V payload output. Rods are disabled since they don't affect the power
budget -- this keeps the run fast.

Shows the whole pattern: set parameters in configure(), interpret data in
analyze(). No copy of base.py, ~a dozen lines.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from base import BaseExperiment


class GraphPowerStates(BaseExperiment):
    def configure(self):
        self.config.sim_duration_s = 7200.0      # one ~orbit-length window
        self.config.timestep_s = 0.5
        self.config.enable_rods = False          # power study -> skip rod dynamics
        self.config.enable_perm_magnet = False
        self.config.battery_initial_soc = 0.8

    def analyze(self, r):
        r.power_system.print_summary()
        r.power_system.plot_history("power_states.png")

        # The I-V payload rides on the same Sun geometry.
        r.payload.print_sample_sweep()
        r.payload.print_summary()
        r.payload.plot("power_states_iv.png")


if __name__ == "__main__":
    GraphPowerStates().main()
