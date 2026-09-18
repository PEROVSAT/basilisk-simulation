"""
sim/physics.py
Orbital irradiance and eclipse geometry.
"""

import numpy as np

R_EARTH_M = 6.378137e6
R_SUN_M = 6.9634e8
AU_M = 1.495978707e11


def _circle_overlap_area(r, R, d):
    if d >= r + R:
        return 0.0
    if d <= abs(R - r):
        return np.pi * min(r, R) ** 2
    r2, R2, d2 = r * r, R * R, d * d
    a1 = r2 * np.arccos(np.clip((d2 + r2 - R2) / (2 * d * r), -1.0, 1.0))
    a2 = R2 * np.arccos(np.clip((d2 + R2 - r2) / (2 * d * R), -1.0, 1.0))
    tri = 0.5 * np.sqrt(max(0.0, (-d + r + R) * (d + r - R) * (d - r + R) * (d + r + R)))
    return a1 + a2 - tri


def eclipse_shadow_factor(r_sc_N, r_sun_N,
                          occulter_radius_m=R_EARTH_M, sun_radius_m=R_SUN_M):
    """Fraction of the solar disk visible from the spacecraft."""
    r_sc = np.asarray(r_sc_N, dtype=float)
    r_sun = np.asarray(r_sun_N, dtype=float)
    s = r_sun - r_sc
    b = -r_sc
    ds = np.linalg.norm(s)
    db = np.linalg.norm(b)
    if ds == 0.0 or db == 0.0:
        return 1.0
    s_hat = s / ds
    b_hat = b / db
    if np.dot(s_hat, b_hat) <= 0.0 or db > ds:
        return 1.0
    a_sun = np.arcsin(np.clip(sun_radius_m / ds, -1.0, 1.0))
    a_body = np.arcsin(np.clip(occulter_radius_m / db, -1.0, 1.0))
    theta = np.arccos(np.clip(np.dot(s_hat, b_hat), -1.0, 1.0))
    if theta >= a_sun + a_body:
        return 1.0
    if a_body >= a_sun and theta <= a_body - a_sun:
        return 0.0
    if a_sun > a_body and theta <= a_sun - a_body:
        return float(1.0 - (a_body * a_body) / (a_sun * a_sun))
    covered = _circle_overlap_area(a_sun, a_body, theta)
    return float(np.clip(1.0 - covered / (np.pi * a_sun * a_sun), 0.0, 1.0))


def sun_distance_factor(r_sc_to_sun):
    d = np.linalg.norm(r_sc_to_sun)
    if d == 0.0:
        return 1.0
    return (AU_M / d) ** 2