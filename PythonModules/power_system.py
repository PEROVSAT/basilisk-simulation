"""
power_system.py
Orbital irradiance/eclipse geometry shared by sim_state.py (bus power) and
payload_iv.py (payload I-V sweeps).

NOTE: the old PowerComponent/SolarPanel/SolarArray/PowerSystem/NSLBus/OBC/...
classes that used to live in this file have been superseded by the
generalized devices/ package (devices/base.py, devices/bus_components.py,
devices/solar_cell.py) and power_management.py. Only the physics that both
the bus-power model and the payload model depend on -- eclipse shadowing and
the 1/r^2 irradiance falloff -- stays here.
"""

import numpy as np

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
    spacecraft.

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
