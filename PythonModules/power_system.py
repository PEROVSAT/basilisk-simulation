"""
power_system.py
Power management for PEROVSAT - battery, components, solar generation.

Solar generation is a physical model: irradiance x cell area x efficiency x
cosine-of-incidence x eclipse-shadow-factor x (1 AU / r_sun)^2. No empirical
scaling factor - the orbit-average generation emerges from the real attitude
and eclipse geometry supplied by the caller (see sims/base.py). The eclipse
calculation (conical umbra + penumbra) lives here in eclipse_shadow_factor().
"""

import numpy as np
import matplotlib.pyplot as plt


# ----------------------------------------------------------------------
# Physical constants (SI, metres - Basilisk state/SPICE positions are in m)
# ----------------------------------------------------------------------

R_EARTH_M = 6.378137e6      # Earth mean equatorial radius [m]
R_SUN_M   = 6.9634e8        # Sun radius [m]
AU_M      = 1.495978707e11  # 1 astronomical unit [m]


# ----------------------------------------------------------------------
# Eclipse geometry - the "specific calculation"
# ----------------------------------------------------------------------

def _circle_overlap_area(r, R, d):
    """Area of intersection of two circles of radii r, R whose centres are a
    distance d apart. Used for the penumbra (partial solar-disk occultation)."""
    if d >= r + R:                 # disjoint
        return 0.0
    if d <= abs(R - r):            # one disk fully inside the other
        return np.pi * min(r, R) ** 2
    r2, R2, d2 = r * r, R * R, d * d
    a1 = r2 * np.arccos(np.clip((d2 + r2 - R2) / (2 * d * r), -1.0, 1.0))
    a2 = R2 * np.arccos(np.clip((d2 + R2 - r2) / (2 * d * R), -1.0, 1.0))
    tri = 0.5 * np.sqrt(max(0.0, (-d + r + R) * (d + r - R) * (d - r + R) * (d + r + R)))
    return a1 + a2 - tri


def eclipse_shadow_factor(r_sc_N, r_sun_N,
                          occulter_radius_m=R_EARTH_M, sun_radius_m=R_SUN_M):
    """
    Fraction of the solar disk visible from the spacecraft, given inertial
    positions (Earth-centred, metres).

    Returns 1.0 in full sunlight, 0.0 in total umbra, and a value in (0, 1)
    in the penumbra, computed from the apparent angular radii of the Sun and
    the occulting body (Earth) and their angular separation as seen from the
    spacecraft. This multiplies solar generation directly.

    Parameters
    ----------
    r_sc_N  : array_like (3,)  spacecraft position, Earth-centred inertial [m]
    r_sun_N : array_like (3,)  Sun position, Earth-centred inertial [m]
    """
    r_sc = np.asarray(r_sc_N, dtype=float)
    r_sun = np.asarray(r_sun_N, dtype=float)

    s = r_sun - r_sc     # spacecraft -> Sun
    b = -r_sc            # spacecraft -> Earth centre (Earth at inertial origin)
    ds = np.linalg.norm(s)
    db = np.linalg.norm(b)
    if ds == 0.0 or db == 0.0:
        return 1.0
    s_hat = s / ds
    b_hat = b / db

    # Earth can only occult the Sun if it lies between the spacecraft and the
    # Sun (angular separation < 90 deg) and is nearer than the Sun.
    if np.dot(s_hat, b_hat) <= 0.0 or db > ds:
        return 1.0

    a_sun = np.arcsin(np.clip(sun_radius_m / ds, -1.0, 1.0))       # apparent Sun radius
    a_body = np.arcsin(np.clip(occulter_radius_m / db, -1.0, 1.0))  # apparent Earth radius
    theta = np.arccos(np.clip(np.dot(s_hat, b_hat), -1.0, 1.0))     # centre separation

    if theta >= a_sun + a_body:                       # disks disjoint -> full sun
        return 1.0
    if a_body >= a_sun and theta <= a_body - a_sun:   # Sun fully hidden -> umbra
        return 0.0
    if a_sun > a_body and theta <= a_sun - a_body:    # Earth inside Sun disk (annular)
        return float(1.0 - (a_body * a_body) / (a_sun * a_sun))

    covered = _circle_overlap_area(a_sun, a_body, theta)            # penumbra
    return float(np.clip(1.0 - covered / (np.pi * a_sun * a_sun), 0.0, 1.0))


