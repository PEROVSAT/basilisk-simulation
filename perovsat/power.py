"""Basilisk power graph: panels, catalog sinks, battery.

Sink ``nodePowerOut`` is negative watts (consumption). Battery storage is
W·s (Joules): Wh × 3600. Panels need spacecraft state, sun ephemeris, and
eclipse illumination — attach this after ``setup_environment``.
"""

from __future__ import annotations

from dataclasses import dataclass

from Basilisk.simulation import simpleBattery, simplePowerSink, simpleSolarPanel

from perovsat import config
from perovsat._bsk import attach_recorder


@dataclass
class PowerStack:
    battery: object
    panels: dict
    sinks: dict
    recorders: dict
    capacity_ws: float


def setup_power(
    scSim,
    task_name,
    sc_state_msg,
    sun_state_msg,
    eclipse_out_msg,
    record_period_ns,
    soc=None,
) -> PowerStack:
    if soc is None:
        soc = config.BATTERY_INITIAL_SOC
    soc = max(0.0, min(1.0, soc))
    capacity_ws = config.BATTERY_CAPACITY_WH * 3600.0

    panels = {}
    panel_recs = {}
    for name, spec in config.PANELS.items():
        panel = simpleSolarPanel.SimpleSolarPanel()
        panel.ModelTag = f"SolarPanel_{name}"
        panel.setPanelParameters(list(spec.n_hat), spec.area_m2, spec.efficiency)
        panel.stateInMsg.subscribeTo(sc_state_msg)
        panel.sunInMsg.subscribeTo(sun_state_msg)
        panel.sunEclipseInMsg.subscribeTo(eclipse_out_msg)
        scSim.AddModelToTask(task_name, panel)
        panel_recs[name] = attach_recorder(
            scSim, task_name, panel.nodePowerOutMsg, record_period_ns
        )
        panels[name] = panel

    sinks = {}
    sink_recs = {}
    for device in config.DEVICES:
        sink = simplePowerSink.SimplePowerSink()
        sink.ModelTag = f"Sink_{device.name}"
        sink.nodePowerOut = -device.average_power_w
        scSim.AddModelToTask(task_name, sink)
        sink_recs[device.name] = attach_recorder(
            scSim, task_name, sink.nodePowerOutMsg, record_period_ns
        )
        sinks[device.name] = sink

    battery = simpleBattery.SimpleBattery()
    battery.ModelTag = "Battery"
    battery.storageCapacity = capacity_ws
    battery.storedCharge_Init = capacity_ws * soc
    for panel in panels.values():
        battery.addPowerNodeToModel(panel.nodePowerOutMsg)
    for sink in sinks.values():
        battery.addPowerNodeToModel(sink.nodePowerOutMsg)
    scSim.AddModelToTask(task_name, battery)

    return PowerStack(
        battery=battery,
        panels=panels,
        sinks=sinks,
        recorders={
            "battery": attach_recorder(
                scSim, task_name, battery.batPowerOutMsg, record_period_ns
            ),
            "panels": panel_recs,
            "sinks": sink_recs,
        },
        capacity_ws=capacity_ws,
    )
