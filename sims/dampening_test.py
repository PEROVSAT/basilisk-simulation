import os
import sys

import numpy as np

from Basilisk import __path__
from Basilisk.simulation import magneticFieldWMM, spacecraft
from Basilisk.utilities import SimulationBaseClass, macros, simIncludeGravBody, vizSupport
from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

# ---------------------------------------------------------------------------
# Key parameters — edit here
# ---------------------------------------------------------------------------

MASS_KG          = 1.2
INERTIA_KGM2     = [[0.002, 0.0, 0.0],
                     [0.0,   0.002, 0.0],
                     [0.0,   0.0,   0.001]]
SIGMA_INIT       = [[0.2], [-0.1], [0.3]]    # initial MRP
OMEGA_INIT_RADS  = [[0.05], [0.07], [0.02]]  # initial angular velocity [rad/s]

DIPOLE_BODY_AM2  = np.array([0.0, 0.0, 0.15])  # permanent magnet dipole vector [A·m²]

SIM_DURATION_S   = 5580.0   # ~1 ISS orbital period [s]
TIMESTEP_S       = 1.0

VIZARD_OUTPUT    = os.path.splitext(__file__)[0]  # writes core_sim.bin beside this file

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root
sys.path.insert(0, os.path.join(_root, "PythonModules"))

from issOrbit import set_iss_orbit        # noqa: E402
from fakeDampening import FakeDampener    # noqa: E402

try:
    from perovsat_plugins.permanentMagnet import PermanentMagnet
except ImportError as exc:
    raise ImportError(
        "Compiled 'permanentMagnet' module not found. "
        "Run ./setup.sh to build the Docker image which compiles the plugin.\n"
        f"  Original error: {exc}"
    ) from exc


def run():
    scSim = SimulationBaseClass.SimBaseClass()
    scSim.SetProgressBar(True)

    dynProcess = scSim.CreateNewProcess("simProcess")
    dynProcess.addTask(scSim.CreateNewTask("simTask", macros.sec2nano(TIMESTEP_S)))

    # Spacecraft
    scObject = spacecraft.Spacecraft()
    scObject.ModelTag = "PEROVSAT"
    scObject.hub.mHub = MASS_KG
    scObject.hub.IHubPntBc_B = INERTIA_KGM2
    scObject.hub.sigma_BNInit = SIGMA_INIT
    scObject.hub.omega_BN_BInit = OMEGA_INIT_RADS
    scSim.AddModelToTask("simTask", scObject)

    # Earth gravity
    gravFactory = simIncludeGravBody.gravBodyFactory()
    planet = gravFactory.createEarth()
    planet.isCentralBody = True
    gravFactory.addBodiesTo(scObject)

    # ISS orbit
    set_iss_orbit(scObject, planet.mu)

    # WMM
    magModule = magneticFieldWMM.MagneticFieldWMM()
    magModule.ModelTag = "WMM"
    magModule.configureWMMFile(str(get_path(DataFile.MagneticFieldData.WMM)))
    magModule.addSpacecraftToModel(scObject.scStateOutMsg)
    scSim.AddModelToTask("simTask", magModule)

    # Permanent magnet
    permMagnet = PermanentMagnet()
    permMagnet.ModelTag = "PermanentMagnet"
    permMagnet.magDipole_B = DIPOLE_BODY_AM2
    permMagnet.magFieldInMsg.subscribeTo(magModule.envOutMsgs[0])
    scObject.addDynamicEffector(permMagnet)
    scSim.AddModelToTask("simTask", permMagnet)

    # Fake viscous damping (near-critical, for visual verification only)
    FakeDampener(scSim, "simTask", scObject)

    # Vizard — save to file
    if vizSupport.vizFound:
        vizSupport.enableUnityVisualization(
            scSim, "simTask", scObject, saveFile=VIZARD_OUTPUT
        )

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(SIM_DURATION_S))
    scSim.ExecuteSimulation()


if __name__ == "__main__":
    run()
