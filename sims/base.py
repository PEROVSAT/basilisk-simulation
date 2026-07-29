"""
base.py
Experiment base for PEROVSAT simulations.

Assembles the fundamental simulation (spacecraft, orbit, WMM, permanent
magnet, hysteresis rods, power system, payload) and exposes every handle and
recorder on a SimulationResults object. It never plots or interprets anything
-- that belongs to specific experiments in sims/experiments/.

Create an experiment by subclassing BaseExperiment: override configure() to
set parameters and analyze() to interpret results.

    class MyExperiment(BaseExperiment):
        def configure(self):
            self.config.sim_duration_s = 3600.0
            self.config.enable_rods = False
        def analyze(self, results):
            results.power_system.plot_history("power_states.png")

    MyExperiment().main()               # or MyExperiment(sim_duration_s=7200).main()

base.py should only change when a genuinely new subsystem is added: wire it up
in build() (a small _build_* step) and expose its recorder on
SimulationResults so every experiment can reach it.
"""

import os
import sys
from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np

from Basilisk.simulation import magneticFieldWMM, spacecraft, svIntegrators
from Basilisk.utilities import SimulationBaseClass, macros, vizSupport
from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

# ---------------------------------------------------------------------------
# Path setup & imports
# ---------------------------------------------------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, "PythonModules"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))   # sims/ (sysmodels)

try:
    import perovsat_plugins.messaging          # noqa: F401  (registers recorders)
    from perovsat_plugins.permanentMagnet import PermanentMagnet
except ImportError as exc:
    raise ImportError(f"Compiled plugin modules not found.\nOriginal error: {exc}") from exc

from issOrbit import set_iss_orbit
from hysteresisFactory import HysteresisFactory
from solarSystemFactory import setup_solar_system, wire_wmm_epoch
from power_system import PowerSystem
from payload_iv import Payload
from sysmodels import OrientationMonitor, PowerManager

# ---------------------------------------------------------------------------
# Fixed references (not per-experiment tunable)
# ---------------------------------------------------------------------------
EPOCH_UTC_SUMMER = "2026 JUN 21 12:00:00.0 (UTC)"
EPOCH_UTC_WINTER = "2026 DEC 21 12:00:00.0 (UTC)"

_configs_dir = os.path.join(_root, "hysteresis_configs")
Z_JSON = os.path.join(_configs_dir, "hymu80_z_axis.json")
XY_JSON = os.path.join(_configs_dir, "hymu80_xy_axis.json")

INV_SQRT2 = 0.70710678118654752

# 8-rod HyMu80 PMAC layout: (tag, body axis, material JSON).
ROD_LAYOUT = [
    ("HystRod_Z1", [0.0, 0.0, 1.0], Z_JSON),
    ("HystRod_Z2", [0.0, 0.0, 1.0], Z_JSON),
    ("HystRod_X1", [1.0, 0.0, 0.0], XY_JSON),
    ("HystRod_X2", [1.0, 0.0, 0.0], XY_JSON),
    ("HystRod_Y1", [0.0, 1.0, 0.0], XY_JSON),
    ("HystRod_Y2", [0.0, 1.0, 0.0], XY_JSON),
    ("HystRod_D1", [INV_SQRT2,  INV_SQRT2, 0.0], XY_JSON),
    ("HystRod_D2", [INV_SQRT2, -INV_SQRT2, 0.0], XY_JSON),
]


# ---------------------------------------------------------------------------
# Experiment configuration
# ---------------------------------------------------------------------------
@dataclass
class ExperimentConfig:
    """Every per-experiment knob. Subclasses tweak these in configure()."""
    # timing
    sim_duration_s: float = 3600.0
    timestep_s: float = 0.5
    record_period_s: float = 1.0
    power_update_period_s: float = 0.5
    print_period_s: float = 3600.0
    # epoch
    epoch_utc: str = EPOCH_UTC_SUMMER
    # spacecraft
    mass_kg: float = 1.2
    inertia_kgm2: tuple = ((0.002, 0.0, 0.0),
                           (0.0, 0.002, 0.0),
                           (0.0, 0.0, 0.001))
    sigma_init: tuple = (0.2, -0.1, 0.3)
    omega_init_rads: tuple = (0.05, 0.07, 0.02)
    dipole_body_am2: tuple = (0.0, 0.0, 0.15)
    # hysteresis rods
    rod_diameter_m: float = 0.002
    rod_length_m: float = 0.095
    # subsystem toggles
    enable_perm_magnet: bool = True
    enable_rods: bool = True
    enable_power: bool = True
    enable_payload: bool = True
    enable_viz: bool = False
    # power system
    battery_capacity_wh: float = 100.0
    battery_initial_soc: float = 0.8
    # output
    vizard_output: Optional[str] = None


