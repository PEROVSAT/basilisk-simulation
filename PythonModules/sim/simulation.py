"""
sim/simulation.py
The one PEROVSAT Basilisk vehicle. Experiments pass a RunConfig and read sim.log.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import os
import sys

import numpy as np

from Basilisk.simulation import spacecraft, svIntegrators
from Basilisk.utilities import SimulationBaseClass, macros

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "PythonModules"))

from hardware.hysteresisFactory import HysteresisFactory
from sim.environment import setup_environment
from sim.log import SimLog
from sim.power import setup_power

try:
    import perovsat_plugins.messaging  # noqa: F401
    from perovsat_plugins.permanentMagnet import PermanentMagnet
except ImportError as exc:
    raise ImportError(f"Compiled plugins not found: {exc}") from exc


# ---------------------------------------------------------------------------
# Vehicle (the satellite does not change between experiments)
# ---------------------------------------------------------------------------

MASS_KG = 1.2
INERTIA_KGM2 = [[0.002, 0.0, 0.0],
                [0.0, 0.002, 0.0],
                [0.0, 0.0, 0.001]]
SIGMA_INIT = [[0.2], [-0.1], [0.3]]
OMEGA_INIT_RADS = [[0.05], [0.07], [0.02]]
DIPOLE_BODY_AM2 = np.array([0.0, 0.0, 0.15])
EPOCH_UTC = "2026 JUN 21 12:00:00.0 (UTC)"
BATTERY_INITIAL_SOC = 0.8

ROD_DIAMETER_M = 0.002
ROD_LENGTH_M = 0.095
_INV_SQRT2 = 0.70710678118654752


def _rod_defs():
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
        ("HystRod_D1", [_INV_SQRT2, _INV_SQRT2, 0.0], xy_json),
        ("HystRod_D2", [_INV_SQRT2, -_INV_SQRT2, 0.0], xy_json),
    ]


@dataclass
class RunConfig:
    """Experiment knobs. Hardware lives in this module and sim/power.py."""

    name: str = "unnamed"
    duration_s: float = 3600.0
    timestep_s: float = 0.5
    record_period_s: float = 1.0
    omega_init: list | None = None
    sigma_init: list | None = None
    soc_init: float | None = None
    epoch_utc: str | None = None
    output_dir: str | None = None


class PerovSatSimulation:
    def __init__(self, config: RunConfig | None = None, **kwargs):
        if config is None:
            config = RunConfig(**kwargs)
        elif kwargs:
            raise TypeError("pass either a RunConfig or keyword overrides, not both")
        self.config = config
        self.output_dir = config.output_dir or os.path.join(
            _ROOT, "experiments", config.name, "output"
        )

        self.scSim = None
        self.scObject = None
        self.env = None
        self.power = None
        self.perm_magnet = None
        self.rods = {}
        self.log: SimLog | None = None

    def run(self) -> SimLog:
        self._build()
        print(f"\nRunning {self.config.name} for {self.config.duration_s:.1f} s "
              f"(dt={self.config.timestep_s} s)...")
        self.scSim.InitializeSimulation()
        self.scSim.ConfigureStopTime(macros.sec2nano(self.config.duration_s))
        self.scSim.ExecuteSimulation()
        print("Simulation complete.\n")
        self._write_summary()
        return self.log

    def _build(self):
        os.makedirs(self.output_dir, exist_ok=True)
        cfg = self.config
        print(f"\n{'=' * 60}")
        print(f"PEROVSAT  {cfg.name}")
        print(f"Output: {self.output_dir}")
        print(f"{'=' * 60}\n")

        self.scSim = SimulationBaseClass.SimBaseClass()
        self.scSim.SetProgressBar(False)
        dyn_process = self.scSim.CreateNewProcess("simProcess")
        dyn_process.addTask(
            self.scSim.CreateNewTask("simTask", macros.sec2nano(cfg.timestep_s))
        )

        self._setup_spacecraft()
        self.env = setup_environment(
            self.scSim, self.scObject, "simTask",
            cfg.epoch_utc or EPOCH_UTC,
        )
        self._setup_permanent_magnet()
        self._setup_hysteresis_rods()
        self.power = setup_power(
            self.scSim,
            "simTask",
            self.scObject.scStateOutMsg,
            self.env.sun_state_msg,
            self.env.eclipse_out_msg,
            macros.sec2nano(cfg.record_period_s),
            soc=cfg.soc_init if cfg.soc_init is not None else BATTERY_INITIAL_SOC,
        )
        self._attach_recorders(macros.sec2nano(cfg.record_period_s))

    def _setup_spacecraft(self):
        cfg = self.config
        sc = spacecraft.Spacecraft()
        sc.ModelTag = "PEROVSAT"
        sc.hub.mHub = MASS_KG
        sc.hub.IHubPntBc_B = INERTIA_KGM2
        sc.hub.sigma_BNInit = cfg.sigma_init if cfg.sigma_init is not None else SIGMA_INIT
        sc.hub.omega_BN_BInit = (
            cfg.omega_init if cfg.omega_init is not None else OMEGA_INIT_RADS
        )
        integrator = svIntegrators.svIntegratorRKF45(sc)
        sc.setIntegrator(integrator)
        self.scSim.AddModelToTask("simTask", sc)
        self.scObject = sc

    def _setup_permanent_magnet(self):
        pm = PermanentMagnet()
        pm.ModelTag = "PermanentMagnet"
        pm.magDipole_B = DIPOLE_BODY_AM2
        pm.magFieldInMsg.subscribeTo(self.env.mag.envOutMsgs[0])
        self.scObject.addDynamicEffector(pm)
        self.scSim.AddModelToTask("simTask", pm)
        self.perm_magnet = pm

    def _setup_hysteresis_rods(self):
        factory = HysteresisFactory(self.scSim, self.scObject, self.env.mag)
        for tag, axis, json_path in _rod_defs():
            self.rods[tag] = factory.add_rod(
                length_m=ROD_LENGTH_M,
                diameter_m=ROD_DIAMETER_M,
                axis_B=axis,
                json_path=json_path,
                tag=tag,
            )

    def _attach_recorders(self, period_ns):
        rec = {
            "scState": self._recorder(self.scObject.scStateOutMsg, period_ns),
            "mag": self._recorder(self.env.mag.envOutMsgs[0], period_ns),
            "pmTorque": self._recorder(self.perm_magnet.cmdTorqueOutMsg, period_ns),
            "eclipse": self._recorder(self.env.eclipse_out_msg, period_ns),
            "battery": self.power.recorders["battery"],
            "panels": self.power.recorders["panels"],
            "sinks": self.power.recorders["sinks"],
            "rodTorques": {},
            "hysteresis": {},
        }
        for tag, rod in self.rods.items():
            rec["rodTorques"][tag] = self._recorder(rod.torqueLogOutMsg, period_ns)
            rec["hysteresis"][tag] = self._recorder(rod.hysteresisDebugOutMsg, period_ns)
        self.log = SimLog(rec, self.power.capacity_ws)

    def _recorder(self, msg, period_ns):
        rec = msg.recorder(period_ns)
        self.scSim.AddModelToTask("simTask", rec)
        return rec

    def _write_summary(self):
        path = os.path.join(self.output_dir, "summary.txt")
        cfg = self.config
        lines = [
            f"Experiment: {cfg.name}",
            f"Run at: {datetime.now().isoformat()}",
            "=" * 60,
            f"Duration: {cfg.duration_s:.1f} s",
            f"Timestep: {cfg.timestep_s:.3f} s",
            f"Record period: {cfg.record_period_s:.3f} s",
            f"Rods: {len(self.rods)}",
        ]
        if self.log is not None and self.log.power.soc is not None and len(self.log.power.soc):
            lines.append(f"Final SOC: {self.log.power.soc[-1] * 100:.1f}%")
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        print(f"Summary: {path}")
