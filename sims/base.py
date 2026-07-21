import os
import sys
import numpy as np
import matplotlib.pyplot as plt

from Basilisk import __path__
from Basilisk.simulation import magneticFieldWMM, spacecraft, svIntegrators
from Basilisk.utilities import SimulationBaseClass, macros, simIncludeGravBody, vizSupport
from Basilisk.utilities.supportDataTools.dataFetcher import DataFile, get_path

# ---------------------------------------------------------------------------
# Path setup & Imports
# ---------------------------------------------------------------------------
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, "PythonModules"))

try:
    import perovsat_plugins.messaging
    from perovsat_plugins.permanentMagnet import PermanentMagnet
except ImportError as exc:
    raise ImportError(f"Compiled plugin modules not found.\nOriginal error: {exc}") from exc

from issOrbit import set_iss_orbit
from hysteresisFactory import HysteresisFactory

# ---------------------------------------------------------------------------
# Key parameters
# ---------------------------------------------------------------------------
MASS_KG          = 1.2
INERTIA_KGM2     = [[0.002, 0.0, 0.0],
                     [0.0,   0.002, 0.0],
                     [0.0,   0.0,   0.001]]

SIGMA_INIT       = [[0.2], [-0.1], [0.3]]
OMEGA_INIT_RADS  = [[0.05], [0.07], [0.02]]

DIPOLE_BODY_AM2  = np.array([0.0, 0.0, 0.15])

# ---- 1U CubeSat envelope constraint: rods must fit within a 100mm cube,
# so max usable length is ~95mm (leaves a few mm of installation margin). ----
ROD_DIAMETER_M   = 0.010   # 10 mm
ROD_LENGTH_M     = 0.095   # 95 mm (was 200mm -- too long for a 1U bus)

# ---- Choose duration here ----
# For 1‑hour test:
# SIM_DURATION_S = 3600.0
# TIMESTEP_S = 0.5
# RECORD_PERIOD_S = 1.0

