"""Design-phase spacecraft electrical load catalog.

Each entry is a device *type* with time-fraction duties and constant average
draw. ``sim/power.py`` builds one sink per type from these averages; HIL/SITL
device models will replace the static sinks later.
"""

from __future__ import annotations

from dataclasses import dataclass

_DUTY_SUM_EPS = 1e-9


@dataclass(frozen=True)
class DeviceState:
    name: str
    power_w: float
    duty: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.duty <= 1.0:
            raise ValueError(f"duty must be in [0, 1], got {self.duty}")


@dataclass(frozen=True)
class DeviceType:
    name: str
    count: int
    states: tuple[DeviceState, ...]

    def __post_init__(self) -> None:
        if self.count < 1:
            raise ValueError(f"count must be >= 1, got {self.count}")
        duty_sum = sum(s.duty for s in self.states)
        if duty_sum > 1.0 + _DUTY_SUM_EPS:
            raise ValueError(
                f"{self.name}: state duties sum to {duty_sum}, must be <= 1"
            )

    @property
    def average_power_w(self) -> float:
        return self.count * sum(s.power_w * s.duty for s in self.states)


DEVICES: tuple[DeviceType, ...] = (
    DeviceType(
        "NSLBus",
        1,
        (DeviceState("active", 0.6, 1.0),),
    ),
    DeviceType(
        "OBC",
        1,
        (
            DeviceState("idle", 0.01, 0.75),
            DeviceState("active", 0.1, 0.25),
        ),
    ),
    DeviceType(
        "Iridium",
        1,
        (DeviceState("transmit", 1.4, 0.1),),
    ),
    DeviceType(
        "IMU",
        1,
        (
            DeviceState("idle", 0.001, 0.9),
            DeviceState("active", 0.01, 0.1),
        ),
    ),
    DeviceType(
        "SunSensor",
        2,
        (
            DeviceState("idle", 0.002, 0.9),
            DeviceState("active", 0.04, 0.1),
        ),
    ),
    DeviceType(
        "AMU",
        16,
        (
            DeviceState("idle", 0.002, 0.95),
            DeviceState("active", 0.018, 0.05),
        ),
    ),
)


def total_average_power_w() -> float:
    return sum(d.average_power_w for d in DEVICES)


def iter_sink_watts():
    """Yield (sink_name, positive_average_w) for each catalog device type."""
    for device in DEVICES:
        yield device.name, device.average_power_w