def sun_distance_factor(r_sc_to_sun):
    """(1 AU / |r|)^2 irradiance scaling for the spacecraft->Sun vector [m]."""
    d = np.linalg.norm(r_sc_to_sun)
    if d == 0.0:
        return 1.0
    return (AU_M / d) ** 2


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
# Solar panel - body-mounted bus cells, NOT the perovskite payload.
# Physical model: P = S * A * eff * max(0,cos(incidence)) * shadow * dist^2 * temp
# ----------------------------------------------------------------------

class SolarPanel:
    SOLAR_CONSTANT = 1361.0  # W/m^2 at 1 AU

    def __init__(self, area_m2=0.008, efficiency=0.23, orientation=(0, 0, 1),
                 temp_coeff_per_c=0.004):
        # 0.008 m^2 usable cell area per 1U face x 0.23 cell efficiency
        # -> ~2.5 W at normal incidence in full sun, matching the PDR power
        # budget ("2.5 W: face in sun"). Tune area/efficiency to the real
        # bus-cell layout when it is fixed.
        self.area = area_m2
        self.efficiency = efficiency
        self.orientation = np.array(orientation, dtype=float) / np.linalg.norm(orientation)
        self.degradation = 1.0
        self.temperature = 25.0          # deg C; inert until an RTD feed is wired
        self.temp_coeff_per_c = temp_coeff_per_c

    def peak_power(self):
        """Normal-incidence, full-sun, 1 AU output [W]."""
        return self.SOLAR_CONSTANT * self.area * self.efficiency

    def get_power(self, sun_direction_body, shadow_factor=1.0, sun_distance_factor=1.0):
        cos_inc = max(0.0, float(np.dot(self.orientation, sun_direction_body)))
        temp_corr = 1.0 - self.temp_coeff_per_c * (self.temperature - 25.0)
        return (self.SOLAR_CONSTANT * self.area * self.efficiency *
                cos_inc * shadow_factor * sun_distance_factor *
                self.degradation * temp_corr)


