"""
devices/solar_cell.py
Power-GENERATING solar cell. Deliberately NOT a SimulatedDevice subclass --
it produces power rather than consuming it and has no command surface
(no onMessage), so the ABC doesn't fit. Kept alongside the devices/ package
because it is still a per-face hardware model that experiments configure
the same way they configure SimulatedDevices.
"""

import numpy as np


class SolarCell:
    SOLAR_CONSTANT_W_M2 = 1361.0  # AM0 solar constant at 1 AU

    def __init__(self, name, area_m2, efficiency, orientation=(0, 0, 1),
                 temp_coeff_per_c=0.004, temperature_c=25.0):
        self.name = name
        self.area_m2 = area_m2
        self.efficiency = efficiency
        self.orientation = np.array(orientation, dtype=float)
        norm = np.linalg.norm(self.orientation)
        if norm == 0.0:
            raise ValueError(f"SolarCell '{name}': orientation vector must be nonzero")
        self.orientation /= norm
        self.temp_coeff_per_c = temp_coeff_per_c
        self.temperature_c = temperature_c
        self.degradation = 1.0

    def peak_power_w(self):
        """Normal-incidence, full-sun, 1 AU output [W]."""
        return self.SOLAR_CONSTANT_W_M2 * self.area_m2 * self.efficiency

    def power_w(self, sun_direction_body, shadow_factor=1.0, sun_distance_factor=1.0):
        """Instantaneous generated power [W] for the given Sun geometry."""
        cos_inc = max(0.0, float(np.dot(self.orientation, sun_direction_body)))
        temp_corr = 1.0 - self.temp_coeff_per_c * (self.temperature_c - 25.0)
        return (self.SOLAR_CONSTANT_W_M2 * self.area_m2 * self.efficiency *
                cos_inc * shadow_factor * sun_distance_factor *
                self.degradation * temp_corr)

    def energy_generated_wh(self, dt_s, sun_direction_body, shadow_factor=1.0,
                            sun_distance_factor=1.0):
        """Energy generated [Wh] over dt_s seconds of this (instantaneous)
        Sun geometry. This is the 'given a length of time and sun
        orientation' method the design calls for; the power manager also
        uses power_w() directly since it already tracks dt itself."""
        return self.power_w(sun_direction_body, shadow_factor,
                            sun_distance_factor) * dt_s / 3600.0
