"""
experiments/detumble/run.py
PMAC detumble with hysteresis rods and full device suite.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "PythonModules"))

from sim.core import ExperimentBase
from sim.plotting import (
    plot_detumble_curve, plot_power_history,
    plot_hysteresis_loops, plot_rod_torques, plot_magnetic_field,
)
from devices.bus_components import NSLBus, OBC, IridiumModem, SunSensor, IMU
from devices.amu import SimulatedAMU
from devices.solar_cell import SolarCell


class DetumbleExperiment(ExperimentBase):
    EXPERIMENT_NAME = "detumble"
    SIM_DURATION_S = 3600.0          # 1 hour test; 18*86400 for full run
    TIMESTEP_S = 0.5
    RECORD_PERIOD_S = 1.0

    def devices(self):
        devs = [NSLBus(), OBC(), IridiumModem(), IMU()]
        devs += [SunSensor(face) for face in ('+Z', '-X')]
        devs += [SimulatedAMU(i) for i in range(1, 17)]
        return devs

    def solar_cells(self):
        orientations = [(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)]
        return [SolarCell(f"Panel_{i}", area_m2=0.008, efficiency=0.23, orientation=o)
                for i, o in enumerate(orientations)]

    def postprocess(self, output_dir):
        plot_detumble_curve(self.recorders["scState"], output_dir)
        plot_magnetic_field(self.recorders["mag"], output_dir)
        if self.rods:
            plot_hysteresis_loops(self.recorders["hysteresis"], output_dir)
            plot_rod_torques(self.recorders["rodTorques"], output_dir)
        if self.power_manager:
            self.power_manager.print_summary()
            plot_power_history(self.power_manager, output_dir)


if __name__ == "__main__":
    DetumbleExperiment().run()