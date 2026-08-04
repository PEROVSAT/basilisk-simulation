"""
base.py — Experiment base class for PEROVSAT Basilisk simulations.

An "experiment" is a subclass of ExperimentBase that:
  * overrides class-level parameters it cares about (spacecraft properties,
    duration, which subsystems are active, battery size, ...),
  * overrides devices() / solar_cells() to say which SimulatedDevices and
    SolarCells exist for this run,
  * overrides postprocess() for its own custom analysis/plots.

base.py itself should basically never need to change -- only touch it when
adding a genuinely new subsystem (a new dynamic effector, a new environment
model, etc). Everything experiment-specific belongs in the experiment file.
Never create a new experiment by copy-pasting this file: subclass it.

Minimal example (see sims/graph_power_states.py / sims/detumble_experiment.py
for full examples):

    from base import ExperimentBase

    class MyExperiment(ExperimentBase):
        SIM_DURATION_S = 3600.0

        def devices(self):
            return [...]

        def solar_cells(self):
            return [...]

        def postprocess(self):
            # self.power_manager, self.recorders, self.scObject, etc. are
            # all populated by now -- do your custom plotting/analysis here.
            ...

    if __name__ == "__main__":
        MyExperiment().run()
"""

import os
import sys

import numpy as np

from Basilisk.architecture import sysModel
from Basilisk.simulation import magneticFieldWMM, spacecraft, svIntegrators
from Basilisk.utilities import SimulationBaseClass, macros, vizSupport
from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

# ---------------------------------------------------------------------------
# Path setup & Imports
# ---------------------------------------------------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, "PythonModules"))

try:
    import perovsat_plugins.messaging
    from perovsat_plugins.permanentMagnet import PermanentMagnet
except ImportError as exc:
    raise ImportError(f"Compiled plugin modules not found.\nOriginal error: {exc}") from exc

from issOrbit import set_iss_orbit
from hysteresisFactory import HysteresisFactory
from solarSystemFactory import setup_solar_system, wire_wmm_epoch
from sim_state import SimulationState
from power_management import create_power_manager


class OrientationMonitor(sysModel.SysModel):
    """Periodic console printout of attitude/rate. Generic utility -- every
    experiment gets it for free via INCLUDE_ORIENTATION_PRINTOUT."""

    def __init__(self, scStateOutMsg):
        super().__init__()
        self.ModelTag = "OrientationMonitor"
        self.scStateOutMsg = scStateOutMsg

    def UpdateState(self, currentSimNanos):
        state = self.scStateOutMsg.read()
        t_s = currentSimNanos * macros.NANO2SEC
        sigma = state.sigma_BN
        omega_deg = np.degrees(state.omega_BN_B)
        omega_mag_deg = np.degrees(np.linalg.norm(state.omega_BN_B))
        print(
            f"t={t_s:10.1f}s  sigma_BN=[{sigma[0]:+.4f}, {sigma[1]:+.4f}, {sigma[2]:+.4f}]"
            f"  omega_BN_B=[{omega_deg[0]:+.4f}, {omega_deg[1]:+.4f}, {omega_deg[2]:+.4f}] deg/s"
            f"  |omega|={omega_mag_deg:.4f} deg/s"
        )


