"""Execution parameters, independent of the Basilisk runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from perovsat.bridge import parse_address
from perovsat.validation import positive, fraction


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
    realtime: bool = False
    realtime_factor: float = 1.0
    max_lag_s: float = 0.1
    overrun_policy: str = "warn"
    vizard_live: bool = False
    vizard_address: str = "127.0.0.1"
    vizard_timeout_s: float = 120.0
    imu_stimulus: bool = False
    imu_print_every: int = 0
    # HITL bridge TCP listener ("host:port"); None keeps the sample local.
    imu_bridge: str | None = None
    imu_destination: int = 1   # emulated MPU6050 participant address
    imu_source: int = 252      # this simulation's participant address

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        for name in ("duration_s", "timestep_s", "record_period_s",
                     "realtime_factor", "max_lag_s", "vizard_timeout_s"):
            positive(name, getattr(self, name))
        if (not isinstance(self.vizard_address, str) or not self.vizard_address
                or any(c.isspace() or c in ":/" for c in self.vizard_address)):
            raise ValueError("vizard_address must be an IPv4 address or hostname without spaces, protocol, or port")
        if self.overrun_policy not in ("warn", "stop"):
            raise ValueError("overrun_policy must be 'warn' or 'stop'")
        if (not isinstance(self.imu_print_every, int) or isinstance(self.imu_print_every, bool)
                or self.imu_print_every < 0):
            raise ValueError("imu_print_every must be a non-negative integer (0 disables printing)")
        # 0 is the general call and 254 is the bridge's own address.
        for name, low, high in (("imu_destination", 0, 253), ("imu_source", 1, 253)):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f"{name} must be an integer in {low}..{high}")
        if self.imu_source == self.imu_destination:
            raise ValueError("imu_source and imu_destination must differ")
        if self.imu_bridge is not None:
            if not self.imu_stimulus:
                raise ValueError("imu_bridge requires imu_stimulus=True")
            parse_address(self.imu_bridge)
        if self.soc_init is not None:
            fraction("initial SOC", self.soc_init)
        for name in ("omega_init", "sigma_init"):
            value = getattr(self, name)
            if value is not None:
                arr = np.asarray(value, dtype=float)
                if arr.shape not in ((3,), (3, 1)) or not np.all(np.isfinite(arr)):
                    raise ValueError(f"{name} must be a finite three-component vector")

