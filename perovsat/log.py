"""Experiment-facing time series from Basilisk recorders (no Basilisk imports)."""

from __future__ import annotations

from typing import Protocol, Any
from dataclasses import dataclass, field

from perovsat.validation import positive

import numpy as np


class Recorder(Protocol):
    def times(self) -> np.ndarray: ...
    def __getattr__(self, name: str) -> Any: ...


@dataclass
class EnvironmentRecorders:
    mag: Recorder
    eclipse: Recorder


@dataclass
class PmacRecorders:
    pmTorque: Recorder
    rodTorques: dict[str, Recorder] = field(default_factory=dict)
    hysteresis: dict[str, Recorder] = field(default_factory=dict)


@dataclass
class PowerRecorders:
    battery: Recorder
    panels: dict[str, Recorder] = field(default_factory=dict)
    sinks: dict[str, Recorder] = field(default_factory=dict)


@dataclass
class SimulationRecorders:
    scState: Recorder
    environment: EnvironmentRecorders
    pmac: PmacRecorders
    power: PowerRecorders


def _as_array(x) -> np.ndarray:
    return np.asarray(x)


def _times_s(rec: Recorder | None) -> np.ndarray | None:
    if rec is None:
        return None
    try:
        return _as_array(rec.times()) * 1e-9
    except AttributeError as exc:
        raise ValueError("configured recorder has no times()") from exc


def _rec_field(rec: Recorder | None, *names: str) -> np.ndarray | None:
    if rec is None:
        return None
    for name in names:
        try:
            return _as_array(getattr(rec, name))
        except AttributeError:
            continue
    raise ValueError(f"configured recorder is missing field {names}")


def _check_recorder(rec: Recorder, reference: np.ndarray, *fields: str) -> None:
    times = _times_s(rec)
    if times is None or not np.array_equal(times, reference):
        raise ValueError("recorder timestamps do not match")
    if times.ndim != 1 or not np.all(np.isfinite(times)) or np.any(np.diff(times) <= 0):
        raise ValueError("recorder timestamps must be finite and strictly increasing")
    for name in fields:
        values = _rec_field(rec, name)
        if values.ndim == 0 or len(values) != len(times):
            raise ValueError(f"{name}: sample count does not match timestamps")
        vector_fields = {"sigma_BN", "omega_BN_B", "r_BN_N", "magField_N", "torqueRequestBody"}
        if name in vector_fields and values.shape != (len(times), 3):
            raise ValueError(f"{name}: expected three-component samples")
        if name not in vector_fields and values.size != len(times):
            raise ValueError(f"{name}: expected scalar samples")
        if not np.all(np.isfinite(values)):
            raise ValueError(f"{name}: nonfinite samples")


class AttitudeLog:
    def __init__(self, rec: Recorder) -> None:
        self._rec = rec

    @property
    def t(self) -> np.ndarray:
        times = _times_s(self._rec)
        if times is None:
            raise ValueError("attitude recorder has no times()")
        return times

    @property
    def sigma_BN(self) -> np.ndarray | None:
        return _rec_field(self._rec, "sigma_BN")

    @property
    def omega_B(self) -> np.ndarray | None:
        return _rec_field(self._rec, "omega_BN_B")

    @property
    def r_BN_N(self) -> np.ndarray | None:
        return _rec_field(self._rec, "r_BN_N")

    @property
    def omega_deg(self) -> np.ndarray | None:
        w = self.omega_B
        return None if w is None else np.degrees(w)

    @property
    def omega_mag(self) -> np.ndarray | None:
        w = self.omega_B
        if w is None:
            return None
        w = np.atleast_2d(w)
        return np.linalg.norm(w, axis=1)

    @property
    def omega_mag_deg(self) -> np.ndarray | None:
        m = self.omega_mag
        return None if m is None else np.degrees(m)


class MagLog:
    def __init__(self, rec: Recorder | None) -> None:
        self._rec = rec

    @property
    def t(self) -> np.ndarray | None:
        return _times_s(self._rec)

    @property
    def B_N(self) -> np.ndarray | None:
        return _rec_field(self._rec, "magField_N", "magneticField_N")

    @property
    def B_mag(self) -> np.ndarray | None:
        b = self.B_N
        return None if b is None else np.linalg.norm(b, axis=1)


class RodLog:
    def __init__(
        self,
        tag: str,
        torque_rec: Recorder | None,
        hyst_rec: Recorder | None,
    ) -> None:
        self.tag = tag
        self._torque_rec = torque_rec
        self._hyst_rec = hyst_rec

    @property
    def torque_B(self) -> np.ndarray | None:
        return _rec_field(self._torque_rec, "torqueRequestBody")

    @property
    def H(self) -> np.ndarray | None:
        return _rec_field(self._hyst_rec, "H")

    @property
    def M(self) -> np.ndarray | None:
        return _rec_field(self._hyst_rec, "M")


