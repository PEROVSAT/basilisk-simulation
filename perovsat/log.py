"""Experiment-facing time series from Basilisk recorders (no Basilisk imports)."""

from __future__ import annotations

from typing import Any

import numpy as np

Recorder = Any


def _as_array(x) -> np.ndarray:
    return np.asarray(x)


def _times_s(rec: Recorder | None) -> np.ndarray | None:
    if rec is None:
        return None
    try:
        return _as_array(rec.times()) * 1e-9
    except AttributeError:
        return None


def _rec_field(rec: Recorder | None, *names: str) -> np.ndarray | None:
    if rec is None:
        return None
    for name in names:
        try:
            return _as_array(getattr(rec, name))
        except AttributeError:
            continue
    return None


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
        cap = _rec_field(self._battery_rec, "storageCapacity")
        if cap is not None and len(cap) > 0:
            last = float(cap[-1])
            if last > 0:
                return last
        return self._battery_capacity_ws

    @property
    def soc(self) -> np.ndarray | None:
        stored = self.stored_ws
        if stored is None:
            return None
        return stored / self.capacity_ws

    @staticmethod
    def _align_series(arr: np.ndarray, n: int) -> np.ndarray:
        if n <= 0:
            return np.zeros(0, dtype=float)
        arr = np.ravel(arr).astype(float, copy=False)
        if len(arr) == n:
            return arr
        out = np.zeros(n, dtype=float)
        m = min(n, len(arr))
        out[:m] = arr[:m]
        return out

    def _aligned_net_power(self, rec: Recorder | None, n: int) -> np.ndarray:
        if n <= 0:
            return np.zeros(0, dtype=float)
        arr = _rec_field(rec, "netPower")
        if arr is None or len(arr) == 0:
            return np.zeros(n, dtype=float)
        return self._align_series(arr, n)

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
        direct = _rec_field(self._battery_rec, "currentNetPower")
        if direct is not None:
            n = len(self.t) if self.t is not None else len(np.ravel(direct))
            return self._align_series(direct, n)
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
    def __init__(self, recorders: dict, battery_capacity_ws: float) -> None:
        if recorders.get("scState") is None:
            raise ValueError("recorders['scState'] is required")
        self._recorders = recorders
        self._battery_capacity_ws = battery_capacity_ws

    @property
    def t(self) -> np.ndarray:
        times = _times_s(self._recorders["scState"])
        if times is None:
            raise ValueError("recorders['scState'] has no times()")
        return times

    @property
    def attitude(self) -> AttitudeLog:
        return AttitudeLog(self._recorders["scState"])

    @property
    def mag(self) -> MagLog:
        return MagLog(self._recorders.get("mag"))

    @property
    def power(self) -> PowerLog:
        return PowerLog(
            self._recorders.get("battery"),
            self._recorders.get("panels") or {},
            self._recorders.get("sinks") or {},
            self._recorders.get("eclipse"),
            self._battery_capacity_ws,
        )

    @property
    def rods(self) -> dict[str, RodLog]:
        torques: dict[str, Recorder] = self._recorders.get("rodTorques") or {}
        hyst: dict[str, Recorder] = self._recorders.get("hysteresis") or {}
        tags = set(torques) | set(hyst)
        return {
            tag: RodLog(tag, torques.get(tag), hyst.get(tag))
            for tag in sorted(tags)
        }

    @property
    def perm_magnet_torque(self) -> np.ndarray | None:
        return _rec_field(self._recorders.get("pmTorque"), "torqueRequestBody")
