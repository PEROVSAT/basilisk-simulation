"""
experiments/power_states/run.py
Power-only experiment (3 days).
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "PythonModules"))

from sim.core import ExperimentBase
from sim.plotting import plot_power_history
from devices.bus_components import NSLBus, OBC, IridiumModem, SunSensor, IMU
from devices.amu import SimulatedAMU
from devices.solar_cell import SolarCell


class PowerStatesExperiment(ExperimentBase):
    EXPERIMENT_NAME = "power_states"
    SIM_DURATION_S = 3 * 86400.0
    TIMESTEP_S = 1.0
    RECORD_PERIOD_S = 10.0
    INCLUDE_PERMANENT_MAGNET = False
    INCLUDE_HYSTERESIS_RODS = False
    INCLUDE_VIZARD = False

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
        self.power_manager.print_summary()
        plot_power_history(self.power_manager, output_dir)


if __name__ == "__main__":
    PowerStatesExperiment().run()