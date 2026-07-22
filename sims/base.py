import os
import sys
import numpy as np
import matplotlib.pyplot as plt

from Basilisk import __path__
from Basilisk.architecture import sysModel
from Basilisk.simulation import magneticFieldWMM, spacecraft, svIntegrators
from Basilisk.utilities import SimulationBaseClass, macros, vizSupport
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
from solarSystemFactory import setup_solar_system, wire_wmm_epoch

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

# Real UTC epoch the sim starts at -- drives Earth's rotational phase (and
# therefore which longitude the orbit's initial true anomaly sits over) and
# the WMM secular-variation date, via solarSystemFactory.py. Swap between the
# two presets below to compare a summer vs. winter launch; same year, so the
# dominant difference is Earth's rotation state at insertion rather than WMM
# secular drift (that term matters more for epochs years apart).
EPOCH_UTC_SUMMER = "2026 JUN 21 12:00:00.0 (UTC)"
EPOCH_UTC_WINTER = "2026 DEC 21 12:00:00.0 (UTC)"
EPOCH_UTC        = EPOCH_UTC_SUMMER

# 8-rod HyMu80 PMAC layout. Must fit a 1U (100mm) envelope. The prior 10mm
# diameter gave L/D=9.5, BELOW the L/D>10 threshold that
# hysteresisFactory.calculate_geometry()'s own Bozorth demagnetization-factor
# formula warns is required for validity -- Nd swings by ~13x between
# L/D=9.5 and L/D=47.5 (0.0216 -> 0.0016), so a sub-10 ratio isn't just
# "less accurate," it's outside the regime the approximation is for. 2mm
# also matches realistic HyMu80 flight-hardware proportions (thin, long
# rods) much better than 10mm did.
# NOTE: the hysteresis_configs/*.json Bs/Br/Hc values are labeled "effective
# as-installed" for demagnetization but the Flatley-Henretty model doesn't
# runtime-correct them from Nd (see hysteresisFactory.py) -- they weren't
# re-derived for this geometry, so treat them as provisional too.
ROD_DIAMETER_M   = 0.002   # 2 mm
ROD_LENGTH_M     = 0.095   # 95 mm (200mm was checked in at one point and
                            # physically cannot fit a 1U bus)

# ---- Choose duration here ----
# For 1‑hour test:
# SIM_DURATION_S = 3600.0
# TIMESTEP_S = 0.5
# RECORD_PERIOD_S = 1.0

# For 18‑day run:
SIM_DURATION_S   = 3600.0 * 24 * 50
TIMESTEP_S       = 5
RECORD_PERIOD_S  = 60.0

# Console print period for the OrientationMonitor — coarse on purpose so the
# 18-day run doesn't spam stdout.
PRINT_PERIOD_S   = 3600.0

VIZARD_OUTPUT    = os.path.splitext(__file__)[0]

_configs_dir = os.path.join(_root, "hysteresis_configs")
Z_JSON  = os.path.join(_configs_dir, "hymu80_z_axis.json")
XY_JSON = os.path.join(_configs_dir, "hymu80_xy_axis.json")

INV_SQRT2 = 0.70710678118654752


class OrientationMonitor(sysModel.SysModel):
    """
    Prints sim time and attitude MRP (sigma_BN) to the console on its own
    coarse task. Independent of Vizard, so the console trace can be diffed
    against Vizard's playback to isolate whether an orientation discrepancy
    is in the dynamics or in Vizard's rendering.
    """

    def __init__(self, scStateOutMsg):
        super().__init__()
        self.ModelTag = "OrientationMonitor"
        self.scStateOutMsg = scStateOutMsg

    def UpdateState(self, currentSimNanos):
        state = self.scStateOutMsg.read()
        t_s = currentSimNanos * macros.NANO2SEC
        sigma = state.sigma_BN
        omega = state.omega_BN_B
        omega_deg = np.degrees(omega)
        omega_mag_deg = np.degrees(np.linalg.norm(omega))
        print(
            f"t={t_s:10.1f}s  sigma_BN=[{sigma[0]:+.4f}, {sigma[1]:+.4f}, {sigma[2]:+.4f}]"
            f"  omega_BN_B=[{omega_deg[0]:+.4f}, {omega_deg[1]:+.4f}, {omega_deg[2]:+.4f}] deg/s"
            f"  |omega|={omega_mag_deg:.4f} deg/s"
        )


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

    # Solar system gravity (Earth + Sun), anchored to a real UTC epoch so
    # Earth's rotational phase at insertion -- and hence the WMM field trace
    # along the orbit -- reflects the actual launch date.
    gravFactory, spiceObject = setup_solar_system(scSim, scObject, "simTask", EPOCH_UTC)
    set_iss_orbit(scObject, gravFactory.gravBodies["earth"].mu)

    # WMM
    magModule = magneticFieldWMM.MagneticFieldWMM()
    magModule.ModelTag = "WMM"
    magModule.configureWMMFile(str(get_path(DataFile.MagneticFieldData.WMM)))
    magModule.addSpacecraftToModel(scObject.scStateOutMsg)
    wire_wmm_epoch(magModule, gravFactory, spiceObject)
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

    # Console orientation/timestamp monitor, on its own coarse task so it
    # doesn't run 3.1M times over the 18-day sim.
    dynProcess.addTask(scSim.CreateNewTask("printTask", macros.sec2nano(PRINT_PERIOD_S)))
    orientationMonitor = OrientationMonitor(scObject.scStateOutMsg)
    scSim.AddModelToTask("printTask", orientationMonitor)

    # Vizard — disabled by default for this long (18-day, 3.1M-step) headless
    # analysis run. Writing a per-step binary Vizard frame for that many steps
    # is an I/O bottleneck unrelated to the physics; use a short-duration run
    # (see wmm_pointing.py / dampening_test.py) for actual Vizard playback.
    if vizSupport.vizFound and os.environ.get("PEROVSAT_ENABLE_VIZ"):
        vizSupport.enableUnityVisualization(
            scSim, "simTask", scObject, saveFile=VIZARD_OUTPUT
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