class SolarArray:
    def __init__(self):
        self.panels = []

    def add_panel(self, panel):
        self.panels.append(panel)

    def get_total_power(self, sun_direction_body, shadow_factor=1.0, sun_distance_factor=1.0):
        return sum(p.get_power(sun_direction_body, shadow_factor, sun_distance_factor)
                   for p in self.panels)


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
                 num_amus=16, num_sun_sensors=2, faces=('+Z', '-X'),
                 panel_area_m2=0.008, panel_efficiency=0.23):

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
        for i in range(1, num_amus + 1):
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
        # Solar array - body-mounted bus cells on all six faces, each
        # peaking at ~2.5 W at normal incidence (PDR "face in sun"). With
        # cells on every face, attitude alone never zeroes generation; it is
        # ECLIPSE (shadow_factor -> 0) that drives generation to zero in
        # Earth's shadow. The orbit-average is an emergent result of the real
        # attitude + eclipse geometry, not a hard-coded factor. Reduce the
        # face set here when the true bus-cell layout is known.
        # --------------------------------------------------------------
        self.solar_array = SolarArray()
        for orient in [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]:
            self.solar_array.add_panel(
                SolarPanel(area_m2=panel_area_m2, efficiency=panel_efficiency, orientation=orient))
        self.panel_peak_w = self.solar_array.panels[0].peak_power()

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
    # Operational status logic: SAFE <20%, LOW 20-40%, and at >=40% split
    # on power flow -- NOMINAL when not charging, HIGH when charging.
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

    def get_total_generation(self, sun_direction_body, shadow_factor=1.0, sun_distance_factor=1.0):
        return self.solar_array.get_total_power(sun_direction_body, shadow_factor, sun_distance_factor)

    def get_net_power(self, sun_direction_body, shadow_factor=1.0, sun_distance_factor=1.0):
        gen = self.get_total_generation(sun_direction_body, shadow_factor, sun_distance_factor)
        con = self.get_total_consumption()
        return gen - con, gen, con

    # ------------------------------------------------------------------
    # Time step
    # ------------------------------------------------------------------

    def step(self, dt_s, sun_direction_body=(0, 0, 1), shadow_factor=1.0,
             sun_distance_factor=1.0, override_soc=None):
        """
        Advance the power system by dt_s seconds.

        sun_direction_body : unit vector to the Sun, body frame
        shadow_factor      : 1 sunlit, 0 umbra, in-between penumbra
                             (see eclipse_shadow_factor)
        sun_distance_factor: (1 AU / r_sun)^2 irradiance scaling
        """
        gen = self.get_total_generation(sun_direction_body, shadow_factor, sun_distance_factor)
        con = self.get_total_consumption()

        if override_soc is not None:
            self.soc = max(0.0, min(1.0, override_soc))
            self.energy_wh = self.soc * self.battery_capacity_wh
            net_power = gen - con
            self.is_charging = net_power > 0
        else:
            net_power = gen - con
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
            'generation_w': gen,
            'consumption_w': con,
            'net_power_w': net_power,
            'shadow_factor': shadow_factor,
            'eclipsed': shadow_factor < 0.5,
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
            'generation_w': self.history[-1]['generation_w'] if self.history else 0.0,
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
        eclipsed = [d.get('eclipsed', False) for d in data]

        fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)

        # Power plot, with eclipse intervals shaded
        axes[0].fill_between(t, 0, 1, where=eclipsed, transform=axes[0].get_xaxis_transform(),
                             color='gray', alpha=0.15, step='post', label='Eclipse')
        axes[0].plot(t, [d['generation_w'] for d in data], label='Generation', color='green', linewidth=1.5)
        axes[0].plot(t, [d['consumption_w'] for d in data], label='Consumption', color='red', linewidth=1.5)
        axes[0].plot(t, [d['net_power_w'] for d in data], label='Net', color='blue', linestyle='--', linewidth=1)
        axes[0].axhline(0, color='black', linewidth=0.5)
        axes[0].set_ylabel('Power (W)')
        axes[0].set_title('Power Generation vs Consumption (shaded = eclipse)')
        axes[0].legend(loc='upper right')
        axes[0].grid(True, alpha=0.3)

        # SOC
        axes[1].plot(t, [d['soc'] * 100 for d in data], color='blue', linewidth=1.5)
        axes[1].axhline(self.SOC_SAFE_MAX * 100, color='red', linestyle='--', label='SAFE threshold')
        axes[1].axhline(self.SOC_LOW_MAX * 100, color='orange', linestyle='--', label='LOW threshold')
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
        print("\n" + "=" * 60)
        print("PEROVSAT POWER SYSTEM STATUS")
        print("=" * 60)
        print(f"Time: {status['time_hours']:.2f} hours")
        print(f"Battery SOC: {status['soc'] * 100:.1f}% "
              f"({status['energy_wh']:.2f} Wh / {status['capacity_wh']} Wh)")
        print(f"Operational Status: {status['status']}")
        print(f"Panel peak (normal, full sun): {self.panel_peak_w:.2f} W/face")
        if self.history:
            gen = [d['generation_w'] for d in self.history]
            ecl = [d.get('eclipsed', False) for d in self.history]
            print(f"Instantaneous Generation: {gen[-1]:.3f} W")
            print(f"Mean Generation (sim):     {np.mean(gen):.3f} W")
            print(f"Peak Generation (sim):     {np.max(gen):.3f} W")
            print(f"Eclipse fraction (sim):    {100.0 * np.mean(ecl):.1f} %")
        print(f"Total Consumption: {status['consumption_w']:.3f} W")
        print("\nComponent Power Breakdown:")
        breakdown = self.get_component_power_breakdown()
        for name, power in sorted(breakdown.items()):
            if power > 0.0001:
                print(f"  {name}: {power:.4f} W")
        print("=" * 60 + "\n")


# ----------------------------------------------------------------------
# Quick test if run standalone (synthetic circular orbit with eclipse)
# ----------------------------------------------------------------------

if __name__ == "__main__":
    import math

    ps = PowerSystem(battery_capacity_wh=100.0, initial_soc=0.8)

    # Synthetic LEO: spacecraft on a circular orbit in the X-Y plane, Sun far
    # along +X. Half the orbit is on the far side of Earth -> eclipse.
    R_orbit = R_EARTH_M + 420e3     # ~ISS altitude
    r_sun = np.array([AU_M, 0.0, 0.0])
    dt = 10.0
    period = 2 * math.pi * math.sqrt(R_orbit ** 3 / 3.986e14)
    steps = int(3 * period / dt)    # ~3 orbits

    for i in range(steps):
        nu = 2 * math.pi * (i * dt) / period
        r_sc = np.array([R_orbit * math.cos(nu), R_orbit * math.sin(nu), 0.0])
        s = r_sun - r_sc
        sun_dir_body = s / np.linalg.norm(s)          # inertial == body (no attitude here)
        shadow = eclipse_shadow_factor(r_sc, r_sun)
        sdf = sun_distance_factor(s)
        ps.step(dt, sun_direction_body=sun_dir_body, shadow_factor=shadow,
                sun_distance_factor=sdf)

    ps.print_summary()
    ps.plot_history('power_system_example.png', show=False)
