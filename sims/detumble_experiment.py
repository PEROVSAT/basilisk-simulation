"""
detumble_experiment.py
The PMAC detumble experiment (formerly the hard-coded run() in base.py).
Everything generic (spacecraft/orbit/WMM/permanent magnet/hysteresis
rods/power management wiring) comes from ExperimentBase; this file only
supplies: the run duration, which devices/solar cells exist on the bus, and
the PMAC-specific plots in postprocess().
"""

from base import ExperimentBase
from plotting_utils import (
    plot_hysteresis_loops, plot_detumble_curve, plot_rod_torques,
    plot_magnetic_field, plot_permanent_magnet_torque,
)

# NOTE: importing base already inserts PythonModules/ onto sys.path (using an
# absolute path derived from base.py's own location), so devices/ is already
# importable here regardless of the current working directory.
from devices.bus_components import NSLBus, OBC, IridiumModem, SunSensor, IMU
from devices.amu import SimulatedAMU
from devices.solar_cell import SolarCell


class DetumbleExperiment(ExperimentBase):
    # ---- Choose duration here ----
    # For a 1-hour smoke test:
    SIM_DURATION_S = 3600.0
    TIMESTEP_S = 0.5
    RECORD_PERIOD_S = 1.0

    # For the full 18-day detumble run, use instead:
    # SIM_DURATION_S = 18 * 86400.0
    # TIMESTEP_S = 0.5
    # RECORD_PERIOD_S = 60.0

    def devices(self):
        devs = [NSLBus(), OBC(), IridiumModem(), IMU()]
        devs += [SunSensor(face) for face in ('+Z', '-X')]
        devs += [SimulatedAMU(i) for i in range(1, 17)]   # no PV device wired yet
        return devs

    def solar_cells(self):
        orientations = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
        return [SolarCell(f"Panel_{i}", area_m2=0.008, efficiency=0.23, orientation=o)
                for i, o in enumerate(orientations)]

    def postprocess(self):
        print("\n" + "=" * 60)
        print("ROD TORQUE VERIFICATION")
        print("=" * 60)
        for tag, rec in self.recorders["rodTorques"].items():
            torque = rec.torqueRequestBody
            print(f"{tag}: recorded {len(torque)} samples")
        print("=" * 60 + "\n")

        self.power_manager.print_summary()

        plot_hysteresis_loops(self.recorders["hysteresis"])
        plot_detumble_curve(self.recorders["scState"])
        plot_rod_torques(self.recorders["rodTorques"])
        plot_magnetic_field(self.recorders["mag"])
        plot_permanent_magnet_torque(self.recorders["pmTorque"])


if __name__ == "__main__":
    DetumbleExperiment().run()
