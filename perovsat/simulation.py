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
from perovsat.vizard import wait_for_vizard

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
        self.vizard_status = None
        self.log: SimLog | None = None
        self.pacer = None
        self.imu = None
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
        self.status = "initializing"
        try:
            if self.config.vizard_live:
                self.status = "waiting for Vizard"
                wait_for_vizard(self.config.vizard_address, self.config.vizard_timeout_s)
            self.scSim.InitializeSimulation()
            self.scSim.ConfigureStopTime(macros.sec2nano(self.config.duration_s))
            self.status = "running"
            self.scSim.ExecuteSimulation()
            assert self.log is not None
            self.log.validate()
            if self.imu is not None:
                self.imu.finish()
        except (Exception, KeyboardInterrupt):
            self.status = "interrupted or failed"
            self._write_summary()
            if self.pacer is not None and self.pacer.failure:
                raise RuntimeError(self.pacer.failure) from None
            raise
        finally:
            if self.imu is not None:
                self.imu.close()
        self.status = "complete"
        print("Simulation complete.\n")
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
        if cfg.imu_stimulus:
            from perovsat.imu import add_imu_stimulus

            self.imu = add_imu_stimulus(
                self.scSim, _TASK, self.scObject.scStateOutMsg, cfg, self.output_dir,
            )
        if cfg.realtime:
            from perovsat.realtime import RealtimePacer

            self.pacer = RealtimePacer(cfg)
            if self.vizard_status is not None:
                self.vizard_status.pacer = self.pacer
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
        from perovsat.vizard_status import VizardStatus, set_status_panel

        if self.config.vizard_status_panel:
            self.vizard_status = VizardStatus(
                self.power.battery.batPowerOutMsg, self.env.eclipse_out_msg,
                self.config.timestep_s,
                panel_messages=[panel.nodePowerOutMsg for panel in self.power.panels.values()],
                sink_messages=[sink.nodePowerOutMsg for sink in self.power.sinks.values()],
                duration_s=self.config.duration_s,
                realtime_factor=self.config.realtime_factor if self.config.realtime else None,
                max_lag_s=self.config.max_lag_s,
                diagnostics=self.config.vizard_status_diagnostics,
                state_message=self.scObject.scStateOutMsg,
                sun_message=self.env.sun_state_msg,
            )
            self.scSim.AddModelToTask(_TASK, self.vizard_status)
        self.viz = vizSupport.enableUnityVisualization(
            self.scSim, _TASK, self.scObject,
            saveFile=save_file if self.config.vizard else None,
            liveStream=self.config.vizard_live,
            genericStorageList=[self.vizard_status.gauges] if self.vizard_status else None,
        )
        set_status_panel(self.viz, self.scObject.ModelTag, self.vizard_status is not None)
        # The prepared OBJ is already centered and uses meters. Its visual
        # origin remains provisional; rotation follows the user's face mapping.
        # Do not resolve this viewer-side path with Linux/Docker pathlib.
        # Basilisk 2.10.2 keeps this helper list globally, across simulation
        # instances. Each PEROVSAT run must publish only its own model settings.
        vizSupport.customModelList.clear()
        vizSupport.createCustomModel(
            self.viz,
            modelPath=config.VIZARD_MODEL_PATH,
            simBodiesToModify=[self.scObject.ModelTag],
            offset=[0.0, 0.0, 0.0],
            rotation=list(config.VIZARD_MODEL_ROTATION_RAD),
            scale=[1.0, 1.0, 1.0],
        )
        print(f"Vizard spacecraft model: {config.VIZARD_MODEL_PATH} (user face mapping applied)")
        # Body axes rotate with the same attitude used by the face illumination
        # gauges. Vizard updates the Sun direction from the streamed body states.
        from Basilisk.simulation import vizInterface
        self.viz.settings.spacecraftCSon = 1
        self.viz.settings.showCSLabels = 1
        self.viz.settings.forceStartAtSpacecraftLocalView = 1
        sun_line = vizInterface.PointLine()
        sun_line.fromBodyName = self.scObject.ModelTag
        sun_line.toBodyName = self.env.grav_factory.gravBodies["sun"].displayName
        sun_line.lineColor = vizSupport.toRGBA255([255, 205, 64, 255])
        self.viz.settings.pointLineList.push_back(sun_line)
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
        if self.imu is not None:
            lines.extend(self.imu.summary())
        if cfg.vizard_live:
            lines.extend([
                f"Vizard destination: tcp://{cfg.vizard_address}:5556",
                f"Vizard listener timeout: {cfg.vizard_timeout_s:g} s",
            ])
        if self.log is not None and self.log.power.soc is not None and len(self.log.power.soc):
            lines.append(f"Final SOC: {self.log.power.soc[-1] * 100:.1f}%")
        path.write_text("\n".join(lines) + "\n")
        print(f"Summary: {path}")
