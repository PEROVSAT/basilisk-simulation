"""
devices/bus_components.py
Simple always-on / periodic bus components that don't (yet) have any
commands worth modeling -- they just draw power in a fixed off/idle/active
pattern. onMessage is a no-op placeholder until these get real commands;
when they do, give each its own file (the way SimulatedAMU has amu.py) and
break each command into a private _cmd_* method there, same convention as
SimulatedAMU.
"""

from devices.base import SimulatedDevice


class NSLBus(SimulatedDevice):
    def __init__(self):
        super().__init__('NSL Bus', power_idle=0.6, power_active=0.6,
                         duty_cycle=1.0, initial_state='active')

    def onMessage(self, message, simulation):
        return None


class OBC(SimulatedDevice):
    def __init__(self):
        super().__init__('OBC', power_idle=0.01, power_active=0.1,
                         duty_cycle=0.25, initial_state='idle')

    def onMessage(self, message, simulation):
        return None


class IridiumModem(SimulatedDevice):
    def __init__(self):
        super().__init__('Iridium Modem', power_idle=0.0, power_active=1.4,
                         duty_cycle=0.1, initial_state='off')

    def onMessage(self, message, simulation):
        return None


class SunSensor(SimulatedDevice):
    def __init__(self, face):
        super().__init__(f'SunSensor_{face}', power_idle=0.002, power_active=0.04,
                         duty_cycle=0.1, initial_state='off')
        self.face = face

    def onMessage(self, message, simulation):
        return None


class IMU(SimulatedDevice):
    def __init__(self):
        super().__init__('IMU', power_idle=0.001, power_active=0.01,
                         duty_cycle=0.1, initial_state='off')

    def onMessage(self, message, simulation):
        return None