class PowerLog:
    def __init__(
        self,
        battery_rec: Recorder | None,
        panel_recs: dict[str, Recorder],
        sink_recs: dict[str, Recorder],
        eclipse_rec: Recorder | None,
        battery_capacity_ws: float,
    ) -> None:
        positive("battery capacity", battery_capacity_ws)
        self._battery_rec = battery_rec
        self._panel_recs = panel_recs or {}
        self._sink_recs = sink_recs or {}
        self._eclipse_rec = eclipse_rec
        self._battery_capacity_ws = battery_capacity_ws

    @property
    def t(self) -> np.ndarray | None:
        return _times_s(self._battery_rec)

    @property
    def stored_ws(self) -> np.ndarray | None:
        return _rec_field(self._battery_rec, "storageLevel", "storedCharge")

    @property
    def capacity_ws(self) -> float:
        return self._battery_capacity_ws

    @property
    def soc(self) -> np.ndarray | None:
        stored = self.stored_ws
        if stored is None:
            return None
        return stored / self.capacity_ws

    @staticmethod
    def _align_series(arr: np.ndarray, n: int) -> np.ndarray:
        arr = np.ravel(arr).astype(float, copy=False)
        if len(arr) != n:
            raise ValueError(f"power sample count {len(arr)} does not match {n}")
        return arr

    def _aligned_net_power(self, rec: Recorder, n: int) -> np.ndarray:
        if self.t is None:
            raise ValueError("power nodes require a battery recorder")
        _check_recorder(rec, self.t, "netPower")
        return self._align_series(_rec_field(rec, "netPower"), n)

    def _sum_net_power(
        self, recs: dict[str, Recorder], n: int, *, as_load: bool
    ) -> np.ndarray:
        total = np.zeros(n, dtype=float)
        sign = -1.0 if as_load else 1.0
        for rec in recs.values():
            total += sign * self._aligned_net_power(rec, n)
        return total

    @property
    def panels(self) -> dict[str, np.ndarray]:
        n = len(self.t) if self.t is not None else 0
        return {
            name: self._aligned_net_power(rec, n)
            for name, rec in self._panel_recs.items()
        }

    @property
    def sinks(self) -> dict[str, np.ndarray]:
        n = len(self.t) if self.t is not None else 0
        out: dict[str, np.ndarray] = {}
        for name, rec in self._sink_recs.items():
            raw = self._aligned_net_power(rec, n)
            out[name] = -raw
        return out

    @property
    def generation_w(self) -> np.ndarray | None:
        t = self.t
        if t is None:
            return None
        n = len(t)
        if not self._panel_recs:
            return np.zeros(n, dtype=float)
        return self._sum_net_power(self._panel_recs, n, as_load=False)

    @property
    def consumption_w(self) -> np.ndarray | None:
        t = self.t
        if t is None:
            return None
        n = len(t)
        if not self._sink_recs:
            return np.zeros(n, dtype=float)
        return self._sum_net_power(self._sink_recs, n, as_load=True)

    @property
    def net_w(self) -> np.ndarray | None:
        gen = self.generation_w
        con = self.consumption_w
        if gen is None or con is None:
            return None
        return gen - con

    @property
    def shadow_factor(self) -> np.ndarray | None:
        return _rec_field(self._eclipse_rec, "shadowFactor")

    @property
    def eclipsed(self) -> np.ndarray | None:
        sf = self.shadow_factor
        if sf is None:
            return None
        return sf < 0.5


class SimLog:
    def __init__(self, recorders: SimulationRecorders, battery_capacity_ws: float) -> None:
        self._recorders = recorders
        self._battery_capacity_ws = battery_capacity_ws

    def validate(self) -> None:
        """Validate completed recording before reporting or plotting it."""
        r = self._recorders
        t = self.t
        if not len(t):
            raise ValueError("simulation produced no samples")
        _check_recorder(r.scState, t, "sigma_BN", "omega_BN_B", "r_BN_N")
        _check_recorder(r.environment.mag, t, "magField_N")
        _check_recorder(r.environment.eclipse, t, "shadowFactor")
        _check_recorder(r.power.battery, t, "storageLevel")
        for rec in (*r.power.panels.values(), *r.power.sinks.values()):
            _check_recorder(rec, t, "netPower")
        _check_recorder(r.pmac.pmTorque, t, "torqueRequestBody")
        if r.pmac.rodTorques.keys() != r.pmac.hysteresis.keys():
            raise ValueError("rod torque and hysteresis recorder tags differ")
        for rec in r.pmac.rodTorques.values():
            _check_recorder(rec, t, "torqueRequestBody")
        for rec in r.pmac.hysteresis.values():
            _check_recorder(rec, t, "H", "M")

    @property
    def t(self) -> np.ndarray:
        return _times_s(self._recorders.scState)

    @property
    def attitude(self) -> AttitudeLog:
        return AttitudeLog(self._recorders.scState)

    @property
    def mag(self) -> MagLog:
        return MagLog(self._recorders.environment.mag)

    @property
    def power(self) -> PowerLog:
        r = self._recorders
        return PowerLog(r.power.battery, r.power.panels, r.power.sinks,
                        r.environment.eclipse, self._battery_capacity_ws)

    @property
    def rods(self) -> dict[str, RodLog]:
        r = self._recorders.pmac
        return {tag: RodLog(tag, r.rodTorques[tag], r.hysteresis[tag])
                for tag in sorted(r.rodTorques)}

    @property
    def perm_magnet_torque(self) -> np.ndarray:
        return _rec_field(self._recorders.pmac.pmTorque, "torqueRequestBody")
