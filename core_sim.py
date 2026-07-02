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

# ---------------------------------------------------------------------------
# Hysteresis rod parameters — 4× Mu-Metal rods, 2 mm dia × 95 mm long
# Material: Mu-Metal (HyMu-77 / 80 grade)
#   Bs  = 0.65 T  (saturation flux density, from PDR)
#   Hc  = 1.5 A/m (real coercivity — very soft)
#   μr  ≈ 40 000  (initial relative permeability)
#
# JA parameters derived from the above:
#   Ms  = Bs/μ₀ = 0.65 / (4π×10⁻⁷) ≈ 5.17×10⁵ A/m
#   a   ≈ 3 A/m  — Langevin scale; Earth's field (~30 A/m) >> a, so the rods
#                  spend most of each orbit fully saturated and trace complete
#                  hysteresis loops each time the projected field reverses sign
#   k   ≈ 1.5 A/m — domain-wall pinning, matches the real Hc
#   c   = 0.15    — small reversible fraction typical of Mu-Metal
#   alpha = 1e-4  — weak interdomain coupling; keeps the model stable at the
#                  high permeability of Mu-Metal (χ_init ≈ Ms/3a ≈ 5.8×10⁴)
#
# Geometry: V_single = π × (0.001 m)² × 0.095 m = 2.985×10⁻⁷ m³
#   Rod 1 & 2: axis along body +X — damp X-axis tumble
#   Rod 3 & 4: axis along body +Y — damp Y-axis tumble
# (Z-axis is the science spin axis; rods along Z would damp the desired spin)
#
# Detumble estimate:
#   Energy dissipated per orbit ≈ 4 rods × 90 loop-crossings × μ₀×4Hc×Ms×V
#                               ≈ 4.3×10⁻⁴ J/orbit
#   Initial KE ≈ 7.8×10⁻⁶ J  →  bulk damping within ~1 orbit
#   5 orbits (27 900 s) gives a complete damping curve with margin.
# ---------------------------------------------------------------------------
ROD_Ms              = 5.17e5   # [A/m]     Saturation magnetization
ROD_a               = 3.0      # [A/m]     Langevin shape parameter
ROD_alpha           = 1.0e-4   # [-]       Interdomain coupling
ROD_k               = 1.5      # [A/m]     Domain-wall pinning (≈ Hc)
ROD_c               = 0.15     # [-]       Reversibility coefficient
ROD_M0              = 0.0      # [A/m]     Initially demagnetized
ROD_DELTA_SMOOTHING = 0.3      # [A/m/s]   tanh() smoothing width for δ
ROD_V_SINGLE        = 2.985e-7 # [m³]      Volume per rod

SIM_DURATION_S   = 100000
TIMESTEP_S       = 1.0

VIZARD_OUTPUT    = os.path.splitext(__file__)[0]  # writes core_sim.bin beside this file

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_root, "PythonModules"))

from issOrbit import set_iss_orbit  # noqa: E402

try:
    from perovsat_plugins.permanentMagnet import PermanentMagnet
    from perovsat_plugins.hyteresisRods import HysteresisRods
except ImportError as exc:
    raise ImportError(
        "Compiled plugin modules not found. "
        "Run ./setup.sh to build the Docker image which compiles the plugins.\n"
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

    # Hysteresis rods (Jiles-Atherton passive detumbler)
    # Four rods: 2 along body +X, 2 along body +Y.  Z-axis left undamped
    # so the science spin is preserved.
    _rod_axes = [
        ([1.0, 0.0, 0.0], "HystRod_X1"),
        ([1.0, 0.0, 0.0], "HystRod_X2"),
        ([0.0, 1.0, 0.0], "HystRod_Y1"),
        ([0.0, 1.0, 0.0], "HystRod_Y2"),
    ]
    for axis, tag in _rod_axes:
        rod = HysteresisRods()
        rod.ModelTag        = tag
        rod.Ms              = ROD_Ms
        rod.a               = ROD_a
        rod.alpha           = ROD_alpha
        rod.k               = ROD_k
        rod.c               = ROD_c
        rod.M0              = ROD_M0
        rod.deltaSmoothing  = ROD_DELTA_SMOOTHING
        rod.u_B             = axis
        rod.V               = ROD_V_SINGLE
        rod.magFieldInMsg.subscribeTo(magModule.envOutMsgs[0])
        scObject.addStateEffector(rod)
        scSim.AddModelToTask("simTask", rod)

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
