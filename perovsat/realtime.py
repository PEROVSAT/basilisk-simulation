"""Wall-clock pacing at the end of each physics tick; no physics steps skipped."""

import time
import warnings

from Basilisk.architecture import sysModel
from Basilisk.simulation import simSynch


class RealtimePacer(sysModel.SysModel):
    """Retain the native clock and collect constant-memory timing statistics."""

    def __init__(self, cfg):
        super().__init__()
        self.ModelTag = "realtimePacer"
        self.config = cfg
        self.clock = simSynch.ClockSynch()
        self.clock.accelFactor = cfg.realtime_factor
        self.clock.displayTime = False
        self.started = None
        self.previous = None
        self.elapsed_s = 0.0
        self.simulation_s = 0.0
        self.max_work_s = 0.0
        self.max_lag_s = 0.0
        self.overruns = 0
        self.failure = None

    def Reset(self, current_time):
        self.clock.Reset(current_time)

    def UpdateState(self, current_time):
        before = time.perf_counter()
        if self.started is None:
            # First tick establishes the epoch after initialization/connection setup.
            self.started = before
            self.origin_ns = current_time
        else:
            self.max_work_s = max(self.max_work_s, before - self.previous)
        self.clock.UpdateState(current_time)
        self.previous = time.perf_counter()
        self.elapsed_s = self.previous - self.started
        self.simulation_s = (current_time - self.origin_ns) * 1e-9
        lag = max(0.0, self.elapsed_s - self.simulation_s / self.config.realtime_factor)
        self.max_lag_s = max(self.max_lag_s, lag)
        if lag > self.config.max_lag_s:
            self.overruns += 1
            message = f"Real-time lag {lag:.3f} s exceeds {self.config.max_lag_s:.3f} s"
            if self.config.overrun_policy == "stop":
                # SWIG replaces callback exceptions; retain the actionable reason.
                self.failure = message
                raise RuntimeError(message)
            if self.overruns == 1:
                warnings.warn(message, RuntimeWarning, stacklevel=2)

    def summary(self):
        return [
            f"Real-time factor: {self.config.realtime_factor:g}",
            f"Paced simulation time: {self.simulation_s:.6f} s",
            f"Paced wall time: {self.elapsed_s:.6f} s",
            f"Maximum tick work (including host overhead): {self.max_work_s:.6f} s",
            f"Maximum lag: {self.max_lag_s:.6f} s",
            f"Ticks exceeding lag limit: {self.overruns}",
        ]
