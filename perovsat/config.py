"""The PEROVSAT vehicle — numbers, not Basilisk wiring.

Run knobs (duration, timestep, ICs) live on ``RunConfig`` in simulation.py.
Change this file when the satellite changes; branch the repo if you need a
different vehicle.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

_DUTY_SUM_EPS = 1e-9
_INV_SQRT2 = sqrt(0.5)


# ---------------------------------------------------------------------------
# Hub / ADCS
# ---------------------------------------------------------------------------

MASS_KG = 1.2
INERTIA_KGM2 = [
    [0.002, 0.0, 0.0],
    [0.0, 0.002, 0.0],
    [0.0, 0.0, 0.001],
]
DIPOLE_BODY_AM2 = (0.0, 0.0, 0.15)

# Default initial conditions; experiments may override via RunConfig.
SIGMA_INIT = [[0.2], [-0.1], [0.3]]
OMEGA_INIT_RADS = [[0.05], [0.07], [0.02]]
EPOCH_UTC = "2026 JUN 21 12:00:00.0 (UTC)"


# ---------------------------------------------------------------------------
# ISS-like insertion orbit (used by environment.py)
# ---------------------------------------------------------------------------

R_EARTH_KM = 6378.0
ISS_ALT_KM = 420.0
ISS_ECC = 0.0005
ISS_INC_DEG = 51.64
ISS_RAAN_DEG = 48.2
ISS_AOP_DEG = 347.8
ISS_TA_DEG = 85.3


# ---------------------------------------------------------------------------
# Power
# ---------------------------------------------------------------------------

BATTERY_CAPACITY_WH = 100.0
BATTERY_INITIAL_SOC = 0.8


@dataclass(frozen=True)
class Panel:
    n_hat: tuple[float, float, float]
    area_m2: float
    efficiency: float


# Body-fixed bus arrays. Cosine incidence already zeros a face pointed away
# from the Sun; +X / +Y / -Y is the current layout.
PANELS = {
    "+X": Panel(n_hat=(1.0, 0.0, 0.0), area_m2=0.008, efficiency=0.23),
    "+Y": Panel(n_hat=(0.0, 1.0, 0.0), area_m2=0.008, efficiency=0.23),
    "-Y": Panel(n_hat=(0.0, -1.0, 0.0), area_m2=0.008, efficiency=0.23),
}


@dataclass(frozen=True)
class DeviceState:
    name: str
    power_w: float
    duty: float  # time fraction in this state; leftover duty is off at 0 W

    def __post_init__(self) -> None:
        if not 0.0 <= self.duty <= 1.0:
            raise ValueError(f"duty must be in [0, 1], got {self.duty}")


@dataclass(frozen=True)
class Device:
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


# Design-phase loads: constant average draw, one SimplePowerSink per type.
DEVICES = (
    Device("NSLBus", 1, (DeviceState("active", 0.6, 1.0),)),
    Device(
        "OBC",
        1,
        (
            DeviceState("idle", 0.01, 0.75),
            DeviceState("active", 0.1, 0.25),
        ),
    ),
    Device("Eyestar", 1, (DeviceState("transmit", 1.4, 0.1),)),
    Device(
        "IMU",
        1,
        (
            DeviceState("idle", 0.001, 0.9),
            DeviceState("active", 0.01, 0.1),
        ),
    ),
    Device(
        "SunSensor",
        2,
        (
            DeviceState("idle", 0.002, 0.9),
            DeviceState("active", 0.04, 0.1),
        ),
    ),
    Device(
        "AMU",
        16,
        (
            DeviceState("idle", 0.002, 0.95),
            DeviceState("active", 0.018, 0.05),
        ),
    ),
)


# ---------------------------------------------------------------------------
# Hysteresis rods (Flatley–Henretty as-installed params; demag folded in)
# ---------------------------------------------------------------------------

ROD_LENGTH_M = 0.095
ROD_DIAMETER_M = 0.002


@dataclass(frozen=True)
class HystMaterial:
    Bs: float
    Br: float
    Hc: float
    M0: float = 0.0


MATERIALS = {
    "z": HystMaterial(Bs=0.75, Br=0.001, Hc=5.0, M0=0.0),
    "xy": HystMaterial(Bs=0.75, Br=0.003, Hc=15.0, M0=0.0),
}


@dataclass(frozen=True)
class Rod:
    tag: str
    axis: tuple[float, float, float]
    material: str


RODS = (
    Rod("HystRod_Z1", (0.0, 0.0, 1.0), "z"),
    Rod("HystRod_Z2", (0.0, 0.0, 1.0), "z"),
    Rod("HystRod_X1", (1.0, 0.0, 0.0), "xy"),
    Rod("HystRod_X2", (1.0, 0.0, 0.0), "xy"),
    Rod("HystRod_Y1", (0.0, 1.0, 0.0), "xy"),
    Rod("HystRod_Y2", (0.0, 1.0, 0.0), "xy"),
    Rod("HystRod_D1", (_INV_SQRT2, _INV_SQRT2, 0.0), "xy"),
    Rod("HystRod_D2", (_INV_SQRT2, -_INV_SQRT2, 0.0), "xy"),
)