# ---------------------------------------------------------------------------
# Simulation results container (everything an experiment might plot)
# ---------------------------------------------------------------------------
@dataclass
class SimulationResults:
    config: ExperimentConfig
    scSim: Any = None
    scObject: Any = None
    integrator: Any = None   # MUST be kept alive: SWIG won't, and scObject
                             # holds only a raw pointer -> GC = segfault.
    gravFactory: Any = None
    spiceObject: Any = None
    magModule: Any = None
    permMagnet: Any = None
    power_system: Any = None
    payload: Any = None
    power_manager: Any = None
    rods: dict = field(default_factory=dict)
    # recorders
    scStateRec: Any = None
    magRec: Any = None
    pmTorqueRec: Any = None
    torque_recorders: dict = field(default_factory=dict)
    hystRecorders: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Base experiment
# ---------------------------------------------------------------------------
class BaseExperiment:
    """
    Assembles and runs the PEROVSAT simulation. Subclass it, override
    configure() to set parameters and analyze() to interpret/plot results.
    """
    Config = ExperimentConfig

    def __init__(self, **overrides):
        # Precedence: dataclass defaults < configure() < constructor overrides.
        # Config(**overrides) validates the keys; configure() sets the
        # experiment's baseline; then we re-apply overrides so an explicit
        # kwarg always wins over configure() rather than being clobbered by it.
        self.config = self.Config(**overrides)
        self.configure()
        for key, value in overrides.items():
            setattr(self.config, key, value)

    # -- hooks for subclasses -------------------------------------------
    def configure(self):
        """Override to adjust self.config before the simulation is built."""

    def analyze(self, results):
        """Override to print/plot experiment-specific output after the run."""

    # -- lifecycle ------------------------------------------------------
    def build(self) -> SimulationResults:
        """Assemble the simulation from self.config; return SimulationResults."""
        cfg = self.config
        self._sim = SimulationBaseClass.SimBaseClass()
        self._sim.SetProgressBar(False)
        self._process = self._sim.CreateNewProcess("simProcess")
        self._process.addTask(self._sim.CreateNewTask("simTask", macros.sec2nano(cfg.timestep_s)))
        self._rec = macros.sec2nano(cfg.record_period_s)

        r = SimulationResults(config=cfg, scSim=self._sim)
        self._build_spacecraft(r)
        self._build_environment(r)
        if cfg.enable_perm_magnet:
            self._build_magnet(r)
        if cfg.enable_power:
            self._build_power(r)
        if cfg.enable_rods:
            self._build_rods(r)
        self._build_monitors(r)
        self._maybe_enable_viz(r)
        return r

    def run(self) -> SimulationResults:
        """Build and execute the simulation; return the populated results."""
        cfg = self.config
        r = self.build()
        r.scSim.InitializeSimulation()
        print(f"\n[sim] running {cfg.sim_duration_s:.0f} s "
              f"({cfg.sim_duration_s / 3600.0:.2f} h) at dt={cfg.timestep_s}s ...\n")
        r.scSim.ConfigureStopTime(macros.sec2nano(cfg.sim_duration_s))
        r.scSim.ExecuteSimulation()
        print(f"\n[sim] complete: simulated {cfg.sim_duration_s:.0f} s "
              f"({cfg.sim_duration_s / 3600.0:.2f} h)\n")
        return r

    def main(self) -> SimulationResults:
        """Run the simulation, then hand results to analyze()."""
        results = self.run()
        self.analyze(results)
        return results

    # -- build steps (each wires one subsystem onto self._sim) ----------
    def _build_spacecraft(self, r):
        cfg = self.config
        sc = spacecraft.Spacecraft()
        sc.ModelTag = "PEROVSAT"
        sc.hub.mHub = cfg.mass_kg
        sc.hub.IHubPntBc_B = [list(row) for row in cfg.inertia_kgm2]
        sc.hub.sigma_BNInit = [[v] for v in cfg.sigma_init]
        sc.hub.omega_BN_BInit = [[v] for v in cfg.omega_init_rads]
        # Keep the integrator alive on r: SWIG doesn't, and scObject holds only
        # a raw pointer, so GC after build() returns would segfault the run.
        integrator = svIntegrators.svIntegratorRKF45(sc)
        sc.setIntegrator(integrator)
        self._sim.AddModelToTask("simTask", sc)
        r.scObject = sc
        r.integrator = integrator

    def _build_environment(self, r):
        cfg = self.config
        gravFactory, spiceObject = setup_solar_system(self._sim, r.scObject, "simTask", cfg.epoch_utc)
        set_iss_orbit(r.scObject, gravFactory.gravBodies["earth"].mu)
        r.gravFactory = gravFactory
        r.spiceObject = spiceObject

        mag = magneticFieldWMM.MagneticFieldWMM()
        mag.ModelTag = "WMM"
        mag.configureWMMFile(str(get_path(DataFile.MagneticFieldData.WMM)))
        mag.addSpacecraftToModel(r.scObject.scStateOutMsg)
        wire_wmm_epoch(mag, gravFactory, spiceObject)
        self._sim.AddModelToTask("simTask", mag)
        r.magModule = mag
        r.magRec = mag.envOutMsgs[0].recorder(self._rec)
        self._sim.AddModelToTask("simTask", r.magRec)

    def _build_magnet(self, r):
        pm = PermanentMagnet()
        pm.ModelTag = "PermanentMagnet"
        pm.magDipole_B = np.array(self.config.dipole_body_am2)
        pm.magFieldInMsg.subscribeTo(r.magModule.envOutMsgs[0])
        r.scObject.addDynamicEffector(pm)
        self._sim.AddModelToTask("simTask", pm)
        r.permMagnet = pm
        r.pmTorqueRec = pm.cmdTorqueOutMsg.recorder(self._rec)
        self._sim.AddModelToTask("simTask", r.pmTorqueRec)

    def _build_power(self, r):
        cfg = self.config
        power_system = PowerSystem(battery_capacity_wh=cfg.battery_capacity_wh,
                                   initial_soc=cfg.battery_initial_soc)
        payload = Payload() if cfg.enable_payload else None
        sunIdx = r.gravFactory.spicePlanetNames.index("sun")
        sunStateMsg = r.spiceObject.planetStateOutMsgs[sunIdx]
        manager = PowerManager(power_system, r.scObject.scStateOutMsg, sunStateMsg, payload=payload)
        powerTask = self._sim.CreateNewTask("powerTask", macros.sec2nano(cfg.power_update_period_s))
        self._sim.AddModelToTask("powerTask", manager)
        self._process.addTask(powerTask)
        r.power_system = power_system
        r.payload = payload
        r.power_manager = manager

    def _build_rods(self, r):
        cfg = self.config
        factory = HysteresisFactory(self._sim, r.scObject, r.magModule)
        for tag, axis, json_path in ROD_LAYOUT:
            r.rods[tag] = factory.add_rod(length_m=cfg.rod_length_m, diameter_m=cfg.rod_diameter_m,
                                          axis_B=axis, json_path=json_path, tag=tag)
        for tag, rod in r.rods.items():
            rec = rod.torqueLogOutMsg.recorder(self._rec)
            self._sim.AddModelToTask("simTask", rec)
            r.torque_recorders[tag] = rec
        r.hystRecorders = {label: r.rods[tag].hysteresisDebugOutMsg.recorder(self._rec)
                           for label, tag in (("Z", "HystRod_Z1"), ("X", "HystRod_X1"),
                                              ("D", "HystRod_D1"))}
        for rec in r.hystRecorders.values():
            self._sim.AddModelToTask("simTask", rec)

    def _build_monitors(self, r):
        r.scStateRec = r.scObject.scStateOutMsg.recorder(self._rec)
        self._sim.AddModelToTask("simTask", r.scStateRec)
        self._process.addTask(self._sim.CreateNewTask("printTask",
                                                      macros.sec2nano(self.config.print_period_s)))
        self._sim.AddModelToTask("printTask", OrientationMonitor(r.scObject.scStateOutMsg))

    def _maybe_enable_viz(self, r):
        cfg = self.config
        if cfg.enable_viz and vizSupport.vizFound:
            out = cfg.vizard_output or os.path.join(os.getcwd(), "viz")
            vizSupport.enableUnityVisualization(self._sim, "simTask", r.scObject, saveFile=out)


if __name__ == "__main__":
    print("base.py is the experiment base library -- it does not run on its own.\n"
          "Run a specific experiment, e.g.:\n"
          "  python sims/experiments/detumble_full.py\n"
          "  python sims/experiments/graph_power_states.py")
