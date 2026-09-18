"""
issOrbit.py
-----------
Sets a Basilisk spacecraft object's initial state to an ISS-matching orbit.

ISS orbital parameters (epoch ~2024):
  Altitude  : 420 km
  Inclination: 51.64 deg
  RAAN      : 48.2 deg
  Arg of perigee: 347.8 deg
  True anomaly  : 85.3 deg
  Eccentricity  : 0.0005
"""

from Basilisk.utilities import macros, orbitalMotion


# Nominal ISS orbital elements
_ISS_ALT_KM   = 420.0
_ISS_ECC      = 0.0005
_ISS_INC_DEG  = 51.64
_ISS_RAAN_DEG = 48.2
_ISS_AOP_DEG  = 347.8
_ISS_TA_DEG   = 85.3


def set_iss_orbit(scObject, mu, alt_km=None, inc_deg=None, ecc=None,
                  raan_deg=None, aop_deg=None, ta_deg=None):
    """
    Apply ISS-matching initial orbital state to a Basilisk spacecraft object.

    Parameters
    ----------
    scObject : spacecraft.Spacecraft
        Basilisk spacecraft whose hub r/v init vectors will be set.
    mu : float
        Earth gravitational parameter [m³/s²].
    alt_km : float, optional
        Orbital altitude above Earth's surface [km]. Defaults to 420 km.
    inc_deg : float, optional
        Inclination [deg]. Defaults to 51.64 deg.
    ecc : float, optional
        Eccentricity. Defaults to 0.0005.
    raan_deg : float, optional
        Right ascension of the ascending node [deg]. Defaults to 48.2 deg.
    aop_deg : float, optional
        Argument of perigee [deg]. Defaults to 347.8 deg.
    ta_deg : float, optional
        True anomaly [deg]. Defaults to 85.3 deg.

    Returns
    -------
    oe : orbitalMotion.ClassicElements
        The classical orbital elements used for initialisation.
    rN : list[float]
        Inertial position vector [m].
    vN : list[float]
        Inertial velocity vector [m/s].
    """
    R_EARTH_KM = 6378.0

    oe = orbitalMotion.ClassicElements()
    oe.a     = (R_EARTH_KM + (alt_km  if alt_km  is not None else _ISS_ALT_KM))  * 1e3
    oe.e     =  ecc      if ecc      is not None else _ISS_ECC
    oe.i     = (inc_deg  if inc_deg  is not None else _ISS_INC_DEG)  * macros.D2R
    oe.Omega = (raan_deg if raan_deg is not None else _ISS_RAAN_DEG) * macros.D2R
    oe.omega = (aop_deg  if aop_deg  is not None else _ISS_AOP_DEG)  * macros.D2R
    oe.f     = (ta_deg   if ta_deg   is not None else _ISS_TA_DEG)   * macros.D2R

    rN, vN = orbitalMotion.elem2rv(mu, oe)

    scObject.hub.r_CN_NInit = rN
    scObject.hub.v_CN_NInit = vN

    return oe, rN, vN
