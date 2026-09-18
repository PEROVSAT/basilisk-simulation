"""
sim/environment.py
SPICE + WMM + orbit setup.
"""

import os
import sys

from Basilisk.simulation import magneticFieldWMM
from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "PythonModules"))

from sim.solarSystemFactory import setup_solar_system, wire_wmm_epoch
from sim.issOrbit import set_iss_orbit


def setup_environment(scSim, scObject, task_name, epoch_utc):
    """
    Set up gravity, SPICE, WMM, orbit.

    Returns (gravFactory, spiceObject, magModule, sunStateMsg).
    """
    gravFactory, spiceObject = setup_solar_system(
        scSim, scObject, task_name, epoch_utc
    )
    set_iss_orbit(scObject, gravFactory.gravBodies["earth"].mu)

    magModule = magneticFieldWMM.MagneticFieldWMM()
    magModule.ModelTag = "WMM"
    magModule.configureWMMFile(str(get_path(DataFile.MagneticFieldData.WMM)))
    magModule.addSpacecraftToModel(scObject.scStateOutMsg)
    wire_wmm_epoch(magModule, gravFactory, spiceObject)
    scSim.AddModelToTask(task_name, magModule)

    sunIdx = gravFactory.spicePlanetNames.index("sun")
    sunStateMsg = spiceObject.planetStateOutMsgs[sunIdx]

    return gravFactory, spiceObject, magModule, sunStateMsg