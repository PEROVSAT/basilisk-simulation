"""
model.py
Simulated NSL Electrical Power System.

Core measurement: tracks battery SOC, energy, voltage, and status based on
net power input. Reports the current state so flight software can make
power-aware decisions.
"""

from dataclasses import dataclass
import numpy as np

from . import registers as reg


@dataclass
class EPSReading:
    """One EPS status reading."""
    sim_time_s: float
    soc: float                      # State of charge (0.0-1.0)
    energy_wh: float                # Energy stored [Wh]
    voltage_v: float                # Bus voltage [V]
    current_a: float                # Bus current [A]
    power_w: float                  # Net power [W]
    status: str                     # SAFE, LOW, NOMINAL, HIGH
    charging: bool                  # True if charging, False if discharging
    capacity_wh: float              # Total battery capacity [Wh]

    def __repr__(self):
        return (f"EPSReading(t={self.sim_time_s:.1f}s  "
                f"SOC={self.soc*100:.1f}%  E={self.energy_wh:.2f}Wh  "
                f"V={self.voltage_v:.1f}V  I={self.current_a*1e3:.1f}mA  "
                f"P={self.power_w:+.2f}W  {self.status})")


class SimulatedNSLEPS:
    """
    Simulated NSL Electrical Power System.

    Parameters
    ----------
    capacity_wh : float
        Battery capacity in Watt-hours
    initial_soc : float
        Initial state of charge (0.0-1.0)
    voltage_v : float
        Bus voltage [V]
    max_charge_w : float
        Maximum charge rate [W]
    max_discharge_w : float
        Maximum discharge rate [W]
    """

    def __init__(self,
                 capacity_wh=reg.DEFAULT_CAPACITY_WH,
                 initial_soc=reg.DEFAULT_INITIAL_SOC,
                 voltage_v=reg.DEFAULT_VOLTAGE_V,
                 max_charge_w=reg.DEFAULT_MAX_CHARGE_W,
                 max_discharge_w=reg.DEFAULT_MAX_DISCHARGE_W):
        self.capacity_wh = capacity_wh
        self.energy_wh = capacity_wh * max(0.0, min(1.0, initial_soc))
        self.soc = self.energy_wh / capacity_wh
        self.voltage_v = voltage_v
        self.max_charge_w = max_charge_w
        self.max_discharge_w = max_discharge_w

        self.status = "NOMINAL"
        self.charging = False
        self.last_reading = None
        self.history = []

    def step(self, net_power_w, sim_time_s=0.0):
        """
        Advance the battery state with net power.

        Parameters
        ----------
        net_power_w : float
            Net power into the battery [W]. Positive = charging, negative = discharging.
        sim_time_s : float
            Simulation timestamp [s]

        Returns
        -------
        EPSReading : Current battery status
        """
        self.charging = net_power_w > 0

        # Apply charge/discharge limits
        if net_power_w > 0:
            net_power_w = min(net_power_w, self.max_charge_w)
        else:
            net_power_w = max(net_power_w, -self.max_discharge_w)

        # Update energy
        dt_s = sim_time_s - (self.last_reading.sim_time_s if self.last_reading else 0)
        if dt_s < 0:
            dt_s = 0

        energy_change = net_power_w * dt_s / 3600.0
        self.energy_wh = max(0.0, min(self.capacity_wh, self.energy_wh + energy_change))
        self.soc = self.energy_wh / self.capacity_wh

        # Update status
        self._update_status()

        # Build reading
        reading = EPSReading(
            sim_time_s=sim_time_s,
            soc=self.soc,
            energy_wh=self.energy_wh,
            voltage_v=self.voltage_v,
            current_a=net_power_w / self.voltage_v if self.voltage_v > 0 else 0,
            power_w=net_power_w,
            status=self.status,
            charging=self.charging,
            capacity_wh=self.capacity_wh,
        )
        self.last_reading = reading
        self.history.append(reading)
        return reading

    def step_dt(self, net_power_w, dt_s, sim_time_s=0.0):
        """
        Advance battery state with dt directly (alternate API).

        Parameters
        ----------
        net_power_w : float
            Net power into the battery [W]
        dt_s : float
            Time step [s]
        sim_time_s : float
            Simulation timestamp [s]
        """
        self.charging = net_power_w > 0

        # Apply limits
        if net_power_w > 0:
            net_power_w = min(net_power_w, self.max_charge_w)
        else:
            net_power_w = max(net_power_w, -self.max_discharge_w)

        energy_change = net_power_w * dt_s / 3600.0
        self.energy_wh = max(0.0, min(self.capacity_wh, self.energy_wh + energy_change))
        self.soc = self.energy_wh / self.capacity_wh

        self._update_status()

        reading = EPSReading(
            sim_time_s=sim_time_s,
            soc=self.soc,
            energy_wh=self.energy_wh,
            voltage_v=self.voltage_v,
            current_a=net_power_w / self.voltage_v if self.voltage_v > 0 else 0,
            power_w=net_power_w,
            status=self.status,
            charging=self.charging,
            capacity_wh=self.capacity_wh,
        )
        self.last_reading = reading
        self.history.append(reading)
        return reading

    def _update_status(self):
        """Update operational status based on SOC (PDR Page 11)."""
        if self.soc < reg.SOC_SAFE_MAX:
            self.status = "SAFE"
        elif self.soc < reg.SOC_LOW_MAX:
            self.status = "LOW"
        elif self.soc >= reg.SOC_HIGH_MIN and self.charging:
            self.status = "HIGH"
        else:
            self.status = "NOMINAL"

    def get_soc(self):
        """Get current state of charge (0.0-1.0)."""
        return self.soc

    def get_energy(self):
        """Get current energy stored [Wh]."""
        return self.energy_wh

    def get_capacity(self):
        """Get battery capacity [Wh]."""
        return self.capacity_wh

    def get_voltage(self):
        """Get bus voltage [V]."""
        return self.voltage_v

    def get_status(self):
        """Get current operational status string."""
        return self.status

    def is_charging(self):
        """Return True if battery is charging."""
        return self.charging

    def reset(self, soc=None):
        """Reset battery to a specific SOC or initial SOC."""
        if soc is not None:
            self.soc = max(0.0, min(1.0, soc))
        else:
            self.soc = reg.DEFAULT_INITIAL_SOC
        self.energy_wh = self.soc * self.capacity_wh
        self.history = []
        self.last_reading = None

    def get_history(self):
        """Get full history of readings."""
        return self.history

    def print_summary(self):
        """Print a summary of the current state."""
        if self.last_reading is None:
            print("No readings recorded.")
            return

        print("\n" + "=" * 60)
        print("NSL EPS STATUS")
        print("=" * 60)
        print(f"SOC: {self.soc * 100:.1f}%")
        print(f"Energy: {self.energy_wh:.2f} Wh / {self.capacity_wh} Wh")
        print(f"Voltage: {self.voltage_v:.1f} V")
        print(f"Status: {self.status}")
        print(f"Charging: {'Yes' if self.charging else 'No'}")
        if self.history and len(self.history) > 1:
            avg_power = np.mean([r.power_w for r in self.history])
            print(f"Avg Net Power: {avg_power:+.2f} W")
        print(f"Readings: {len(self.history)} samples")
        print("=" * 60)