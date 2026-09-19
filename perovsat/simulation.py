"""The one PEROVSAT Basilisk vehicle.

Experiments pass a ``RunConfig`` and read numpy off ``sim.log``. Vehicle
hardware lives in ``config.py``; this module only orchestrates Basilisk.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from Basilisk.simulation import spacecraft, svIntegrators
from Basilisk.utilities import SimulationBaseClass, macros

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


class PerovSatSimulation:
    def __init__(self, cfg: RunConfig):
        self.config = cfg
        self.output_dir = Path(cfg.output_dir) if cfg.output_dir else Path("output")
        self.scSim = None
        self.scObject = None
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
        self.scSim.SetProgressBar(False)
        process = self.scSim.CreateNewProcess("simProcess")
        process.addTask(self.scSim.CreateNewTask(_TASK, macros.sec2nano(cfg.timestep_s)))
        rec_ns = macros.sec2nano(cfg.record_period_s)

        # Spacecraft first, then SPICE/WMM/eclipse, then PMAC, then power
        # (panels need sun + eclipse messages that environment publishes).
        self.scObject = self._setup_spacecraft()
        env = setup_environment(
            self.scSim, self.scObject, _TASK,
            cfg.epoch_utc or config.EPOCH_UTC, rec_ns,
        )
        pmac = setup_pmac(self.scSim, self.scObject, env.mag, _TASK, rec_ns)
        power = setup_power(
            self.scSim, _TASK,
            self.scObject.scStateOutMsg,
            env.sun_state_msg,
            env.eclipse_out_msg,
            rec_ns,
            soc=cfg.soc_init,
        )

        recorders = {
            "scState": attach_recorder(
                self.scSim, _TASK, self.scObject.scStateOutMsg, rec_ns
            ),
            **env.recorders,
            **pmac.recorders,
            **power.recorders,
        }
        self.log = SimLog(recorders, power.capacity_ws)

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
        sc.setIntegrator(svIntegrators.svIntegratorRKF45(sc))
        self.scSim.AddModelToTask(_TASK, sc)
        return sc

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
        ]
        if self.log is not None and self.log.power.soc is not None and len(self.log.power.soc):
            lines.append(f"Final SOC: {self.log.power.soc[-1] * 100:.1f}%")
        path.write_text("\n".join(lines) + "\n")
        print(f"Summary: {path}")