# For 18‑day run:
SIM_DURATION_S   = 3600.0 * 24 * 50
TIMESTEP_S       = 5
RECORD_PERIOD_S  = 60.0

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
    # Adaptive (error-tolerance-controlled) integrator instead of fixed-step
    # RK4: sub-steps internally between task ticks so integration accuracy
    # is decoupled from TIMESTEP_S (see DEBUGGING.md #12). Must keep a
    # persistent Python reference -- SWIG does not keep this object alive
    # on its own, and an inline temporary gets GC'd before ExecuteSimulation
    # runs, leaving scObject with a dangling integrator pointer (segfault).
    integrator = svIntegrators.svIntegratorRKF45(scObject)
    scObject.setIntegrator(integrator)
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

    rec_period = macros.sec2nano(RECORD_PERIOD_S)
    magRec = magModule.envOutMsgs[0].recorder(rec_period)
    scSim.AddModelToTask("simTask", magRec)

    # Permanent magnet
    permMagnet = PermanentMagnet()
    permMagnet.ModelTag = "PermanentMagnet"
    permMagnet.magDipole_B = DIPOLE_BODY_AM2
    permMagnet.magFieldInMsg.subscribeTo(magModule.envOutMsgs[0])
    scObject.addDynamicEffector(permMagnet)
    scSim.AddModelToTask("simTask", permMagnet)

    # Hysteresis Rods – proven 8‑rod layout
    rod_factory = HysteresisFactory(scSim, scObject, magModule)

    rod_defs = [
        ("HystRod_Z1", [0.0, 0.0, 1.0], Z_JSON),
        ("HystRod_Z2", [0.0, 0.0, 1.0], Z_JSON),
        ("HystRod_X1", [1.0, 0.0, 0.0], XY_JSON),
        ("HystRod_X2", [1.0, 0.0, 0.0], XY_JSON),
        ("HystRod_Y1", [0.0, 1.0, 0.0], XY_JSON),
        ("HystRod_Y2", [0.0, 1.0, 0.0], XY_JSON),
        ("HystRod_D1", [ INV_SQRT2,  INV_SQRT2, 0.0], XY_JSON),
        ("HystRod_D2", [ INV_SQRT2, -INV_SQRT2, 0.0], XY_JSON),
    ]

    rods = {}
    print("\n" + "="*60)
    print("CREATING HYSTERESIS RODS")
    print("="*60)
    for tag, axis, json_path in rod_defs:
        rods[tag] = rod_factory.add_rod(
            length_m=ROD_LENGTH_M,
            diameter_m=ROD_DIAMETER_M,
            axis_B=axis,
            json_path=json_path,
            tag=tag,
        )
    
    print("\n" + "="*60)
    print(f"Total rods created: {len(rods)}")
    print("="*60 + "\n")

    # Recorders
    torque_recorders = {}
    for tag, rod in rods.items():
        rec = rod.torqueLogOutMsg.recorder(rec_period)
        scSim.AddModelToTask("simTask", rec)
        torque_recorders[tag] = rec

    hystRecorders = {
        "Z": rods["HystRod_Z1"].hysteresisDebugOutMsg.recorder(rec_period),
        "X": rods["HystRod_X1"].hysteresisDebugOutMsg.recorder(rec_period),
        "D": rods["HystRod_D1"].hysteresisDebugOutMsg.recorder(rec_period),
    }
    for rec in hystRecorders.values():
        scSim.AddModelToTask("simTask", rec)

    scStateRec = scObject.scStateOutMsg.recorder(rec_period)
    scSim.AddModelToTask("simTask", scStateRec)

    pmTorqueRec = permMagnet.cmdTorqueOutMsg.recorder(rec_period)
    scSim.AddModelToTask("simTask", pmTorqueRec)

    if vizSupport.vizFound:
        vizSupport.enableUnityVisualization(
            scSim,
            "simTask",
            scObject,
            saveFile=VIZARD_OUTPUT
        )

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(macros.sec2nano(SIM_DURATION_S))
    scSim.ExecuteSimulation()

    # Post‑simulation analysis
    print("\n" + "="*60)
    print("ROD TORQUE VERIFICATION")
    print("="*60)
    for tag, rec in torque_recorders.items():
        torque = np.array(rec.torqueRequestBody)
        if len(torque) > 0:
            torque_mag = np.linalg.norm(torque, axis=1)
            torque_mag = torque_mag[np.isfinite(torque_mag)]
            if len(torque_mag) > 0:
                avg_torque = np.mean(torque_mag)
                max_torque = np.max(torque_mag)
                print(f"{tag}: avg={avg_torque:.2e} Nm, max={max_torque:.2e} Nm")
            else:
                print(f"{tag}: ALL INF/NAN VALUES!")
        else:
            print(f"{tag}: NO DATA RECORDED!")
    print("="*60 + "\n")

    plot_hysteresis_loops(hystRecorders)
    plot_detumble_curve(scStateRec)
    plot_rod_torques(torque_recorders)
    plot_magnetic_field(magRec)
    plot_permanent_magnet_torque(pmTorqueRec)


def plot_hysteresis_loops(hystRecorders, filename="hysteresis_loop.png"):
    fig, axes = plt.subplots(1, 3, figsize=(16, 5))
    labels = {"Z": "Z-Axis Rod (Z1)", "X": "X-Axis Rod (X1)", "D": "Diagonal Rod (D1)"}

    for ax, key in zip(axes, ["Z", "X", "D"]):
        rec = hystRecorders[key]
        H = np.array(rec.H)
        M = np.array(rec.M)
        
        if len(H) == 0 or len(M) == 0:
            ax.text(0.5, 0.5, "NO DATA RECORDED", 
                   transform=ax.transAxes, ha='center', va='center')
            ax.set_title(f"{labels[key]} - NO DATA")
            continue
            
        finite_mask = np.isfinite(H) & np.isfinite(M)
        H_finite = H[finite_mask]
        M_finite = M[finite_mask]
        
        if len(H_finite) == 0:
            ax.text(0.5, 0.5, "ALL INF/NAN VALUES", 
                   transform=ax.transAxes, ha='center', va='center')
            ax.set_title(f"{labels[key]} - NO VALID DATA")
            continue
            
        ax.plot(H_finite, M_finite, color='blue', linewidth=0.8)
        ax.plot(H_finite[0], M_finite[0], 'go', label="Start")
        ax.plot(H_finite[-1], M_finite[-1], 'ro', label="End")
        ax.set_xlabel("H (A/m)")
        ax.set_ylabel("M (A/m)")
        ax.set_title(labels[key])
        ax.grid(True, linestyle='--', alpha=0.7)
        ax.legend()

    fig.suptitle("Flatley-Henretty Hysteresis Loops")
    plt.tight_layout()
    plt.savefig(filename, dpi=200)
    plt.close(fig)


