import os
import sys

import numpy as np

from Basilisk import __path__
from Basilisk.simulation import magneticFieldWMM, spacecraft
from Basilisk.utilities import SimulationBaseClass, macros, simIncludeGravBody, vizSupport
from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

from Basilisk.architecture import sysModel, messaging
from Basilisk.utilities import RigidBodyKinematics as rbk

# ---------------------------------------------------------------------------
# Key parameters
# ---------------------------------------------------------------------------

MASS_KG          = 1.2
INERTIA_KGM2     = [[0.002, 0.0, 0.0],
                     [0.0,   0.002, 0.0],
                     [0.0,   0.0,   0.001]]
SIGMA_INIT       = [[0.2], [-0.1], [0.3]]
OMEGA_INIT_RADS  = [[0.0], [0.0], [0.0]]     

SIM_DURATION_S   = 5580.0
TIMESTEP_S       = 1.0

VIZARD_OUTPUT    = os.path.splitext(__file__)[0]

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_root, "PythonModules"))

from issOrbit import set_iss_orbit  # noqa: E402


# ---------------------------------------------------------------------------
# WMM Kinematic Override Module
# ---------------------------------------------------------------------------
class WmmAligner(sysModel.SysModel):
    """Reads true position and WMM field, outputs a combined state message for Vizard."""
    def __init__(self, modelName="WmmAligner"):
        super().__init__()
        self.ModelTag = modelName
        self.magInMsg = messaging.MagneticFieldMsgReader()
        self.scStateInMsg = messaging.SCStatesMsgReader()
        self.vizStateOutMsg = messaging.SCStatesMsg()

    def UpdateState(self, CurrentSimNanos):
        # Python wrapper calls the object directly rather than using .read()
        magMsg = self.magInMsg()
        scMsg = self.scStateInMsg()

        outMsg = messaging.SCStatesMsgPayload()
        
        # 1. Lock position and velocity to the real dynamic spacecraft
        outMsg.r_BN_N = scMsg.r_BN_N
        outMsg.v_BN_N = scMsg.v_BN_N

        # 2. Compute attitude aligned with WMM vector
        b_N = np.array(magMsg.magField_N)
        norm_b = np.linalg.norm(b_N)

        if norm_b > 1e-12:
            b3 = b_N / norm_b
            
            nX = np.array([1.0, 0.0, 0.0])
            if np.linalg.norm(np.cross(b3, nX)) < 1e-5:
                nX = np.array([0.0, 1.0, 0.0])
            
            b2 = np.cross(b3, nX)
            b2 = b2 / np.linalg.norm(b2)
            b1 = np.cross(b2, b3)

            dcm_BN = np.array([b1, b2, b3])
            outMsg.sigma_BN = rbk.C2MRP(dcm_BN)
        else:
            outMsg.sigma_BN = [0.0, 0.0, 0.0]

        self.vizStateOutMsg.write(outMsg, CurrentSimNanos, self.moduleID)

def run():
    scSim = SimulationBaseClass.SimBaseClass()
    scSim.SetProgressBar(True)

    dynProcess = scSim.CreateNewProcess("simProcess")
    dynProcess.addTask(scSim.CreateNewTask("simTask", macros.sec2nano(TIMESTEP_S)))

    # 1. Main Spacecraft (satisfies physics and vizSupport init)
    scObject = spacecraft.Spacecraft()
    scObject.ModelTag = "PEROVSAT"
    scObject.hub.mHub = MASS_KG
    scObject.hub.IHubPntBc_B = INERTIA_KGM2
    scObject.hub.sigma_BNInit = SIGMA_INIT
    scObject.hub.omega_BN_BInit = OMEGA_INIT_RADS
    scSim.AddModelToTask("simTask", scObject)

    gravFactory = simIncludeGravBody.gravBodyFactory()
    planet = gravFactory.createEarth()
    planet.isCentralBody = True
    gravFactory.addBodiesTo(scObject)

    set_iss_orbit(scObject, planet.mu)

    # 2. WMM Module
    magModule = magneticFieldWMM.MagneticFieldWMM()
    magModule.ModelTag = "WMM"
    magModule.configureWMMFile(str(get_path(DataFile.MagneticFieldData.WMM)))
    magModule.addSpacecraftToModel(scObject.scStateOutMsg)
    scSim.AddModelToTask("simTask", magModule)

    # 3. Kinematic Aligner
    wmmAligner = WmmAligner()
    wmmAligner.magInMsg.subscribeTo(magModule.envOutMsgs[0])
    wmmAligner.scStateInMsg.subscribeTo(scObject.scStateOutMsg)
    scSim.AddModelToTask("simTask", wmmAligner)

    # 4. Vizard configuration
    # The first element MUST be a spacecraft.Spacecraft instance.
    # The second element is our list-formatted proxy.
    scList = [scObject, ["WMM_Aligned", wmmAligner.vizStateOutMsg]]

    if vizSupport.vizFound:
        vizSupport.enableUnityVisualization(
            scSim, "simTask", scList, saveFile=VIZARD_OUTPUT
        )

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(SIM_DURATION_S))
    scSim.ExecuteSimulation()


if __name__ == "__main__":
    run()