class ExperimentBase:
    """
    Every parameter below is a class attribute, so a subclass overrides one
    simply by re-declaring it -- no __init__ override needed for the common
    case. Subsystems can be switched off entirely with the INCLUDE_* flags
    for lightweight experiments that don't need them (e.g. a pure power-model
    experiment doesn't need hysteresis rods).
    """

    # ---- Spacecraft ----
    MASS_KG = 1.2
    INERTIA_KGM2 = [[0.002, 0.0, 0.0],
                    [0.0, 0.002, 0.0],
                    [0.0, 0.0, 0.001]]
    SIGMA_INIT = [[0.2], [-0.1], [0.3]]
    OMEGA_INIT_RADS = [[0.05], [0.07], [0.02]]

    EPOCH_UTC = "2026 JUN 21 12:00:00.0 (UTC)"

    # ---- Timing ----
    SIM_DURATION_S = 3600.0
    TIMESTEP_S = 0.5
    RECORD_PERIOD_S = 1.0
    PRINT_PERIOD_S = 3600.0
    POWER_UPDATE_PERIOD_S = None   # None -> defaults to TIMESTEP_S

    # ---- Subsystem toggles ----
    INCLUDE_PERMANENT_MAGNET = True
    INCLUDE_HYSTERESIS_RODS = True
    INCLUDE_POWER_MANAGEMENT = True
    INCLUDE_ORIENTATION_PRINTOUT = True
    INCLUDE_VIZARD = True

    # ---- Permanent magnet ----
    DIPOLE_BODY_AM2 = np.array([0.0, 0.0, 0.15])

    # ---- Hysteresis rods ----
    ROD_DIAMETER_M = 0.002
    ROD_LENGTH_M = 0.095
    INV_SQRT2 = 0.70710678118654752
    ROD_DEFS = None     # None -> _default_rod_defs()

    # ---- Power management ----
    BATTERY_CAPACITY_WH = 100.0
    BATTERY_INITIAL_SOC = 0.8

    # ---- Output ----
    VIZARD_OUTPUT = None   # None -> derived from the experiment file's path

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
        self.recorders = {}     # name -> recorder (or dict of recorders)

    # ------------------------------------------------------------------
    # Extension points -- override in subclasses
    # ------------------------------------------------------------------
    def devices(self):
        """SimulatedDevice instances active for this experiment. Construct
        fresh instances here (not as class attributes) so re-running the
        experiment doesn't reuse stale device state."""
        return []

    def solar_cells(self):
        """SolarCell instances active for this experiment."""
        return []

    def postprocess(self):
        """Called once after ExecuteSimulation(). Override for custom
        analysis/graphing -- self.recorders / self.power_manager /
        self.scObject / self.rods are all populated by then."""
        pass

    # ------------------------------------------------------------------
    def _configs_dir(self):
        return os.path.join(_root, "hysteresis_configs")

    def _default_rod_defs(self):
        cd = self._configs_dir()
        z_json = os.path.join(cd, "hymu80_z_axis.json")
        xy_json = os.path.join(cd, "hymu80_xy_axis.json")
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

    # ------------------------------------------------------------------
    # Build: all the Basilisk wiring. Should essentially never change per
    # experiment; add a whole new _setup_* method here only when a genuinely
    # new subsystem/feature is implemented, and gate it behind its own
    # INCLUDE_* flag so existing experiments are unaffected.
    # ------------------------------------------------------------------
    def build(self):
        self.scSim = SimulationBaseClass.SimBaseClass()
        self.scSim.SetProgressBar(False)

        self.dynProcess = self.scSim.CreateNewProcess("simProcess")
        self.dynProcess.addTask(self.scSim.CreateNewTask("simTask", macros.sec2nano(self.TIMESTEP_S)))

        self._setup_spacecraft()
        self._setup_environment()
        if self.INCLUDE_PERMANENT_MAGNET:
            self._setup_permanent_magnet()
        if self.INCLUDE_HYSTERESIS_RODS:
            self._setup_hysteresis_rods()
        if self.INCLUDE_POWER_MANAGEMENT:
            self._setup_power_management()
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
        gravFactory, spiceObject = setup_solar_system(self.scSim, self.scObject, "simTask", self.EPOCH_UTC)
        set_iss_orbit(self.scObject, gravFactory.gravBodies["earth"].mu)
        self.gravFactory = gravFactory
        self.spiceObject = spiceObject

        magModule = magneticFieldWMM.MagneticFieldWMM()
        magModule.ModelTag = "WMM"
        magModule.configureWMMFile(str(get_path(DataFile.MagneticFieldData.WMM)))
        magModule.addSpacecraftToModel(self.scObject.scStateOutMsg)
        wire_wmm_epoch(magModule, gravFactory, spiceObject)
        self.scSim.AddModelToTask("simTask", magModule)
        self.magModule = magModule

        rec_period = macros.sec2nano(self.RECORD_PERIOD_S)
        magRec = magModule.envOutMsgs[0].recorder(rec_period)
        self.scSim.AddModelToTask("simTask", magRec)
        self.recorders["mag"] = magRec

        scStateRec = self.scObject.scStateOutMsg.recorder(rec_period)
        self.scSim.AddModelToTask("simTask", scStateRec)
        self.recorders["scState"] = scStateRec

        sunIdx = gravFactory.spicePlanetNames.index("sun")
        self.sunStateMsg = spiceObject.planetStateOutMsgs[sunIdx]

    def _setup_permanent_magnet(self):
        permMagnet = PermanentMagnet()
        permMagnet.ModelTag = "PermanentMagnet"
        permMagnet.magDipole_B = self.DIPOLE_BODY_AM2
        permMagnet.magFieldInMsg.subscribeTo(self.magModule.envOutMsgs[0])
        self.scObject.addDynamicEffector(permMagnet)
        self.scSim.AddModelToTask("simTask", permMagnet)
        self.permMagnet = permMagnet

        pmTorqueRec = permMagnet.cmdTorqueOutMsg.recorder(macros.sec2nano(self.RECORD_PERIOD_S))
        self.scSim.AddModelToTask("simTask", pmTorqueRec)
        self.recorders["pmTorque"] = pmTorqueRec

    def _setup_hysteresis_rods(self):
        self.rod_factory = HysteresisFactory(self.scSim, self.scObject, self.magModule)
        rod_defs = self.ROD_DEFS or self._default_rod_defs()
        rec_period = macros.sec2nano(self.RECORD_PERIOD_S)

        rods, torque_recorders, hyst_recorders = {}, {}, {}
        for tag, axis, json_path in rod_defs:
            rod = self.rod_factory.add_rod(length_m=self.ROD_LENGTH_M, diameter_m=self.ROD_DIAMETER_M,
                                      axis_B=axis, json_path=json_path, tag=tag)
            rods[tag] = rod
            rec = rod.torqueLogOutMsg.recorder(rec_period)
            self.scSim.AddModelToTask("simTask", rec)
            torque_recorders[tag] = rec

        for axis_tag, rod_tag in (("Z", "HystRod_Z1"), ("X", "HystRod_X1"), ("D", "HystRod_D1")):
            if rod_tag in rods:
                rec = rods[rod_tag].hysteresisDebugOutMsg.recorder(rec_period)
                self.scSim.AddModelToTask("simTask", rec)
                hyst_recorders[axis_tag] = rec

        self.rods = rods
        self.recorders["rodTorques"] = torque_recorders
        self.recorders["hysteresis"] = hyst_recorders

    def _setup_power_management(self):
        sim_state = SimulationState(self.scObject.scStateOutMsg, self.sunStateMsg)
        power_manager, task = create_power_manager(
            self.scSim, self.devices(), sim_state, self.solar_cells(),
            battery_capacity_wh=self.BATTERY_CAPACITY_WH,
            battery_initial_soc=self.BATTERY_INITIAL_SOC,
            update_period_s=self.POWER_UPDATE_PERIOD_S or self.TIMESTEP_S,
        )
        self.power_task = task
        self.dynProcess.addTask(self.power_task)
        self.sim_state = sim_state
        self.power_manager = power_manager

    def _setup_orientation_printout(self):
        # NOTE: both objects below MUST be kept as self.* attributes, not just
        # local variables -- Basilisk's C++ scheduler calls back into them
        # every step via a raw reference, so if nothing in Python holds onto
        # them they get garbage-collected as soon as this method returns
        # (before ExecuteSimulation() ever runs), which segfaults.
        self.print_task = self.scSim.CreateNewTask("printTask", macros.sec2nano(self.PRINT_PERIOD_S))
        self.dynProcess.addTask(self.print_task)
        self.orientation_monitor = OrientationMonitor(self.scObject.scStateOutMsg)
        self.scSim.AddModelToTask("printTask", self.orientation_monitor)

    def _setup_vizard(self):
        if not vizSupport.vizFound:
            return
        output = self.VIZARD_OUTPUT or os.path.splitext(os.path.abspath(sys.argv[0]))[0]
        vizSupport.enableUnityVisualization(self.scSim, "simTask", self.scObject, saveFile=output)

    # ------------------------------------------------------------------
    def run(self):
        self.build()
        self.scSim.InitializeSimulation()
        self.scSim.ConfigureStopTime(macros.sec2nano(self.SIM_DURATION_S))
        self.scSim.ExecuteSimulation()
        self.postprocess()
