"""Execution parameters, independent of the Basilisk runtime."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

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

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        for name in ("duration_s", "timestep_s", "record_period_s",
                     "realtime_factor", "max_lag_s"):
            positive(name, getattr(self, name))
        if self.overrun_policy not in ("warn", "stop"):
            raise ValueError("overrun_policy must be 'warn' or 'stop'")
        if self.soc_init is not None:
            fraction("initial SOC", self.soc_init)
        for name in ("omega_init", "sigma_init"):
            value = getattr(self, name)
            if value is not None:
                arr = np.asarray(value, dtype=float)
                if arr.shape not in ((3,), (3, 1)) or not np.all(np.isfinite(arr)):
                    raise ValueError(f"{name} must be a finite three-component vector")

