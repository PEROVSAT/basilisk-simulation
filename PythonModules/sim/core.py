"""
sim/core.py
ExperimentBase -- what every experiment subclasses.
"""

import os
import sys
from datetime import datetime

import numpy as np

from Basilisk.architecture import sysModel
from Basilisk.simulation import spacecraft, svIntegrators
from Basilisk.utilities import SimulationBaseClass, macros

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "PythonModules"))

from sim.environment import setup_environment
from sim.power import create_power_manager, SimulationState
from sim.plotting import save_figure
from hardware.hysteresisFactory import HysteresisFactory

try:
    import perovsat_plugins.messaging  # noqa: F401
    from perovsat_plugins.permanentMagnet import PermanentMagnet
except ImportError as exc:
    raise ImportError(f"Compiled plugins not found: {exc}") from exc


class OrientationMonitor(sysModel.SysModel):
    """Console attitude printout."""

    def __init__(self, scStateOutMsg):
        super().__init__()
        self.ModelTag = "OrientationMonitor"
        self.scStateOutMsg = scStateOutMsg

    def UpdateState(self, currentSimNanos):
        state = self.scStateOutMsg.read()
        if state is None:
            return
        t_s = currentSimNanos * macros.NANO2SEC
        sigma = state.sigma_BN
        omega = np.degrees(state.omega_BN_B)
        omega_mag = np.degrees(np.linalg.norm(state.omega_BN_B))
        print(f"t={t_s:8.1f}s  σ=[{sigma[0]:+.3f},{sigma[1]:+.3f},{sigma[2]:+.3f}]"
              f"  ω=[{omega[0]:+.3f},{omega[1]:+.3f},{omega[2]:+.3f}] deg/s"
              f"  |ω|={omega_mag:.4f}")


