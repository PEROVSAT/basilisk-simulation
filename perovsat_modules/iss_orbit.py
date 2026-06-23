from Basilisk.utilities import orbitalMotion, macros


def get_iss_orbit(mu):
    oe = orbitalMotion.ClassicElements()

    earthRadius = 6378.0 * 1000
    issAltitude = 420.0 * 1000

    oe.a = earthRadius + issAltitude
    oe.e = 0.0005
    oe.i = 51.64 * macros.D2R
    oe.Omega = 48.2 * macros.D2R
    oe.omega = 347.8 * macros.D2R
    oe.f = 85.3 * macros.D2R

    rN, vN = orbitalMotion.elem2rv(mu, oe)

    return rN, vN