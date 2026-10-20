"""The one PEROVSAT Basilisk vehicle.

Experiments pass a ``RunConfig`` and read numpy off ``sim.log``. Vehicle
hardware lives in ``config.py``; this module only orchestrates Basilisk.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from Basilisk.simulation import spacecraft, svIntegrators
from Basilisk.utilities import SimulationBaseClass, macros, vizSupport

from perovsat import config
from perovsat._bsk import attach_recorder
from perovsat.environment import Environment, setup_environment
from perovsat.log import SimLog, SimulationRecorders
from perovsat.pmac import PmacStack, setup_pmac
from perovsat.power import PowerStack, setup_power
from perovsat.run_config import RunConfig

_TASK = "simTask"




class PerovSatSimulation:
    """Own the Basilisk wrappers for exactly one execution."""

    def __init__(self, cfg: RunConfig):
        self.config = cfg
        self.output_dir = Path(cfg.output_dir) if cfg.output_dir else Path("output")
        self._started = False
        self.scSim: SimulationBaseClass.SimBaseClass | None = None
        self.scObject: spacecraft.Spacecraft | None = None
        self.integrator: svIntegrators.svIntegratorRKF45 | None = None
        self.env: Environment | None = None
        self.pmac: PmacStack | None = None
        self.power: PowerStack | None = None
        self.viz = None
        self.log: SimLog | None = None
        self.pacer = None
        self.status = "not started"

    def run(self) -> SimLog:
        if self._started:
            raise RuntimeError("simulation instances support one run; create a new instance")
        self.config.validate()
        config.validate_vehicle()
        self._started = True
        self._build()
        print(
            f"\nRunning {self.config.name} for {self.config.duration_s:.1f} s "
            f"(dt={self.config.timestep_s} s)..."
        )
        self.scSim.InitializeSimulation()
        self.scSim.ConfigureStopTime(macros.sec2nano(self.config.duration_s))
        self.status = "running"
        try:
            self.scSim.ExecuteSimulation()
        except (Exception, KeyboardInterrupt):
            self.status = "interrupted or failed"
            self._write_summary()
            if self.pacer is not None and self.pacer.failure:
                raise RuntimeError(self.pacer.failure) from None
            raise
        self.status = "complete"
        print("Simulation complete.\n")
        assert self.log is not None
        self.log.validate()
        self._write_summary()
        return self.log

    def _build(self):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        cfg = self.config
        print(f"\n{'=' * 60}\nPEROVSAT  {cfg.name}\nOutput: {self.output_dir}\n{'=' * 60}\n")

        self.scSim = SimulationBaseClass.SimBaseClass()
        self.scSim.SetProgressBar(not cfg.realtime)
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
        if cfg.vizard or cfg.vizard_live:
            self._setup_vizard()

        recorders = SimulationRecorders(
            scState=attach_recorder(self.scSim, _TASK, self.scObject.scStateOutMsg, rec_ns),
            environment=self.env.recorders,
            pmac=self.pmac.recorders,
            power=self.power.recorders,
        )
        self.log = SimLog(recorders, self.power.capacity_ws)
        if cfg.realtime:
            from perovsat.realtime import RealtimePacer

            self.pacer = RealtimePacer(cfg)
            # Lower priority runs after physics, output, and recorders (priority 0).
            self.scSim.AddModelToTask(_TASK, self.pacer, -100)

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
            if self.config.vizard_live:
                raise RuntimeError("Live Vizard requested but Vizard support is unavailable")
            print("Vizard support not found; skipping Unity visualization output.")
            return
        # Basilisk appends ``_UnityViz.bin`` to this path.
        save_file = str((self.output_dir / self.config.name).resolve())
        self.viz = vizSupport.enableUnityVisualization(
            self.scSim, _TASK, self.scObject,
            saveFile=save_file if self.config.vizard else None,
            liveStream=self.config.vizard_live,
        )
        if self.config.vizard_live:
            # Basilisk 2.10.2 connects; Vizard owns the listening socket.
            self.viz.reqComAddress = self.config.vizard_address
            print(f"Vizard destination: tcp://{self.config.vizard_address}:5556")
        if self.config.vizard:
            print(f"Vizard: {save_file}_UnityViz.bin")

    def _write_summary(self):
        path = self.output_dir / "summary.txt"
        cfg = self.config
        lines = [
            f"Experiment: {cfg.name}",
            f"Status: {self.status}",
            f"Run at: {datetime.now().isoformat()}",
            "=" * 60,
            f"Duration: {cfg.duration_s:.1f} s",
            f"Timestep: {cfg.timestep_s:.3f} s",
            f"Record period: {cfg.record_period_s:.3f} s",
            f"Vizard: {'on' if cfg.vizard else 'off'}",
            f"Vizard live: {'on' if cfg.vizard_live else 'off'}",
            f"Real-time: {'on' if cfg.realtime else 'off'}",
        ]
        if self.pacer is not None:
            lines.extend(self.pacer.summary())
        if self.log is not None and self.log.power.soc is not None and len(self.log.power.soc):
            lines.append(f"Final SOC: {self.log.power.soc[-1] * 100:.1f}%")
        path.write_text("\n".join(lines) + "\n")
        print(f"Summary: {path}")
