"""Validation shared by vehicle and execution configuration."""

from math import isfinite, isclose


def positive(name: str, value: float) -> None:
    if not isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be finite and positive, got {value}")


def fraction(name: str, value: float) -> None:
    if not isfinite(value) or not 0 <= value <= 1:
        raise ValueError(f"{name} must be in [0, 1], got {value}")


def unit_vector(name: str, value) -> None:
    if len(value) != 3 or not all(isfinite(v) for v in value):
        raise ValueError(f"{name} must contain three finite components")
    if not isclose(sum(v * v for v in value), 1.0, abs_tol=1e-9):
        raise ValueError(f"{name} must be a unit vector")
