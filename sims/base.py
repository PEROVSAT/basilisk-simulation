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

SIGMA_INIT       = [[0.2], [-0.1], [0.3]]    # Initial attitude
OMEGA_INIT_RADS  = [[0.05], [0.07], [0.02]]  # Initial rotation in rad/s

DIPOLE_BODY_AM2  = np.array([0.0, 0.0, 0.15])  # Permanent magnet dipole

# 8-rod HyMu80 PMAC layout, sized per rod: 85mm x 2mm diameter
ROD_DIAMETER_M   = 0.002
ROD_LENGTH_M     = 0.085

# Full-length (multi-day) detumble run. Step rate benchmarked at ~14k steps/s
# on this hardware, so ~18 days at 0.5s step is only a few minutes of wall time.
SIM_DURATION_S   = 18 * 24 * 3600.0   # 18 days
TIMESTEP_S       = 0.5

# Recorders sampled every N seconds rather than every task step, to keep the
# logged arrays a manageable size over an 18-day run.
RECORD_PERIOD_S  = 5.0

VIZARD_OUTPUT    = os.path.splitext(__file__)[0]

_configs_dir = os.path.join(_root, "hysteresis_configs")
Z_JSON  = os.path.join(_configs_dir, "hymu80_z_axis.json")
XY_JSON = os.path.join(_configs_dir, "hymu80_xy_axis.json")

INV_SQRT2 = 0.70710678118654752


def run():
    scSim = SimulationBaseClass.SimBaseClass()
    scSim.SetProgressBar(False)

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

    # -----------------------------------------------------------------
    # Hysteresis Rods — 8 total, 85mm x 2mm each
    #   2x Z  (narrow/reversible material -> fine libration damping)
    #   2x X, 2x Y, 2x diagonal  (wide-loop material -> rotisserie/
    #   transverse-tumble damping, covers modes not aligned to a
    #   principal axis)
    # -----------------------------------------------------------------
    rod_factory = HysteresisFactory(scSim, scObject, magModule)

    rod_defs = [
        ("HystRod_Z1", [0.0, 0.0, 1.0], Z_JSON),
        ("HystRod_Z2", [0.0, 0.0, 1.0], Z_JSON),
        ("HystRod_X1", [1.0, 0.0, 0.0], XY_JSON),
        ("HystRod_X2", [1.0, 0.0, 0.0], XY_JSON),
        ("HystRod_Y1", [0.0, 1.0, 0.0], XY_JSON),
        ("HystRod_Y2", [0.0, 1.0, 0.0], XY_JSON),
        ("HystRod_D1", [INV_SQRT2,  INV_SQRT2, 0.0], XY_JSON),
        ("HystRod_D2", [INV_SQRT2, -INV_SQRT2, 0.0], XY_JSON),
    ]

    rods = {}
    for tag, axis, json_path in rod_defs:
        rods[tag] = rod_factory.add_rod(
            length_m=ROD_LENGTH_M,
            diameter_m=ROD_DIAMETER_M,
            axis_B=axis,
            json_path=json_path,
            tag=tag,
        )

    # Debug recorders on one representative rod per axis group, to keep
    # logged data manageable while still covering each damping channel.
    rec_period = macros.sec2nano(RECORD_PERIOD_S)
    hystRecorders = {
        "Z": rods["HystRod_Z1"].hysteresisDebugOutMsg.recorder(rec_period),
        "X": rods["HystRod_X1"].hysteresisDebugOutMsg.recorder(rec_period),
        "D": rods["HystRod_D1"].hysteresisDebugOutMsg.recorder(rec_period),
    }
    for rec in hystRecorders.values():
        scSim.AddModelToTask("simTask", rec)

    # Spacecraft state recorder -> the real detumble curve (omega vs time)
    scStateRec = scObject.scStateOutMsg.recorder(rec_period)
    scSim.AddModelToTask("simTask", scStateRec)

    # Vizard — disabled for this long (18-day, 3.1M-step) headless analysis
    # run. Writing a per-step binary Vizard frame for that many steps is an
    # I/O bottleneck unrelated to the physics; use a short-duration run (see
    # wmm_pointing.py / dampening_test.py) for actual Vizard playback.
    if vizSupport.vizFound and os.environ.get("PEROVSAT_ENABLE_VIZ"):
        vizSupport.enableUnityVisualization(
            scSim, "simTask", scObject, saveFile=VIZARD_OUTPUT
        )

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(SIM_DURATION_S))
    scSim.ExecuteSimulation()

    plot_hysteresis_loops(hystRecorders)
    plot_detumble_curve(scStateRec)


def plot_hysteresis_loops(hystRecorders, filename="hysteresis_loop.png"):
    """
    Saves M-H hysteresis loop plots for one representative rod per axis
    group (Z, X, diagonal) to a single figure.
    """
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    labels = {"Z": "Z-Axis Rod (Z1)", "X": "X-Axis Rod (X1)", "D": "Diagonal Rod (D1)"}

    for ax, key in zip(axes, ["Z", "X", "D"]):
        rec = hystRecorders[key]
        H = np.array(rec.H)
        M = np.array(rec.M)
        ax.plot(H, M, color='blue', linewidth=0.8)
        ax.plot(H[0], M[0], 'go', label="Start")
        ax.plot(H[-1], M[-1], 'ro', label="End")
        ax.set_xlabel("H (A/m)")
        ax.set_ylabel("M (A/m)")
        ax.set_title(labels[key])
        ax.grid(True, linestyle='--', alpha=0.7)
        ax.legend()

    fig.suptitle("Jiles-Atherton Hysteresis Loops — 18-Day Detumble Run")
    plt.tight_layout()
    plt.savefig(filename, dpi=200)
    plt.close(fig)


def plot_detumble_curve(scStateRec, filename="detumble_curve.png"):
    """
    Plots body angular rate components and magnitude vs. time —
    the actual PMAC detumble curve.
    """
    t_s = np.array(scStateRec.times()) * 1.0e-9
    omega = np.array(scStateRec.omega_BN_B)  # shape (N,3), rad/s

    omega_deg = np.degrees(omega)
    omega_mag_deg = np.degrees(np.linalg.norm(omega, axis=1))

    t_days = t_s / 86400.0

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    ax1.plot(t_days, omega_deg[:, 0], label=r"$\omega_x$", linewidth=0.7)
    ax1.plot(t_days, omega_deg[:, 1], label=r"$\omega_y$", linewidth=0.7)
    ax1.plot(t_days, omega_deg[:, 2], label=r"$\omega_z$", linewidth=0.7)
    ax1.set_ylabel("Body rate (deg/s)")
    ax1.set_title("PMAC Detumble Curve — 8-Rod HyMu80 Layout (85mm x 2mm)")
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.legend()

    ax2.plot(t_days, omega_mag_deg, color='k', linewidth=1.0)
    ax2.set_xlabel("Time (days)")
    ax2.set_ylabel(r"$|\omega|$ (deg/s)")
    ax2.grid(True, linestyle='--', alpha=0.6)

    plt.tight_layout()
    plt.savefig(filename, dpi=200)
    plt.close(fig)

    # Also dump raw data for any further analysis
    np.savez("detumble_data.npz", t_s=t_s, omega=omega)

    print(f"\nInitial |omega|: {omega_mag_deg[0]:.4f} deg/s")
    print(f"Final   |omega|: {omega_mag_deg[-1]:.4f} deg/s  (t = {t_days[-1]:.2f} days)")


if __name__ == "__main__":
    run()
