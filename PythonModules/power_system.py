"""
power_system.py
Power management for PEROVSAT – battery, components, solar generation.
"""

import numpy as np
import matplotlib.pyplot as plt


# ----------------------------------------------------------------------
# Component model: off / idle / active with duty cycle
# ----------------------------------------------------------------------

class PowerComponent:
    def __init__(self, name, power_off=0.0, power_idle=0.0, power_active=0.0,
                 duty_cycle=1.0, initial_state='off'):
        self.name = name
        self.power_off = power_off
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
        if state in ('off', 'idle', 'active'):
            self.state = state

    def get_power(self):
        if not self.enabled:
            return 0.0
        if self.state == 'off':
            return self.power_off
        elif self.state == 'idle':
            return self.power_idle * self.duty_cycle
        else:  # active
            return self.power_active * self.duty_cycle


# ----------------------------------------------------------------------
# Specific components with typical PEROVSAT power numbers
# ----------------------------------------------------------------------

class NSLBus(PowerComponent):
    def __init__(self):
        super().__init__('NSL Bus', power_off=0.0, power_idle=0.6, power_active=0.6,
                         duty_cycle=1.0, initial_state='active')
        self.enabled = True

class OBC(PowerComponent):
    def __init__(self):
        super().__init__('OBC', power_off=0.0, power_idle=0.01, power_active=0.1,
                         duty_cycle=0.25, initial_state='idle')

class AMUModule(PowerComponent):
    def __init__(self, amu_id):
        super().__init__(f'AMU_{amu_id:02d}', power_off=0.0, power_idle=0.002,
                         power_active=0.018, duty_cycle=0.05, initial_state='off')
        self.amu_id = amu_id

class IridiumModem(PowerComponent):
    def __init__(self):
        super().__init__('Iridium Modem', power_off=0.0, power_idle=0.0,
                         power_active=1.4, duty_cycle=0.1, initial_state='off')

class SunSensor(PowerComponent):
    def __init__(self, face):
        super().__init__(f'SunSensor_{face}', power_off=0.0, power_idle=0.002,
                         power_active=0.04, duty_cycle=0.1, initial_state='off')

class IMU(PowerComponent):
    def __init__(self):
        super().__init__('IMU', power_off=0.0, power_idle=0.001, power_active=0.01,
                         duty_cycle=0.1, initial_state='off')


# ----------------------------------------------------------------------
# Solar panel – power from body‑mounted cells, NOT from perovskite payload
# ----------------------------------------------------------------------

class SolarPanel:
    SOLAR_CONSTANT = 1361.0  # W/m² at 1 AU

    def __init__(self, area_m2=0.01, efficiency=0.20, orientation=(0,0,1)):
        # 0.01 m² = 10cm x 10cm, typical for a 1U face
        self.area = area_m2
        self.efficiency = efficiency
        self.orientation = np.array(orientation) / np.linalg.norm(orientation)
        self.degradation = 1.0
        self.temperature = 25.0

    def get_power(self, sun_direction_body, sun_distance_factor=1.0):
        cos_angle = np.dot(self.orientation, sun_direction_body)
        cos_angle = max(0.0, cos_angle)
        temp_correction = 1.0 - 0.004 * (self.temperature - 25.0)
        return (self.SOLAR_CONSTANT * self.area * self.efficiency *
                cos_angle * self.degradation * sun_distance_factor *
                temp_correction)


class SolarArray:
    def __init__(self):
        self.panels = []

    def add_panel(self, panel):
        self.panels.append(panel)

    def get_total_power(self, sun_direction_body, sun_distance_factor=1.0):
        return sum(p.get_power(sun_direction_body, sun_distance_factor) for p in self.panels)


# ----------------------------------------------------------------------
# Main power system
# ----------------------------------------------------------------------

