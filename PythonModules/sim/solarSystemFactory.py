"""
solarSystemFactory.py
----------------------
Sets up an Earth-centered gravity environment that also includes the Sun as
a real, SPICE-ephemeris-driven perturbing body, anchored to an actual UTC
epoch. This replaces the plain
`simIncludeGravBody.gravBodyFactory().createEarth()` call scenarios were
using with one that ties the simulation to a real calendar date/time, which
matters for two reasons:

1. Earth's rotational phase at t=0 (and therefore which longitude the
   orbit's initial true anomaly corresponds to) depends on the actual epoch,
   so a summer vs. winter launch date produces a genuinely different WMM
   field trace along the same orbit -- not just a different label. This
   dominates over WMM's own epoch-dependent secular variation for two dates
   within the same year; the secular term matters more for dates years apart.
2. The Sun becomes a real third-body gravitational perturber on the
   spacecraft (tiny for a 1U CubeSat in LEO over the timescales this repo
   simulates, but now physically present rather than absent).

Usage
-----
    from solarSystemFactory import setup_solar_system, wire_wmm_epoch

    gravFactory, spiceObject = setup_solar_system(scSim, scObject, "simTask", EPOCH_UTC)
    set_iss_orbit(scObject, gravFactory.gravBodies["earth"].mu)

    magModule = magneticFieldWMM.MagneticFieldWMM()
    ...
    wire_wmm_epoch(magModule, gravFactory, spiceObject)
"""

from Basilisk.utilities import simIncludeGravBody


def setup_solar_system(scSim, scObject, task_name, utc_epoch):
    """
    Creates Earth (central body) + Sun (perturbing body) via a real SPICE
    ephemeris anchored to `utc_epoch`, and attaches both as gravitational
    effectors on `scObject`.

    Parameters
    ----------
    scSim : SimulationBaseClass.SimBaseClass
    scObject : spacecraft.Spacecraft
        Must already be added to `task_name`.
    task_name : str
        Task the SPICE interface's own state update runs on -- should be the
        same task the rest of the dynamics run on.
    utc_epoch : str
        A SPICE-recognized UTC time string,
        e.g. "2026 JUN 21 12:00:00.0 (UTC)".

    Returns
    -------
    gravFactory : simIncludeGravBody.gravBodyFactory
        Access bodies via gravFactory.gravBodies["earth"] / ["sun"].
    spiceObject : Basilisk.simulation.spiceInterface.SpiceInterface
    """
    gravFactory = simIncludeGravBody.gravBodyFactory()
    bodies = gravFactory.createBodies(["earth", "sun"])
    bodies["earth"].isCentralBody = True
    gravFactory.addBodiesTo(scObject)

    # zeroBase="earth" re-centers every body's reported position on Earth,
    # matching the Earth-centered orbital elements the rest of this repo
    # uses (issOrbit.py), while the Sun's position is still the real SPICE
    # ephemeris position relative to Earth for this epoch.
    spiceObject = gravFactory.createSpiceInterface(time=utc_epoch, epochInMsg=True)
    spiceObject.zeroBase = "earth"
    scSim.AddModelToTask(task_name, spiceObject)

    return gravFactory, spiceObject


def wire_wmm_epoch(magModule, gravFactory, spiceObject):
    """
    Ties a MagneticFieldWMM module's Earth-fixed rotation and epoch-dependent
    secular variation to the same SPICE epoch used for orbital dynamics, so
    the WMM field is evaluated at the real Earth orientation/date instead of
    an unset (epochDateFractionalYear == -1.0) default.
    """
    earthIdx = gravFactory.spicePlanetNames.index("earth")
    magModule.planetPosInMsg.subscribeTo(spiceObject.planetStateOutMsgs[earthIdx])
    magModule.epochInMsg.subscribeTo(gravFactory.epochMsg)