def plot_detumble_curve(scStateRec, filename="detumble_curve.png"):
    t_s = np.array(scStateRec.times()) * 1.0e-9
    omega = np.array(scStateRec.omega_BN_B)

    if len(t_s) == 0:
        print("WARNING: No spacecraft state data recorded!")
        return

    omega_deg = np.degrees(omega)
    omega_mag_deg = np.degrees(np.linalg.norm(omega, axis=1))

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)

    # Use days if simulation is long, else hours
    if t_s[-1] > 3600*24:
        time_scale = 86400.0
        time_label = "Time (days)"
    else:
        time_scale = 3600.0
        time_label = "Time (hours)"

    t_plot = t_s / time_scale

    ax1.plot(t_plot, omega_deg[:, 0], label=r"$\omega_x$", linewidth=0.7)
    ax1.plot(t_plot, omega_deg[:, 1], label=r"$\omega_y$", linewidth=0.7)
    ax1.plot(t_plot, omega_deg[:, 2], label=r"$\omega_z$", linewidth=0.7)
    ax1.set_ylabel("Body rate (deg/s)")
    ax1.set_title("PMAC Detumble Curve – 8‑Rod HyMu80 Layout")
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.legend()

    ax2.plot(t_plot, omega_mag_deg, color='k', linewidth=1.0)
    ax2.set_xlabel(time_label)
    ax2.set_ylabel(r"$|\omega|$ (deg/s)")
    ax2.grid(True, linestyle='--', alpha=0.6)

    plt.tight_layout()
    plt.savefig(filename, dpi=200)
    plt.close(fig)

    np.savez("detumble_data.npz", t_s=t_s, omega=omega)

    print(f"\n{'='*60}")
    print("DETUMBLE RESULTS")
    print('='*60)
    print(f"Initial |omega|: {omega_mag_deg[0]:.4f} deg/s")
    print(f"Final   |omega|: {omega_mag_deg[-1]:.4f} deg/s  (t = {t_s[-1]/86400.0:.2f} days)")
    reduction = (1 - omega_mag_deg[-1]/omega_mag_deg[0])*100
    print(f"Reduction: {reduction:.1f}%")
    print('='*60 + "\n")


def plot_rod_torques(torque_recorders, filename="rod_torques.png"):
    n_rods = len(torque_recorders)
    n_cols = 4
    n_rows = (n_rods + n_cols - 1) // n_cols
    
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4*n_rows))
    if n_rows == 1:
        axes = axes.reshape(1, -1)
    axes = axes.flatten()
    
    for idx, (tag, rec) in enumerate(torque_recorders.items()):
        t_s = np.array(rec.times()) * 1.0e-9
        torque = np.array(rec.torqueRequestBody)
        
        if len(t_s) == 0:
            axes[idx].text(0.5, 0.5, f"{tag}\nNO DATA", 
                          transform=axes[idx].transAxes, ha='center', va='center')
            axes[idx].set_title(tag)
            continue
            
        if t_s[-1] > 3600*24:
            time_scale = 86400.0
            time_label = "Time (days)"
        else:
            time_scale = 3600.0
            time_label = "Time (hours)"
            
        t_plot = t_s / time_scale
        torque_mag = np.linalg.norm(torque, axis=1)
        
        finite_mask = np.isfinite(torque_mag)
        if not np.any(finite_mask):
            axes[idx].text(0.5, 0.5, f"{tag}\nALL INF/NAN", 
                          transform=axes[idx].transAxes, ha='center', va='center')
            axes[idx].set_title(tag)
            continue
            
        t_finite = t_plot[finite_mask]
        torque_finite = torque[finite_mask]
        torque_mag_finite = torque_mag[finite_mask]
        
        avg_torque = np.mean(torque_mag_finite)
        max_torque = np.max(torque_mag_finite)
        
        axes[idx].plot(t_finite, torque_finite[:, 0], label='x', linewidth=0.5)
        axes[idx].plot(t_finite, torque_finite[:, 1], label='y', linewidth=0.5)
        axes[idx].plot(t_finite, torque_finite[:, 2], label='z', linewidth=0.5)
        axes[idx].plot(t_finite, torque_mag_finite, 'k--', label='|τ|', linewidth=0.7)
        axes[idx].set_title(f"{tag}\navg={avg_torque:.2e} Nm, max={max_torque:.2e} Nm")
        axes[idx].set_xlabel(time_label)
        axes[idx].set_ylabel('Torque (Nm)')
        axes[idx].legend(fontsize=6)
        axes[idx].grid(True, alpha=0.3)
    
    for idx in range(len(torque_recorders), len(axes)):
        axes[idx].set_visible(False)
    
    plt.tight_layout()
    plt.savefig(filename, dpi=200)
    plt.close(fig)


