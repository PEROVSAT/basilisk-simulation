"""Read-only spacecraft telemetry for Vizard's native storage pane."""

import time

import numpy as np

from Basilisk.architecture import sysModel
from Basilisk.simulation import vizInterface
from Basilisk.utilities import RigidBodyKinematics


FACE_NORMALS = {
    "+X": (1.0, 0.0, 0.0), "-X": (-1.0, 0.0, 0.0),
    "+Y": (0.0, 1.0, 0.0), "-Y": (0.0, -1.0, 0.0),
    "+Z": (0.0, 0.0, 1.0), "-Z": (0.0, 0.0, -1.0),
}


def set_status_panel(viz, spacecraft_name, visible):
    """Set visibility on this viewer without accumulating global GUI settings."""
    settings = vizInterface.InstrumentGuiSettings()
    settings.spacecraftName = spacecraft_name
    settings.showGenericStoragePanel = 1 if visible else -1
    viz.settings.instrumentGuiSettingsList = vizInterface.InstrumentGuiSettingsConfig([settings])


class VizardStatus(sysModel.SysModel):
    """Keep native gauge owners alive and refresh them before frame publication."""

    def __init__(self, battery_message, eclipse_message, timestep_s,
                 panel_messages=(), sink_messages=(), duration_s=1.0,
                 realtime_factor=None, max_lag_s=.1, diagnostics=True,
                 state_message=None, sun_message=None):
        super().__init__()
        self.ModelTag = "vizardStatus"
        self.battery_message = battery_message
        self.eclipse_message = eclipse_message
        self.battery_reader = battery_message.addSubscriber()
        self.eclipse_reader = eclipse_message.addSubscriber()
        if (state_message is None) != (sun_message is None):
            raise ValueError("Face illumination requires both spacecraft and Sun messages")
        self.state_message = state_message
        self.sun_message = sun_message
        self.state_reader = state_message.addSubscriber() if state_message is not None else None
        self.sun_reader = sun_message.addSubscriber() if sun_message is not None else None
        self.panel_messages = tuple(panel_messages)
        self.sink_messages = tuple(sink_messages)
        self.pacer = None
        self.gauges = []
        self.battery = self._gauge("Battery SOC", "% | awaiting data", 100)
        self.battery.color = vizInterface.IntVector(
            [220, 65, 65, 255, 235, 175, 45, 255, 65, 185, 115, 255])
        self.battery.thresholds = vizInterface.IntVector([20, 40])
        self.energy = self._gauge("Stored energy", "Wh", 1)
        self.illumination = self._gauge("Sun visible (eclipse)", "% | awaiting data", 100)
        self.face_illumination = {}
        if state_message is not None:
            self.face_illumination = {
                face: self._gauge(f"Face {face} illumination", "% | awaiting data", 100)
                for face in FACE_NORMALS
            }
        self.generation = self._gauge("Solar generation", "W", 1)
        self.consumption = self._gauge("Electrical load", "W", 1)
        self.balance = self._gauge("Power balance", "W | awaiting data", 1)
        self.sim_time = self._gauge("Simulation elapsed", "s", duration_s)
        self.cadence = self._gauge("Simulation cadence (configured)", "Hz", 1 / timestep_s)
        self.cadence.currentValue = 1 / timestep_s
        self.wall_cadence = None
        self.speed = None
        self.lag = None
        if diagnostics:
            target = realtime_factor or 1.0
            self.wall_cadence = self._gauge("Measured simulation updates", "Hz | warming up",
                                            target / timestep_s)
            self.speed = self._gauge("Achieved simulation speed", "x | warming up", target)
            if realtime_factor is not None:
                self.lag = self._gauge("Pacing lag (previous tick)", "s", max_lag_s)
        self.realtime_factor = realtime_factor
        self.max_lag_s = max_lag_s
        self.battery_state = "awaiting data"
        self.illumination_state = "awaiting data"
        self.Reset(0)

    def _gauge(self, label, units, maximum):
        gauge = vizInterface.GenericStorage()
        gauge.label = label
        gauge.units = units
        gauge.maxValue = maximum
        self.gauges.append(gauge)
        return gauge

    @staticmethod
    def _value(gauge, value):
        gauge.currentValue = value
        gauge.maxValue = max(gauge.maxValue, value)

    def Reset(self, current_time):
        self._window_wall = None
        self._window_sim = None
        self._window_ticks = 0
        if self.wall_cadence is not None:
            self.wall_cadence.currentValue = 0
            self.wall_cadence.units = "Hz | warming up"
            self.speed.currentValue = 0
            self.speed.units = "x | warming up"

    def UpdateState(self, current_time):
        simulation_s = current_time * 1e-9
        self.sim_time.currentValue = simulation_s
        if self.battery_reader.isWritten():
            battery = self.battery_message.read()
            capacity = battery.storageCapacity
            if capacity > 0:
                soc = min(1.0, max(0.0, battery.storageLevel / capacity))
                net = battery.currentNetPower
                if soc <= 1e-9 and net <= 1e-6:
                    self.battery_state = "Depleted"
                elif soc >= 1 - 1e-9 and net >= -1e-6:
                    self.battery_state = "Full"
                elif net > 1e-6:
                    self.battery_state = "Charging"
                elif net < -1e-6:
                    self.battery_state = "Discharging"
                else:
                    self.battery_state = "Idle"
                warning = " | LOW" if soc <= .2 else ""
                self.battery.currentValue = soc * 100
                self.battery.units = f"% | {self.battery_state}{warning}"
                self.energy.currentValue = battery.storageLevel / 3600
                self.energy.maxValue = capacity / 3600
                self._value(self.balance, abs(net))
                direction = "surplus" if net > 1e-6 else "deficit" if net < -1e-6 else "balanced"
                self.balance.units = f"W | {direction}"
        if self.eclipse_reader.isWritten():
            eclipse = self.eclipse_message.read()
            illumination = (eclipse.illuminationFactor if hasattr(eclipse, "illuminationFactor")
                            else eclipse.shadowFactor)
            self.illumination.currentValue = 100 * min(1.0, max(0.0, illumination))
            self.illumination_state = ("Eclipse" if illumination <= 1e-9 else
                                       "Sunlight" if illumination >= 1 - 1e-9 else "Partial eclipse")
            self.illumination.units = f"% | {self.illumination_state}"
            self._update_faces(illumination)
        self._value(self.generation, sum(message.read().netPower for message in self.panel_messages))
        self._value(self.consumption, -sum(message.read().netPower for message in self.sink_messages))
        self._update_timing(simulation_s)

    def _update_faces(self, illumination):
        if not self.face_illumination:
            return
        if not self.state_reader.isWritten() or not self.sun_reader.isWritten():
            return
        state = self.state_message.read()
        sun = self.sun_message.read()
        to_sun = np.asarray(sun.PositionVector) - np.asarray(state.r_BN_N)
        distance = np.linalg.norm(to_sun)
        if not np.isfinite(distance) or distance <= 0:
            for gauge in self.face_illumination.values():
                gauge.currentValue = 0
                gauge.units = "% | unavailable"
            return
        sun_body = RigidBodyKinematics.MRP2C(state.sigma_BN) @ (to_sun / distance)
        visibility = min(1.0, max(0.0, illumination))
        for face, normal in FACE_NORMALS.items():
            incidence = min(1.0, max(0.0, float(np.dot(normal, sun_body))))
            gauge = self.face_illumination[face]
            gauge.currentValue = 100 * visibility * incidence
            state_text = ("Eclipse" if visibility <= 1e-9 else
                          "Facing away / edge-on" if incidence <= 1e-9 else "Sunlit")
            gauge.units = f"% | {state_text}"

    def _update_timing(self, simulation_s):
        if self.wall_cadence is None:
            return
        now = time.perf_counter()
        if self._window_wall is None:
            self._window_wall = now
            self._window_sim = simulation_s
        else:
            self._window_ticks += 1
            elapsed = now - self._window_wall
            if elapsed >= 1.0:
                self._value(self.wall_cadence, self._window_ticks / elapsed)
                self.wall_cadence.units = "Hz"
                self._value(self.speed, (simulation_s - self._window_sim) / elapsed)
                self.speed.units = "x"
                self._window_wall = now
                self._window_sim = simulation_s
                self._window_ticks = 0
        if self.lag is not None and self.pacer is not None:
            lag = max(0.0, self.pacer.elapsed_s - self.pacer.simulation_s / self.realtime_factor)
            self._value(self.lag, lag)
            self.lag.units = "s | LATE" if lag > self.max_lag_s else "s | on time"