class ExperimentBase:
    """
    Base class for all PEROVSAT experiments.

    Subclasses override:
      - Class parameters (spacecraft, timing, subsystem toggles)
      - devices() -> list of SimulatedDevice
      - solar_cells() -> list of SolarCell
      - add_recorders(rec_period) -> dict (optional)
      - postprocess(output_dir) (optional)
    """

    # Spacecraft
    MASS_KG = 1.2
    INERTIA_KGM2 = [[0.002, 0.0, 0.0],
                    [0.0, 0.002, 0.0],
                    [0.0, 0.0, 0.001]]
    SIGMA_INIT = [[0.2], [-0.1], [0.3]]
    OMEGA_INIT_RADS = [[0.05], [0.07], [0.02]]
    DIPOLE_BODY_AM2 = np.array([0.0, 0.0, 0.15])

    # Environment
    EPOCH_UTC = "2026 JUN 21 12:00:00.0 (UTC)"

    # Timing
    SIM_DURATION_S = 3600.0
    TIMESTEP_S = 0.5
    RECORD_PERIOD_S = 1.0
    PRINT_PERIOD_S = 3600.0

    # Toggles
    INCLUDE_PERMANENT_MAGNET = True
    INCLUDE_HYSTERESIS_RODS = True
    INCLUDE_POWER_MANAGEMENT = True
    INCLUDE_ORIENTATION_PRINTOUT = True
    INCLUDE_VIZARD = False

    # Rods
    ROD_DIAMETER_M = 0.002
    ROD_LENGTH_M = 0.095
    ROD_DEFS = None
    INV_SQRT2 = 0.70710678118654752

    # Power
    BATTERY_CAPACITY_WH = 100.0
    BATTERY_INITIAL_SOC = 0.8

    # Output
    EXPERIMENT_NAME = "unnamed"

    def __init__(self):
        self.scSim = None
        self.dynProcess = None
        self.scObject = None
        self.gravFactory = None
        self.spiceObject = None
        self.magModule = None
        self.permMagnet = None
        self.rods = {}
        self.sim_state = None
        self.power_manager = None
        self.recorders = {}
        self._device_instances = []
        self.output_dir = os.path.join(
            _ROOT, "experiments", self.EXPERIMENT_NAME, "output"
        )

    def devices(self):
        return []

    def solar_cells(self):
        return []

    def add_recorders(self, rec_period):
        return {}

    def postprocess(self, output_dir):
        pass

    def _default_rod_defs(self):
        configs = os.path.join(_ROOT, "configs", "hysteresis")
        z_json = os.path.join(configs, "hymu80_z_axis.json")
        xy_json = os.path.join(configs, "hymu80_xy_axis.json")
        return [
            ("HystRod_Z1", [0.0, 0.0, 1.0], z_json),
            ("HystRod_Z2", [0.0, 0.0, 1.0], z_json),
            ("HystRod_X1", [1.0, 0.0, 0.0], xy_json),
            ("HystRod_X2", [1.0, 0.0, 0.0], xy_json),
            ("HystRod_Y1", [0.0, 1.0, 0.0], xy_json),
            ("HystRod_Y2", [0.0, 1.0, 0.0], xy_json),
            ("HystRod_D1", [self.INV_SQRT2, self.INV_SQRT2, 0.0], xy_json),
            ("HystRod_D2", [self.INV_SQRT2, -self.INV_SQRT2, 0.0], xy_json),
        ]

    def build(self):
        os.makedirs(self.output_dir, exist_ok=True)
        print(f"\n{'='*60}")
        print(f"EXPERIMENT: {self.EXPERIMENT_NAME}")
        print(f"Output: {self.output_dir}")
        print(f"{'='*60}\n")

        self.scSim = SimulationBaseClass.SimBaseClass()
        self.scSim.SetProgressBar(False)
        self.dynProcess = self.scSim.CreateNewProcess("simProcess")
        self.dynProcess.addTask(
            self.scSim.CreateNewTask("simTask", macros.sec2nano(self.TIMESTEP_S))
        )

        self._setup_spacecraft()
        self._setup_environment()

        if self.INCLUDE_PERMANENT_MAGNET:
            self._setup_permanent_magnet()
        if self.INCLUDE_HYSTERESIS_RODS:
            self._setup_hysteresis_rods()

        self._device_instances = self.devices()
        if self.INCLUDE_POWER_MANAGEMENT:
            self._setup_power_management()

        self._setup_standard_recorders()
        self.recorders.update(self.add_recorders(macros.sec2nano(self.RECORD_PERIOD_S)))

        if self.INCLUDE_ORIENTATION_PRINTOUT:
            self._setup_orientation_printout()
        if self.INCLUDE_VIZARD:
            self._setup_vizard()

    def _setup_spacecraft(self):
        scObject = spacecraft.Spacecraft()
        scObject.ModelTag = "PEROVSAT"
        scObject.hub.mHub = self.MASS_KG
        scObject.hub.IHubPntBc_B = self.INERTIA_KGM2
        scObject.hub.sigma_BNInit = self.SIGMA_INIT
        scObject.hub.omega_BN_BInit = self.OMEGA_INIT_RADS
        self.integrator = svIntegrators.svIntegratorRKF45(scObject)
        scObject.setIntegrator(self.integrator)
        self.scSim.AddModelToTask("simTask", scObject)
        self.scObject = scObject

    def _setup_environment(self):
        self.gravFactory, self.spiceObject, self.magModule, self.sunStateMsg = \
            setup_environment(self.scSim, self.scObject, "simTask", self.EPOCH_UTC)

    def _setup_permanent_magnet(self):
        pm = PermanentMagnet()
        pm.ModelTag = "PermanentMagnet"
        pm.magDipole_B = self.DIPOLE_BODY_AM2
        pm.magFieldInMsg.subscribeTo(self.magModule.envOutMsgs[0])
        self.scObject.addDynamicEffector(pm)
        self.scSim.AddModelToTask("simTask", pm)
        self.permMagnet = pm

    def _setup_hysteresis_rods(self):
        factory = HysteresisFactory(self.scSim, self.scObject, self.magModule)
        rod_defs = self.ROD_DEFS or self._default_rod_defs()
        for tag, axis, json_path in rod_defs:
            rod = factory.add_rod(
                length_m=self.ROD_LENGTH_M,
                diameter_m=self.ROD_DIAMETER_M,
                axis_B=axis,
                json_path=json_path,
                tag=tag,
            )
            self.rods[tag] = rod

    def _setup_power_management(self):
        self.sim_state = SimulationState(self.scObject.scStateOutMsg, self.sunStateMsg)
        self.power_manager, task = create_power_manager(
            self.scSim, self._device_instances, self.sim_state, self.solar_cells(),
            battery_capacity_wh=self.BATTERY_CAPACITY_WH,
            battery_initial_soc=self.BATTERY_INITIAL_SOC,
            update_period_s=self.TIMESTEP_S,
        )
        self.dynProcess.addTask(task)
        self.power_task = task

    def _setup_standard_recorders(self):
        rp = macros.sec2nano(self.RECORD_PERIOD_S)
        self.recorders["scState"] = self._attach_recorder(self.scObject.scStateOutMsg, rp)
        if self.magModule is not None:
            self.recorders["mag"] = self._attach_recorder(self.magModule.envOutMsgs[0], rp)
        if self.permMagnet is not None:
            self.recorders["pmTorque"] = self._attach_recorder(self.permMagnet.cmdTorqueOutMsg, rp)
        if self.rods:
            torque_recs, hyst_recs = {}, {}
            for tag, rod in self.rods.items():
                torque_recs[tag] = self._attach_recorder(rod.torqueLogOutMsg, rp)
                hyst_recs[tag] = self._attach_recorder(rod.hysteresisDebugOutMsg, rp)
            self.recorders["rodTorques"] = torque_recs
            self.recorders["hysteresis"] = hyst_recs

    def _attach_recorder(self, msg, period_ns):
        rec = msg.recorder(period_ns)
        self.scSim.AddModelToTask("simTask", rec)
        return rec

    def _setup_orientation_printout(self):
        self.print_task = self.scSim.CreateNewTask(
            "printTask", macros.sec2nano(self.PRINT_PERIOD_S))
        self.dynProcess.addTask(self.print_task)
        self.orientation_monitor = OrientationMonitor(self.scObject.scStateOutMsg)
        self.scSim.AddModelToTask("printTask", self.orientation_monitor)

    def _setup_vizard(self):
        try:
            from Basilisk.utilities import vizSupport
            if vizSupport.vizFound:
                viz_path = os.path.join(self.output_dir, "viz")
                vizSupport.enableUnityVisualization(
                    self.scSim, "simTask", self.scObject, saveFile=viz_path)
        except ImportError:
            pass

    def run(self):
        self.build()
        print(f"\nRunning simulation for {self.SIM_DURATION_S:.1f} s...")
        self.scSim.InitializeSimulation()
        self.scSim.ConfigureStopTime(macros.sec2nano(self.SIM_DURATION_S))
        self.scSim.ExecuteSimulation()
        print("Simulation complete.\n")
        self.postprocess(self.output_dir)
        self._write_summary()

    def _write_summary(self):
        path = os.path.join(self.output_dir, "summary.txt")
        with open(path, "w") as f:
            f.write(f"Experiment: {self.EXPERIMENT_NAME}\n")
            f.write(f"Run at: {datetime.now().isoformat()}\n")
            f.write(f"{'='*60}\n")
            f.write(f"Duration: {self.SIM_DURATION_S:.1f} s\n")
            f.write(f"Timestep: {self.TIMESTEP_S:.3f} s\n")
            f.write(f"Devices: {len(self._device_instances)}\n")
            f.write(f"Rods: {len(self.rods)}\n")
            if self.power_manager:
                f.write(f"Final SOC: {self.power_manager.soc*100:.1f}%\n")
        print(f"Summary: {path}")