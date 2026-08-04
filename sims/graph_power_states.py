"""
graph_power_states.py
Example experiment: exercises just the power management system (no PMAC
attitude control needed for this) and graphs battery SOC / generation /
consumption over the run. This is the intended shape of a new experiment:
inherit ExperimentBase, set a few parameters, define devices()/solar_cells(),
and add the custom graphing in postprocess() -- nothing here touches base.py.
"""

import numpy as np
import matplotlib.pyplot as plt

from base import ExperimentBase

# NOTE: importing base already inserts PythonModules/ onto sys.path (using an
# absolute path derived from base.py's own location), so devices/ is already
# importable here regardless of the current working directory.
from devices.bus_components import NSLBus, OBC, IridiumModem, SunSensor, IMU
from devices.amu import SimulatedAMU
from devices.solar_cell import SolarCell


class GraphPowerStatesExperiment(ExperimentBase):
    SIM_DURATION_S = 3 * 86400.0     # 3 days, long enough to see several eclipses
    TIMESTEP_S = 1.0
    RECORD_PERIOD_S = 10.0

    # This experiment doesn't need attitude control at all.
    INCLUDE_PERMANENT_MAGNET = False
    INCLUDE_HYSTERESIS_RODS = False
    INCLUDE_VIZARD = False

    BATTERY_CAPACITY_WH = 100.0
    BATTERY_INITIAL_SOC = 0.8
    POWER_UPDATE_PERIOD_S = 1.0

    def devices(self):
        devs = [NSLBus(), OBC(), IridiumModem(), IMU()]
        devs += [SunSensor(face) for face in ('+Z', '-X')]
        devs += [SimulatedAMU(i) for i in range(1, 17)]
        return devs

    def solar_cells(self):
        orientations = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
        return [SolarCell(f"Panel_{i}", area_m2=0.008, efficiency=0.23, orientation=o)
                for i, o in enumerate(orientations)]

    def postprocess(self):
        self.power_manager.print_summary()
        self._plot_power_states()

    def _plot_power_states(self):
        history = self.power_manager.history
        if not history:
            print("No power history recorded.")
            return

        t_h = np.array([h['time_s'] for h in history]) / 3600.0
        gen = np.array([h['generation_w'] for h in history])
        con = np.array([h['consumption_w'] for h in history])
        net = np.array([h['net_power_w'] for h in history])
        soc = np.array([h['soc'] for h in history]) * 100.0
        eclipsed = np.array([h['eclipsed'] for h in history])

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)

        ax1.fill_between(t_h, 0, 1, where=eclipsed, transform=ax1.get_xaxis_transform(),
                         color='gray', alpha=0.15, step='post', label='Eclipse')
        ax1.plot(t_h, gen, label='Generation', color='green', linewidth=1.2)
        ax1.plot(t_h, con, label='Consumption', color='red', linewidth=1.2)
        ax1.plot(t_h, net, label='Net', color='blue', linestyle='--', linewidth=1.0)
        ax1.axhline(0, color='black', linewidth=0.5)
        ax1.set_ylabel('Power (W)')
        ax1.set_title('Power Generation vs Consumption (shaded = eclipse)')
        ax1.legend(loc='upper right')
        ax1.grid(True, alpha=0.3)

        ax2.plot(t_h, soc, color='blue', linewidth=1.5)
        ax2.set_xlabel('Time (hours)')
        ax2.set_ylabel('State of Charge (%)')
        ax2.set_title('Battery SOC')
        ax2.grid(True, alpha=0.3)
        ax2.set_ylim(0, 105)

        plt.tight_layout()
        plt.savefig('power_states.png', dpi=150)
        plt.close(fig)
        print("Saved power_states.png")


if __name__ == "__main__":
    GraphPowerStatesExperiment().run()
