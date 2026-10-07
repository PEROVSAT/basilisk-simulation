"""Gravity, SPICE, ISS insertion, WMM, and eclipse.

Task order: this module assumes the spacecraft is already on ``task_name``.
SPICE must run before WMM/eclipse so planet states exist on the first step.
"""

from __future__ import annotations

from dataclasses import dataclass

from Basilisk.simulation import eclipse, magneticFieldWMM
from Basilisk.utilities import macros, orbitalMotion, simIncludeGravBody
from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

from perovsat import config
from perovsat._bsk import attach_recorder


@dataclass
class Environment:
    grav_factory: object
    spice: object
    mag: object
    sun_state_msg: object
    eclipse: object
    recorders: dict

    @property
    def eclipse_out_msg(self):
        return self.eclipse.eclipseOutMsgs[0]


def setup_environment(scSim, scObject, task_name, epoch_utc, record_period_ns) -> Environment:
    # Earth-centered frame so ISS elements, WMM, and eclipse share one origin.
    # Epoch sets Earth rotation (and thus the WMM track) for this calendar date.
    grav_factory = simIncludeGravBody.gravBodyFactory()
    bodies = grav_factory.createBodies(["earth", "sun"])
    bodies["earth"].isCentralBody = True
    grav_factory.addBodiesTo(scObject)

    spice = grav_factory.createSpiceInterface(time=epoch_utc, epochInMsg=True)
    spice.zeroBase = "earth"
    scSim.AddModelToTask(task_name, spice)

    _set_iss_orbit(scObject, grav_factory.gravBodies["earth"].mu)

    mag = magneticFieldWMM.MagneticFieldWMM()
    mag.ModelTag = "WMM"
    mag.configureWMMFile(str(get_path(DataFile.MagneticFieldData.WMM)))
    mag.addSpacecraftToModel(scObject.scStateOutMsg)
    earth_idx = grav_factory.spicePlanetNames.index("earth")
    mag.planetPosInMsg.subscribeTo(spice.planetStateOutMsgs[earth_idx])
    mag.epochInMsg.subscribeTo(grav_factory.epochMsg)
    scSim.AddModelToTask(task_name, mag)

    sun_idx = grav_factory.spicePlanetNames.index("sun")
    sun_state_msg = spice.planetStateOutMsgs[sun_idx]

    eclipse_model = eclipse.Eclipse()
    eclipse_model.ModelTag = "Eclipse"
    eclipse_model.sunInMsg.subscribeTo(sun_state_msg)
    eclipse_model.addSpacecraftToModel(scObject.scStateOutMsg)
    eclipse_model.addPlanetToModel(spice.planetStateOutMsgs[earth_idx])
    scSim.AddModelToTask(task_name, eclipse_model)

    return Environment(
        grav_factory=grav_factory,
        spice=spice,
        mag=mag,
        sun_state_msg=sun_state_msg,
        eclipse=eclipse_model,
        recorders={
            "mag": attach_recorder(scSim, task_name, mag.envOutMsgs[0], record_period_ns),
            "eclipse": attach_recorder(
                scSim, task_name, eclipse_model.eclipseOutMsgs[0], record_period_ns
            ),
        },
    )


def _set_iss_orbit(scObject, mu):
    oe = orbitalMotion.ClassicElements()
    oe.a = (config.R_EARTH_KM + config.ISS_ALT_KM) * 1e3
    oe.e = config.ISS_ECC
    oe.i = config.ISS_INC_DEG * macros.D2R
    oe.Omega = config.ISS_RAAN_DEG * macros.D2R
    oe.omega = config.ISS_AOP_DEG * macros.D2R
    oe.f = config.ISS_TA_DEG * macros.D2R
    rN, vN = orbitalMotion.elem2rv(mu, oe)
    scObject.hub.r_CN_NInit = rN
    scObject.hub.v_CN_NInit = vN
