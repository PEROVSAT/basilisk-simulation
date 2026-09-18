"""
sim/power.py
Power manager: sums device draw, sums solar generation, tracks battery.
"""

import numpy as np
from Basilisk.architecture import sysModel
from Basilisk.utilities import macros


class PowerManager(sysModel.SysModel):
    """Basilisk task that updates the power system each step."""

    def __init__(self, devices, sim_state, solar_cells,
                 battery_capacity_wh, battery_initial_soc):
        super().__init__()
        self.ModelTag = "PowerManager"
        self.devices = list(devices)
        self.sim_state = sim_state
        self.solar_cells = list(solar_cells)
        self.battery_capacity_wh = battery_capacity_wh
        self.energy_wh = battery_capacity_wh * max(0.0, min(1.0, battery_initial_soc))
        self.soc = self.energy_wh / battery_capacity_wh
        self.is_charging = False
        self.history = []

    def get_total_consumption_w(self):
        return sum(d.get_power() for d in self.devices)

    def get_total_generation_w(self):
        s = self.sim_state
        return sum(c.power_w(s.sun_direction_body, s.shadow_factor,
                             s.sun_distance_factor) for c in self.solar_cells)

    def UpdateState(self, currentSimNanos):
        dt_s = self.sim_state.update(currentSimNanos)
        if dt_s <= 0.0:
            return

        gen_w = self.get_total_generation_w()
        con_w = self.get_total_consumption_w()
        net_w = gen_w - con_w
        self.is_charging = net_w > 0

        energy_change_wh = net_w * dt_s / 3600.0
        self.energy_wh = max(0.0, min(self.battery_capacity_wh,
                                     self.energy_wh + energy_change_wh))
        self.soc = self.energy_wh / self.battery_capacity_wh

        self.history.append({
            'time_s': self.sim_state.sim_time_s,
            'generation_w': gen_w,
            'consumption_w': con_w,
            'net_power_w': net_w,
            'soc': self.soc,
            'energy_wh': self.energy_wh,
            'eclipsed': self.sim_state.shadow_factor < 0.5,
        })

    def print_summary(self):
        print("\n" + "=" * 60)
        print("PEROVSAT POWER SYSTEM STATUS")
        print("=" * 60)
        print(f"Battery SOC: {self.soc * 100:.1f}% "
              f"({self.energy_wh:.2f} Wh / {self.battery_capacity_wh} Wh)")
        print(f"Total Consumption: {self.get_total_consumption_w():.3f} W")
        if self.history:
            gen = [h['generation_w'] for h in self.history]
            ecl = [h['eclipsed'] for h in self.history]
            print(f"Mean Generation: {sum(gen)/len(gen):.3f} W, Peak: {max(gen):.3f} W")
            print(f"Eclipse fraction: {100.0 * sum(ecl) / len(ecl):.1f}%")
        print("\nDevice power breakdown:")
        for d in sorted(self.devices, key=lambda d: d.name):
            p = d.get_power()
            if p > 1e-4:
                print(f"  {d.name}: {p:.4f} W")
        print("=" * 60 + "\n")


def create_power_manager(scSim, devices, sim_state, solar_cells,
                         battery_capacity_wh=100.0, battery_initial_soc=0.8,
                         update_period_s=0.5, task_name="powerTask"):
    pm = PowerManager(devices, sim_state, solar_cells,
                      battery_capacity_wh, battery_initial_soc)
    task = scSim.CreateNewTask(task_name, macros.sec2nano(update_period_s))
    scSim.AddModelToTask(task_name, pm)
    return pm, task