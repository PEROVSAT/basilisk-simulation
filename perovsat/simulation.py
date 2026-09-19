"""The one PEROVSAT Basilisk vehicle.

Experiments pass a ``RunConfig`` and read numpy off ``sim.log``. Vehicle
hardware lives in ``config.py``; this module only orchestrates Basilisk.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from Basilisk.simulation import spacecraft, svIntegrators
from Basilisk.utilities import SimulationBaseClass, macros, vizSupport

from perovsat import config
from perovsat._bsk import attach_recorder
from perovsat.environment import setup_environment
from perovsat.log import SimLog
from perovsat.pmac import setup_pmac
from perovsat.power import setup_power

_TASK = "simTask"


@dataclass
class RunConfig:
    """Knobs for this execution. The satellite itself is ``config.py``."""

    name: str = "unnamed"
    duration_s: float = 3600.0
    timestep_s: float = 0.5
    record_period_s: float = 1.0
    omega_init: list | None = None
    sigma_init: list | None = None
    soc_init: float | None = None
    epoch_utc: str | None = None
    output_dir: str | Path | None = None
    vizard: bool = False


class PerovSatSimulation:
    def __init__(self, cfg: RunConfig):
        self.config = cfg
        self.output_dir = Path(cfg.output_dir) if cfg.output_dir else Path("output")
        self.scSim = None
        self.scObject = None
        self.integrator = None
        self.env = None
        self.pmac = None
        self.power = None
        self.viz = None
        self.log: SimLog | None = None

    def run(self) -> SimLog:
        self._build()
        print(
            f"\nRunning {self.config.name} for {self.config.duration_s:.1f} s "
            f"(dt={self.config.timestep_s} s)..."
        )
        self.scSim.InitializeSimulation()
        self.scSim.ConfigureStopTime(macros.sec2nano(self.config.duration_s))
        self.scSim.ExecuteSimulation()
        print("Simulation complete.\n")
        self._write_summary()
        return self.log

    def _build(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        cfg = self.config
        print(f"\n{'=' * 60}\nPEROVSAT  {cfg.name}\nOutput: {self.output_dir}\n{'=' * 60}\n")

        self.scSim = SimulationBaseClass.SimBaseClass()
        self.scSim.SetProgressBar(True)
        process = self.scSim.CreateNewProcess("simProcess")
        process.addTask(self.scSim.CreateNewTask(_TASK, macros.sec2nano(cfg.timestep_s)))
        rec_ns = macros.sec2nano(cfg.record_period_s)

        # Spacecraft first, then SPICE/WMM/eclipse, then PMAC, then power
        # (panels need sun + eclipse messages that environment publishes).
        self.scObject = self._setup_spacecraft()
        # Keep these on `self`. Basilisk/SWIG stores raw C++ pointers; if the
        # Python wrappers are collected, ExecuteSimulation segfaults (the
        # integrator is the usual one; gravBodyFactory.epochMsg is the other).
        self.env = setup_environment(
            self.scSim, self.scObject, _TASK,
            cfg.epoch_utc or config.EPOCH_UTC, rec_ns,
        )
        self.pmac = setup_pmac(self.scSim, self.scObject, self.env.mag, _TASK, rec_ns)
        self.power = setup_power(
            self.scSim, _TASK,
            self.scObject.scStateOutMsg,
            self.env.sun_state_msg,
            self.env.eclipse_out_msg,
            rec_ns,
            soc=cfg.soc_init,
        )
        if cfg.vizard:
            self._setup_vizard()

        recorders = {
            "scState": attach_recorder(
                self.scSim, _TASK, self.scObject.scStateOutMsg, rec_ns
            ),
            **self.env.recorders,
            **self.pmac.recorders,
            **self.power.recorders,
        }
        self.log = SimLog(recorders, self.power.capacity_ws)

    def _setup_spacecraft(self):
        cfg = self.config
        sc = spacecraft.Spacecraft()
        sc.ModelTag = "PEROVSAT"
        sc.hub.mHub = config.MASS_KG
        sc.hub.IHubPntBc_B = config.INERTIA_KGM2
        sc.hub.sigma_BNInit = (
            cfg.sigma_init if cfg.sigma_init is not None else config.SIGMA_INIT
        )
        sc.hub.omega_BN_BInit = (
            cfg.omega_init if cfg.omega_init is not None else config.OMEGA_INIT_RADS
        )
        self.integrator = svIntegrators.svIntegratorRKF45(sc)
        sc.setIntegrator(self.integrator)
        self.scSim.AddModelToTask(_TASK, sc)
        return sc

    def _setup_vizard(self):
        if not vizSupport.vizFound:
            print("Vizard support not found; skipping Unity visualization output.")
            return
        # Basilisk appends ``_UnityViz.bin`` to this path.
        save_file = str((self.output_dir / self.config.name).resolve())
        self.viz = vizSupport.enableUnityVisualization(
            self.scSim, _TASK, self.scObject, saveFile=save_file,
        )
        print(f"Vizard: {save_file}_UnityViz.bin")

    def _write_summary(self):
        path = self.output_dir / "summary.txt"
        cfg = self.config
        lines = [
            f"Experiment: {cfg.name}",
            f"Run at: {datetime.now().isoformat()}",
            "=" * 60,
            f"Duration: {cfg.duration_s:.1f} s",
            f"Timestep: {cfg.timestep_s:.3f} s",
            f"Record period: {cfg.record_period_s:.3f} s",
            f"Vizard: {'on' if cfg.vizard else 'off'}",
        ]
        if self.log is not None and self.log.power.soc is not None and len(self.log.power.soc):
            lines.append(f"Final SOC: {self.log.power.soc[-1] * 100:.1f}%")
        path.write_text("\n".join(lines) + "\n")
        print(f"Summary: {path}")