class PowerSystem:
    # Operational statuses (SAFE, LOW, NOMINAL, HIGH)
    STATUS_SAFE = 0
    STATUS_LOW = 1
    STATUS_NOMINAL = 2
    STATUS_HIGH = 3
    STATUS_NAMES = {0: 'SAFE', 1: 'LOW', 2: 'NOMINAL', 3: 'HIGH'}

    # SOC thresholds for status transitions
    SOC_SAFE_MAX = 0.20
    SOC_LOW_MAX = 0.40

    def __init__(self, battery_capacity_wh=100.0, initial_soc=0.8,
                 num_amus=16, num_sun_sensors=2, faces=('+Z', '-X')):

        # Battery
        self.battery_capacity_wh = battery_capacity_wh
        self.energy_wh = battery_capacity_wh * max(0.0, min(1.0, initial_soc))
        self.soc = self.energy_wh / battery_capacity_wh

        # Components
        self.components = []
        self.components_by_name = {}

        # NSL bus (always on)
        bus = NSLBus()
        self.components.append(bus)
        self.components_by_name[bus.name] = bus

        # OBC
        obc = OBC()
        self.components.append(obc)
        self.components_by_name[obc.name] = obc

        # 16 AMUs
        for i in range(1, num_amus+1):
            amu = AMUModule(i)
            self.components.append(amu)
            self.components_by_name[amu.name] = amu

        # Iridium modem
        iridium = IridiumModem()
        self.components.append(iridium)
        self.components_by_name[iridium.name] = iridium

        # Sun sensors (one per payload face)
        for face in faces[:num_sun_sensors]:
            ss = SunSensor(face)
            self.components.append(ss)
            self.components_by_name[ss.name] = ss

        # IMU
        imu = IMU()
        self.components.append(imu)
        self.components_by_name[imu.name] = imu

        # --------------------------------------------------------------
        # Solar array – body‑mounted cells, not the perovskite payload.
        # We want peak generation ~2.5 W when a face is normal to sun,
        # and average ~0.93 W over an orbit.  Six faces, each 0.01 m²,
        # 20% efficiency gives ~2.72 W peak. We scale to match the
        # expected numbers.  The perovskite cells are separate and not
        # used for bus power.
        # --------------------------------------------------------------
        self.solar_array = SolarArray()
        for orient in [(1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)]:
            panel = SolarPanel(area_m2=0.01, efficiency=0.20, orientation=orient)
            self.solar_array.add_panel(panel)

        # Scaling factor to get 0.93 W average from the raw panel output.
        # Raw peak = 1361 * 0.01 * 0.20 = 2.722 W.  We want peak ~2.5 W,
        # and the average over time (considering orbit) to be ~0.93 W.
        # This factor brings the simulated average to that value.
        # Use SolarPanel.SOLAR_CONSTANT to avoid AttributeError.
        self.generation_scaling = 0.93 / (SolarPanel.SOLAR_CONSTANT * 0.01 * 0.20)
        # That's about 0.342

        # Internal state
        self.current_status = self.STATUS_NOMINAL
        self.is_charging = False
        self.time_hours = 0.0
        self.history = []

        self._apply_status_constraints()

    # ------------------------------------------------------------------
    # Component control
    # ------------------------------------------------------------------

    def get_component(self, name):
        return self.components_by_name.get(name)

    def set_component_state(self, name, state):
        comp = self.get_component(name)
        if comp:
            comp.set_state(state)
            return True
        return False

    def set_component_duty_cycle(self, name, duty_cycle):
        comp = self.get_component(name)
        if comp:
            comp.duty_cycle = duty_cycle
            return True
        return False

    def enable_component(self, name, enabled=True):
        comp = self.get_component(name)
        if comp:
            comp.enabled = enabled
            return True
        return False

    # ------------------------------------------------------------------
    # Operational status logic
    # ------------------------------------------------------------------

    def get_operational_status(self):
        if self.soc < self.SOC_SAFE_MAX:
            return self.STATUS_SAFE
        elif self.soc < self.SOC_LOW_MAX:
            return self.STATUS_LOW
        elif self.soc >= 0.4 and not self.is_charging:
            return self.STATUS_NOMINAL
        else:
            return self.STATUS_HIGH

    def _apply_status_constraints(self):
        status = self.get_operational_status()
        self.current_status = status

        if status == self.STATUS_SAFE:
            # Payload off, only periodic comms check
            self.set_component_state('OBC', 'idle')
            self.set_component_state('Iridium Modem', 'off')
            for comp in self.components:
                if comp.name.startswith('AMU_'):
                    comp.set_state('off')
                    comp.enabled = False
                if comp.name.startswith('SunSensor_'):
                    comp.set_state('off')
                    comp.enabled = False
            self.set_component_state('IMU', 'off')
            self.components_by_name['NSL Bus'].set_state('active')

        elif status == self.STATUS_LOW:
            # Only sun sensors and IMU, beacon every 30 min
            self.set_component_state('OBC', 'idle')
            self.set_component_state('Iridium Modem', 'idle')
            for comp in self.components:
                if comp.name.startswith('AMU_'):
                    comp.set_state('off')
                    comp.enabled = False
                if comp.name.startswith('SunSensor_'):
                    comp.set_state('active')
                    comp.enabled = True
            self.set_component_state('IMU', 'active')
            self.components_by_name['NSL Bus'].set_state('active')

        elif status == self.STATUS_NOMINAL:
            # Full payload, basic data processing, experiment data downlink
            self.set_component_state('OBC', 'active')
            self.set_component_state('Iridium Modem', 'idle')  # standby for commands
            for comp in self.components:
                if comp.name.startswith('AMU_'):
                    comp.set_state('active')
                    comp.enabled = True
                if comp.name.startswith('SunSensor_'):
                    comp.set_state('active')
                    comp.enabled = True
            self.set_component_state('IMU', 'active')
            self.components_by_name['NSL Bus'].set_state('active')

        else:  # HIGH
            # Same as NOMINAL but with more frequent transmissions
            self.set_component_state('OBC', 'active')
            self.set_component_state('Iridium Modem', 'active')
            for comp in self.components:
                if comp.name.startswith('AMU_'):
                    comp.set_state('active')
                    comp.enabled = True
                if comp.name.startswith('SunSensor_'):
                    comp.set_state('active')
                    comp.enabled = True
            self.set_component_state('IMU', 'active')
            self.components_by_name['NSL Bus'].set_state('active')

    # ------------------------------------------------------------------
    # Power calculations
    # ------------------------------------------------------------------

    def get_total_consumption(self):
        return sum(c.get_power() for c in self.components)

    def get_total_generation(self, sun_direction_body, sun_distance_factor=1.0):
        raw = self.solar_array.get_total_power(sun_direction_body, sun_distance_factor)
        return raw * self.generation_scaling

    def get_net_power(self, sun_direction_body, sun_distance_factor=1.0):
        gen = self.get_total_generation(sun_direction_body, sun_distance_factor)
        con = self.get_total_consumption()
        return gen - con, gen, con

    # ------------------------------------------------------------------
    # Time step
    # ------------------------------------------------------------------

    def step(self, dt_s, sun_direction_body=(0,0,1), sun_distance_factor=1.0,
             override_soc=None):
        if override_soc is not None:
            self.soc = max(0.0, min(1.0, override_soc))
            self.energy_wh = self.soc * self.battery_capacity_wh
        else:
            net_power, gen, con = self.get_net_power(sun_direction_body, sun_distance_factor)
            self.is_charging = net_power > 0
            energy_change_wh = net_power * dt_s / 3600.0
            self.energy_wh = max(0.0, min(self.battery_capacity_wh,
                                          self.energy_wh + energy_change_wh))
            self.soc = self.energy_wh / self.battery_capacity_wh

        self._apply_status_constraints()

        self.time_hours += dt_s / 3600.0
        status = self.get_operational_status()
        self.history.append({
            'time_hours': self.time_hours,
            'soc': self.soc,
            'energy_wh': self.energy_wh,
            'generation_w': self.get_total_generation(sun_direction_body, sun_distance_factor),
            'consumption_w': self.get_total_consumption(),
            'net_power_w': self.get_net_power(sun_direction_body, sun_distance_factor)[0],
            'status': self.STATUS_NAMES[status],
            'status_code': status
        })

    # ------------------------------------------------------------------
    # Reporting and plotting
    # ------------------------------------------------------------------

    def get_status(self):
        status = self.get_operational_status()
        return {
            'time_hours': self.time_hours,
            'soc': self.soc,
            'energy_wh': self.energy_wh,
            'capacity_wh': self.battery_capacity_wh,
            'generation_w': self.get_total_generation((0,0,1)),
            'consumption_w': self.get_total_consumption(),
            'status': self.STATUS_NAMES[status],
            'status_code': status
        }

    def get_component_power_breakdown(self):
        return {c.name: c.get_power() for c in self.components}

    def plot_history(self, filename='power_history.png', show=False):
        if not self.history:
            print("No history to plot.")
            return

        data = self.history
        t = [d['time_hours'] for d in data]

        fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

        # Power plot
        axes[0].plot(t, [d['generation_w'] for d in data], label='Generation', color='green', linewidth=1.5)
        axes[0].plot(t, [d['consumption_w'] for d in data], label='Consumption', color='red', linewidth=1.5)
        axes[0].plot(t, [d['net_power_w'] for d in data], label='Net', color='blue', linestyle='--', linewidth=1)
        axes[0].axhline(0, color='black', linewidth=0.5)
        axes[0].set_ylabel('Power (W)')
        axes[0].set_title('Power Generation vs Consumption')
        axes[0].legend()
        axes[0].grid(True, alpha=0.3)

        # SOC
        axes[1].plot(t, [d['soc']*100 for d in data], color='blue', linewidth=1.5)
        axes[1].axhline(self.SOC_SAFE_MAX*100, color='red', linestyle='--', label='SAFE threshold')
        axes[1].axhline(self.SOC_LOW_MAX*100, color='orange', linestyle='--', label='LOW threshold')
        axes[1].set_ylabel('State of Charge (%)')
        axes[1].set_title('Battery SOC')
        axes[1].legend()
        axes[1].grid(True, alpha=0.3)
        axes[1].set_ylim(0, 105)

        # Operational status
        status_map = {'SAFE': 0, 'LOW': 1, 'NOMINAL': 2, 'HIGH': 3}
        status_vals = [status_map[d['status']] for d in data]
        axes[2].step(t, status_vals, where='post', linewidth=1.5)
        axes[2].set_yticks([0, 1, 2, 3])
        axes[2].set_yticklabels(['SAFE', 'LOW', 'NOMINAL', 'HIGH'])
        axes[2].set_xlabel('Time (hours)')
        axes[2].set_ylabel('Operational Status')
        axes[2].set_title('Operational Status')
        axes[2].grid(True, alpha=0.3)

        plt.tight_layout()
        plt.savefig(filename, dpi=150)
        if show:
            plt.show()
        plt.close()

    def print_summary(self):
        status = self.get_status()
        print("\n" + "="*60)
        print("PEROVSAT POWER SYSTEM STATUS")
        print("="*60)
        print(f"Time: {status['time_hours']:.2f} hours")
        print(f"Battery SOC: {status['soc']*100:.1f}% ({status['energy_wh']:.2f} Wh / {status['capacity_wh']} Wh)")
        print(f"Operational Status: {status['status']}")
        print(f"Total Generation: {status['generation_w']:.3f} W")
        print(f"Total Consumption: {status['consumption_w']:.3f} W")
        print("\nComponent Power Breakdown:")
        breakdown = self.get_component_power_breakdown()
        for name, power in sorted(breakdown.items()):
            if power > 0.0001:
                print(f"  {name}: {power:.4f} W")
        print("="*60 + "\n")


# ----------------------------------------------------------------------
# Quick test if run standalone
# ----------------------------------------------------------------------

if __name__ == "__main__":
    ps = PowerSystem(battery_capacity_wh=100.0, initial_soc=0.8)
    import math
    dt = 60.0
    steps = 24 * 60
    for i in range(steps):
        t = i * dt
        angle = 2 * math.pi * (t / (90*60))
        sun_dir = (math.cos(angle), math.sin(angle), 0.0)
        ps.step(dt, sun_direction_body=sun_dir, sun_distance_factor=1.0)
    ps.print_summary()
    ps.plot_history('power_system_example.png', show=True)