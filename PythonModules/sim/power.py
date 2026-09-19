"""Basilisk native power stack for PEROVSAT (panels, sinks, battery)."""

from __future__ import annotations

from dataclasses import dataclass

from Basilisk.simulation import simpleBattery, simplePowerSink, simpleSolarPanel

from devices.catalog import iter_sink_watts

_PANEL_NORMALS: dict[str, list[float]] = {
    "+X": [1.0, 0.0, 0.0],
    "+Y": [0.0, 1.0, 0.0],
    "-Y": [0.0, -1.0, 0.0],
}
_PANEL_AREA_M2 = 0.008
_PANEL_EFFICIENCY = 0.23
_BATTERY_CAPACITY_WH = 100.0


@dataclass
class PowerStack:
    battery: object
    panels: dict[str, object]
    sinks: dict[str, object]
    recorders: dict
    capacity_ws: float


def setup_power(
    scSim,
    task_name,
    sc_state_msg,
    sun_state_msg,
    eclipse_out_msg,
    record_period_ns,
    soc=0.8,
) -> PowerStack:
    """Wire catalog-average sinks and attitude/eclipse-coupled ``simpleSolarPanel`` generation."""
    soc = max(0.0, min(1.0, soc))
    capacity_ws = _BATTERY_CAPACITY_WH * 3600.0

    panels: dict[str, object] = {}
    panel_recs: dict[str, object] = {}
    for name, n_hat in _PANEL_NORMALS.items():
        panel = simpleSolarPanel.SimpleSolarPanel()
        panel.ModelTag = f"SolarPanel_{name}"
        panel.setPanelParameters(n_hat, _PANEL_AREA_M2, _PANEL_EFFICIENCY)
        panel.stateInMsg.subscribeTo(sc_state_msg)
        panel.sunInMsg.subscribeTo(sun_state_msg)
        panel.sunEclipseInMsg.subscribeTo(eclipse_out_msg)
        scSim.AddModelToTask(task_name, panel)
        panel_recs[name] = _attach_recorder(
            scSim, task_name, panel.nodePowerOutMsg, record_period_ns
        )
        panels[name] = panel

    sinks: dict[str, object] = {}
    sink_recs: dict[str, object] = {}
    for sink_name, average_w in iter_sink_watts():
        sink = simplePowerSink.SimplePowerSink()
        sink.ModelTag = f"Sink_{sink_name}"
        sink.nodePowerOut = -average_w
        scSim.AddModelToTask(task_name, sink)
        sink_recs[sink_name] = _attach_recorder(
            scSim, task_name, sink.nodePowerOutMsg, record_period_ns
        )
        sinks[sink_name] = sink

    battery = simpleBattery.SimpleBattery()
    battery.ModelTag = "Battery"
    battery.storageCapacity = capacity_ws
    battery.storedCharge_Init = capacity_ws * soc
    for panel in panels.values():
        battery.addPowerNodeToModel(panel.nodePowerOutMsg)
    for sink in sinks.values():
        battery.addPowerNodeToModel(sink.nodePowerOutMsg)
    scSim.AddModelToTask(task_name, battery)
    battery_rec = _attach_recorder(
        scSim, task_name, battery.batPowerOutMsg, record_period_ns
    )

    recorders = {
        "battery": battery_rec,
        "panels": panel_recs,
        "sinks": sink_recs,
    }
    return PowerStack(
        battery=battery,
        panels=panels,
        sinks=sinks,
        recorders=recorders,
        capacity_ws=capacity_ws,
    )


def _attach_recorder(scSim, task_name, msg, period_ns):
    rec = msg.recorder(period_ns)
    scSim.AddModelToTask(task_name, rec)
    return rec
