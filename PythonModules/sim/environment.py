"""
sim/environment.py
SPICE + WMM + ISS orbit + eclipse.
"""

from dataclasses import dataclass
import os
import sys

from Basilisk.simulation import eclipse, magneticFieldWMM
from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "PythonModules"))

from sim.solarSystemFactory import setup_solar_system, wire_wmm_epoch
from sim.issOrbit import set_iss_orbit


@dataclass
class Environment:
    grav_factory: object
    spice: object
    mag: object
    sun_state_msg: object
    eclipse: object

    @property
    def eclipse_out_msg(self):
        return self.eclipse.eclipseOutMsgs[0]


def setup_environment(scSim, scObject, task_name, epoch_utc) -> Environment:
    grav_factory, spice = setup_solar_system(
        scSim, scObject, task_name, epoch_utc
    )
    set_iss_orbit(scObject, grav_factory.gravBodies["earth"].mu)

    mag = magneticFieldWMM.MagneticFieldWMM()
    mag.ModelTag = "WMM"
    mag.configureWMMFile(str(get_path(DataFile.MagneticFieldData.WMM)))
    mag.addSpacecraftToModel(scObject.scStateOutMsg)
    wire_wmm_epoch(mag, grav_factory, spice)
    scSim.AddModelToTask(task_name, mag)

    sun_idx = grav_factory.spicePlanetNames.index("sun")
    earth_idx = grav_factory.spicePlanetNames.index("earth")
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
    )
