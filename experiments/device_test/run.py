"""
experiments/device_test/run.py
Device integration test with all standalone packages.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "PythonModules"))

# Add standalone device packages to path
_DEV_ROOT = os.path.join(_ROOT, "PythonModules", "devices")
for sub in ("SimulatedAMU", "SimulatedMPU6050", "SimulatedNSLEPS", "SimulatedEyestar"):
    p = os.path.join(_DEV_ROOT, sub)
    if os.path.exists(p):
        sys.path.insert(0, p)

from sim.core import ExperimentBase
from sim.plotting import plot_power_history
from devices.bus_components import NSLBus, OBC, IridiumModem, SunSensor, IMU
from devices.amu import SimulatedAMU
from devices.solar_cell import SolarCell

from simulated_mpu6050 import SimulatedMPU6050, GyroRange, AccelRange
from simulated_nsl_eps import SimulatedNSLEPS
from simulated_eyestar import SimulatedEyestar


class DeviceTestExperiment(ExperimentBase):
    EXPERIMENT_NAME = "device_test"
    SIM_DURATION_S = 600.0
    TIMESTEP_S = 0.5
    RECORD_PERIOD_S = 1.0
    INCLUDE_PERMANENT_MAGNET = False
    INCLUDE_HYSTERESIS_RODS = False
    INCLUDE_VIZARD = False

    def devices(self):
        devs = [NSLBus(), OBC(), IridiumModem(), IMU()]
        devs += [SunSensor(face) for face in ('+Z', '-X')]
        devs += [SimulatedAMU(i) for i in range(1, 5)]

        mpu = SimulatedMPU6050(gyro_range=GyroRange.DPS_500,
                                accel_range=AccelRange.G_2, seed=42)
        # Add get_power for power manager compatibility
        mpu.get_power = lambda: 0.01 if getattr(mpu, 'enabled', True) else 0.0
        mpu.name = "MPU6050"
        devs.append(mpu)

        eps = SimulatedNSLEPS(capacity_wh=100.0, initial_soc=0.8)
        eps.get_power = lambda: 0.0
        eps.name = "NSL_EPS"
        devs.append(eps)

        eyestar = SimulatedEyestar(enabled=True)
        eyestar.get_power = lambda: 0.1 if eyestar.enabled else 0.0
        eyestar.name = "Eyestar"
        devs.append(eyestar)

        return devs

    def solar_cells(self):
        orientations = [(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)]
        return [SolarCell(f"Panel_{i}", area_m2=0.008, efficiency=0.23, orientation=o)
                for i, o in enumerate(orientations)]

    def postprocess(self, output_dir):
        self.power_manager.print_summary()
        plot_power_history(self.power_manager, output_dir)


if __name__ == "__main__":
    DeviceTestExperiment().run()