def plot_magnetic_field(magRec, filename="magnetic_field.png"):
    t_s = np.array(magRec.times()) * 1.0e-9
    
    try:
        B = np.array(magRec.magField_N)
    except AttributeError:
        try:
            B = np.array(magRec.magneticField_N)
        except AttributeError:
            print("WARNING: Could not read magnetic field data")
            return
    
    if len(t_s) == 0:
        print("WARNING: No magnetic field data recorded!")
        return
        
    if t_s[-1] > 3600*24:
        time_scale = 86400.0
        time_label = "Time (days)"
    else:
        time_scale = 3600.0
        time_label = "Time (hours)"
        
    t_plot = t_s / time_scale
    B_mag = np.linalg.norm(B, axis=1)
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
    
    ax1.plot(t_plot, B[:, 0], label='Bx', linewidth=0.7)
    ax1.plot(t_plot, B[:, 1], label='By', linewidth=0.7)
    ax1.plot(t_plot, B[:, 2], label='Bz', linewidth=0.7)
    ax1.set_ylabel('B (T)')
    ax1.set_title('Magnetic Field Components (Inertial Frame)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)
    
    ax2.plot(t_plot, B_mag, 'k-', linewidth=1.0)
    ax2.axhline(y=np.mean(B_mag), color='r', linestyle='--', 
                label=f'Mean: {np.mean(B_mag):.1e} T')
    ax2.set_xlabel(time_label)
    ax2.set_ylabel('|B| (T)')
    ax2.set_title('Magnetic Field Magnitude')
    ax2.legend()
    ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(filename, dpi=200)
    plt.close(fig)
    
    print("\n" + "="*60)
    print("MAGNETIC FIELD ANALYSIS")
    print("="*60)
    print(f"Mean |B|: {np.mean(B_mag):.1e} T")
    print(f"Min |B|:  {np.min(B_mag):.1e} T")
    print(f"Max |B|:  {np.max(B_mag):.1e} T")
    print("="*60 + "\n")


def plot_permanent_magnet_torque(pmTorqueRec, filename="pm_torque.png"):
    t_s = np.array(pmTorqueRec.times()) * 1.0e-9
    torque = np.array(pmTorqueRec.torqueRequestBody)
    
    if len(t_s) == 0:
        print("WARNING: No permanent magnet torque data recorded!")
        return
        
    if t_s[-1] > 3600*24:
        time_scale = 86400.0
        time_label = "Time (days)"
    else:
        time_scale = 3600.0
        time_label = "Time (hours)"
        
    t_plot = t_s / time_scale
    torque_mag = np.linalg.norm(torque, axis=1)
    
    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(t_plot, torque[:, 0], label='τx', linewidth=0.7)
    ax.plot(t_plot, torque[:, 1], label='τy', linewidth=0.7)
    ax.plot(t_plot, torque[:, 2], label='τz', linewidth=0.7)
    ax.plot(t_plot, torque_mag, 'k--', label='|τ|', linewidth=1.0)
    ax.set_xlabel(time_label)
    ax.set_ylabel('Torque (Nm)')
    ax.set_title('Permanent Magnet Torque (For Reference)')
    ax.legend()
    ax.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(filename, dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    run()