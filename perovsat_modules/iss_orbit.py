from Basilisk.utilities import macros, orbitalMotion


def get_iss_orbit(mu):
    """
    Return inertial position and velocity vectors for a PEROVSAT ISS-matching orbit.

    Parameters
    ----------
    mu : float
        Earth gravitational parameter [m³/s²].

    Returns
    -------
    rN : list
        Inertial position vector [m].
    vN : list
        Inertial velocity vector [m/s].
    """
    oe = orbitalMotion.ClassicElements()
    oe.a = (6378.0 + 420.0) * 1000   # semi-major axis [m]
    oe.e = 0.0005                      # eccentricity
    oe.i = 51.64 * macros.D2R         # inclination [rad]
    oe.Omega = 48.2 * macros.D2R      # RAAN [rad]
    oe.omega = 347.8 * macros.D2R     # argument of perigee [rad]
    oe.f = 85.3 * macros.D2R          # true anomaly [rad]

    rN, vN = orbitalMotion.elem2rv(mu, oe)
    return rN, vN