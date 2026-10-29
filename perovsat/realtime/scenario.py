"""Load a real-time scenario: timestep, duration, and selected devices.

The vehicle epoch places the orbit and the World Magnetic Model. It is not
synchronized with the FlatSat clocks, and it must not be written into sample
times. Selecting ``imu`` records that a future exporter may publish body-frame
IMU stimulus. This slice does not encode frames.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from math import isfinite
from pathlib import Path

from perovsat.validation import positive

_KNOWN_DEVICES = frozenset({"imu"})
_FIELDS = ("timestep_s", "duration_s", "devices")
_FIELD_SET = frozenset(_FIELDS)


def _nanoseconds(value: float) -> int:
    # Same integer-nanosecond rounding used for mission durations.
    scaled = value * 1_000_000_000
    if not isfinite(scaled):
        raise ValueError(f"time {value} is too large to round to nanoseconds")
    return round(scaled)


def _finite_seconds(name: str, value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        got = type(value).__name__
        raise ValueError(f"{name} must be a finite number, got {got}")
    positive(name, value)
    return float(value)


def _device_names(value: object) -> tuple[str, ...]:
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        raise ValueError("devices must be an array of strings")
    names: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str):
            raise ValueError("devices must be an array of strings")
        if item not in _KNOWN_DEVICES:
            raise ValueError(f"unknown device: {item}")
        if item in seen:
            raise ValueError(f"duplicate device: {item}")
        seen.add(item)
        names.append(item)
    return tuple(names)


@dataclass
class Scenario:
    timestep_s: float
    duration_s: float
    devices: tuple[str, ...]

    def __post_init__(self) -> None:
        self.timestep_s = _finite_seconds("timestep_s", self.timestep_s)
        self.duration_s = _finite_seconds("duration_s", self.duration_s)
        self.devices = _device_names(self.devices)
        tick = _nanoseconds(self.timestep_s)
        if tick < 1:
            raise ValueError("timestep_s must be at least one nanosecond")
        span = _nanoseconds(self.duration_s)
        if span < tick or span % tick:
            raise ValueError("duration_s must be a positive multiple of timestep_s")


def load_scenario(path: Path) -> Scenario:
    """Read a UTF-8 JSON scenario. The vehicle epoch is not a field."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("scenario must be a JSON object")
    missing = [name for name in _FIELDS if name not in payload]
    if missing:
        label = "missing key" if len(missing) == 1 else "missing keys"
        raise ValueError(f"{label}: {', '.join(missing)}")
    unknown = [name for name in payload if name not in _FIELD_SET]
    if unknown:
        label = "unknown key" if len(unknown) == 1 else "unknown keys"
        raise ValueError(f"{label}: {', '.join(unknown)}")
    return Scenario(
        timestep_s=payload["timestep_s"],
        duration_s=payload["duration_s"],
        devices=payload["devices"],
    )


def execution_settings(scenario: Scenario) -> dict[str, str | float | bool]:
    """RunConfig fields for one paced run. The vehicle epoch is left unset."""
    return {
        "name": "realtime",
        "duration_s": scenario.duration_s,
        "timestep_s": scenario.timestep_s,
        "record_period_s": scenario.timestep_s,
        "realtime": True,
    }
