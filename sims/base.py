import os
import sys
import numpy as np
import matplotlib.pyplot as plt

from Basilisk import __path__
from Basilisk.simulation import magneticFieldWMM, spacecraft
from Basilisk.utilities import SimulationBaseClass, macros, simIncludeGravBody, vizSupport
from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

# ---------------------------------------------------------------------------
# Path setup & Imports
# ---------------------------------------------------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # project root
sys.path.insert(0, os.path.join(_root, "PythonModules"))

try:
    import perovsat_plugins.messaging  # noqa: F401 — registers custom message recorders
    from perovsat_plugins.permanentMagnet import PermanentMagnet
except ImportError as exc:
    raise ImportError(f"Compiled plugin modules not found.\nOriginal error: {exc}") from exc

from issOrbit import set_iss_orbit  # noqa: E402
from hysteresisFactory import HysteresisFactory


# ---------------------------------------------------------------------------
# Key parameters
# ---------------------------------------------------------------------------
MASS_KG          = 1.2
INERTIA_KGM2     = [[0.002, 0.0, 0.0],
                     [0.0,   0.002, 0.0],
                     [0.0,   0.0,   0.001]]

SIGMA_INIT       = [[0.2], [-0.1], [0.3]] # Initial attitude
OMEGA_INIT_RADS  = [[0.05], [0.07], [0.02]] # Intial rotation in rads/sec

DIPOLE_BODY_AM2  = np.array([0.0, 0.0, 0.15]) # Permanent Magnet dipole

ROD_DIAMETER_M   = 0.001
ROD_L_Z_M        = 0.095
ROD_L_XY_M       = 0.095

SIM_DURATION_S   = 200.0 
TIMESTEP_S       = 0.001

VIZARD_OUTPUT    = os.path.splitext(__file__)[0]


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

    # Earth gravity & Orbit
    gravFactory = simIncludeGravBody.gravBodyFactory()
    planet = gravFactory.createEarth()
    planet.isCentralBody = True
    gravFactory.addBodiesTo(scObject)

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

    # Hysteresis Rods
    rod_factory = HysteresisFactory(scSim, scObject, magModule)

    # Z-Axis: Libration damping
    rod_z = rod_factory.add_rod(
        length_m=ROD_L_Z_M,
        diameter_m=ROD_DIAMETER_M,
        axis_B=[0.0, 0.0, 1.0],
        json_path="./hysteresis_configs/hymu80_z_axis.json",
        tag="HystRod_Z"
    )
    hystDebugRec = rod_z.hysteresisDebugOutMsg.recorder()
    scSim.AddModelToTask("simTask", hystDebugRec)

    # XY-Axis: Rotisserie & transverse tumbling
    # rod_factory.add_rod(ROD_L_XY_M, ROD_DIAMETER_M, [1.0, 0.0, 0.0], "./hysteresis_configs/hymu80_xy_axis.json", "HystRod_X")
    # rod_factory.add_rod(ROD_L_XY_M, ROD_DIAMETER_M, [0.0, 1.0, 0.0], "./hysteresis_configs/hymu80_xy_axis.json", "HystRod_Y")
    # rod_factory.add_rod(ROD_L_XY_M, ROD_DIAMETER_M, [0.707, 0.707, 0.0], "./hysteresis_configs/hymu80_xy_axis.json", "HystRod_XY")

    # Vizard
    if vizSupport.vizFound:
        vizSupport.enableUnityVisualization(
            scSim, "simTask", scObject, saveFile=VIZARD_OUTPUT
        )

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(SIM_DURATION_S))
    scSim.ExecuteSimulation()

    plot_hysteresis_loop(hystDebugRec)


def plot_hysteresis_loop(hyst_recorder, filename="hysteresis_loop.png"):
    """
    Saves the M-H hysteresis loop plot from logged debug messages to a file.
    """
    # Extract data arrays
    H = np.array(hyst_recorder.H)
    M = np.array(hyst_recorder.M)
    
    plt.figure(figsize=(8, 6))
    
    # Plot the full loop
    plt.plot(H, M, color='blue', linewidth=1.5, label="Z-Axis Rod")
    
    # Mark the start and end points to see the progression direction
    plt.plot(H[0], M[0], 'go', label="Start")
    plt.plot(H[-1], M[-1], 'ro', label="End")
    
    plt.xlabel("Axial Magnetic Field Strength, $H$ (A/m)")
    plt.ylabel("Magnetization, $M$ (A/m)")
    plt.title("Jiles-Atherton Hysteresis Loop")
    plt.grid(True, linestyle='--', alpha=0.7)
    plt.legend()
    plt.tight_layout()
    
    # Save to disk instead of rendering to a window
    plt.savefig(filename, dpi=300)
    plt.close()  # Free memory



if __name__ == "__main__":
    run()
