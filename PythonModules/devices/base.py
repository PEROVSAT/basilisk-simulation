"""
devices/base.py
Abstract base for all simulated spacecraft devices (bus components, payload
instruments, etc). A SimulatedDevice knows its own power draw and how to
react to a command message -- the latter is the hook that will eventually
back the SITL (software-in-the-loop) command interface.
"""

from abc import ABC, abstractmethod


class SimulatedDevice(ABC):
    """
    Common interface + power bookkeeping for every simulated device.

    Power model: off / idle / active, each with its own draw [W], gated by a
    duty cycle in [0, 1] representing how much of "active" time is actually
    spent drawing active-level power (matches the PowerComponent model this
    replaces in the old power_system.py).
    """

    def __init__(self, name, power_idle=0.0, power_active=0.0,
                 duty_cycle=1.0, initial_state='off'):
        self.name = name
        self.power_idle = power_idle
        self.power_active = power_active
        self._duty_cycle = max(0.0, min(1.0, duty_cycle))
        self.state = initial_state
        self.enabled = True

    @property
    def duty_cycle(self):
        return self._duty_cycle

    @duty_cycle.setter
    def duty_cycle(self, value):
        self._duty_cycle = max(0.0, min(1.0, value))

    def set_state(self, state):
        if state not in ('off', 'idle', 'active'):
            raise ValueError(f"Unknown device state '{state}'")
        self.state = state

    def get_power(self):
        """Instantaneous power draw [W] given the device's current state and
        duty cycle. Called every power-management step -- devices never need
        to know about Basilisk to answer this."""
        if not self.enabled or self.state == 'off':
            return 0.0
        if self.state == 'idle':
            return self.power_idle * self.duty_cycle
        return self.power_active * self.duty_cycle

    @abstractmethod
    def onMessage(self, message, simulation):
        """
        Handle an incoming command/message. This is the SITL hook: FSW (real
        or simulated) sends a device a command, the device acts on it and
        updates its own state/power draw accordingly.

        message    : device-specific command payload -- convention used here
                     is a dict with at least a 'command' key, but a subclass
                     is free to define its own.
        simulation : the shared SimulationState for the current timestep,
                     giving the device read-only access to live sim context
                     (e.g. sun_direction_body for an AMU's sun angle) without
                     coupling the device to Basilisk message types directly.

        Returns whatever response makes sense for that device (or None).
        """
        raise NotImplementedError
