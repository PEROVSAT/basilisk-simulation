"""
plotting_utils.py
PMAC-specific plotting helpers (hysteresis loops, detumble curve, rod
torques, magnetic field, permanent-magnet torque). Moved out of base.py
unchanged -- these are specific to the detumble/PMAC experiment, not part of
the generic experiment scaffolding, so they live next to the experiment that
uses them rather than in ExperimentBase itself. Import what you need instead
of copy-pasting into a new experiment file.
"""

import numpy as np
import matplotlib.pyplot as plt


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

    if t_s[-1] > 3600 * 24:
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
    ax1.set_title("PMAC Detumble Curve - 8-Rod HyMu80 Layout")
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
    print('=' * 60)
    print(f"Initial |omega|: {omega_mag_deg[0]:.4f} deg/s")
    print(f"Final   |omega|: {omega_mag_deg[-1]:.4f} deg/s  (t = {t_s[-1]/86400.0:.2f} days)")
    reduction = (1 - omega_mag_deg[-1] / omega_mag_deg[0]) * 100
    print(f"Reduction: {reduction:.1f}%")
    print('=' * 60 + "\n")


def plot_rod_torques(torque_recorders, filename="rod_torques.png"):
    n_rods = len(torque_recorders)
    n_cols = 4
    n_rows = (n_rods + n_cols - 1) // n_cols

    fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4 * n_rows))
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

        if t_s[-1] > 3600 * 24:
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
        axes[idx].plot(t_finite, torque_mag_finite, 'k--', label='|tau|', linewidth=0.7)
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

    if t_s[-1] > 3600 * 24:
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


def plot_permanent_magnet_torque(pmTorqueRec, filename="pm_torque.png"):
    t_s = np.array(pmTorqueRec.times()) * 1.0e-9
    torque = np.array(pmTorqueRec.torqueRequestBody)

    if len(t_s) == 0:
        print("WARNING: No permanent magnet torque data recorded!")
        return

    if t_s[-1] > 3600 * 24:
        time_scale = 86400.0
        time_label = "Time (days)"
    else:
        time_scale = 3600.0
        time_label = "Time (hours)"

    t_plot = t_s / time_scale
    torque_mag = np.linalg.norm(torque, axis=1)

    fig, ax = plt.subplots(figsize=(10, 6))
    ax.plot(t_plot, torque[:, 0], label='taux', linewidth=0.7)
    ax.plot(t_plot, torque[:, 1], label='tauy', linewidth=0.7)
    ax.plot(t_plot, torque[:, 2], label='tauz', linewidth=0.7)
    ax.plot(t_plot, torque_mag, 'k--', label='|tau|', linewidth=1.0)
    ax.set_xlabel(time_label)
    ax.set_ylabel('Torque (Nm)')
    ax.set_title('Permanent Magnet Torque (For Reference)')
    ax.legend()
    ax.grid(True, alpha=0.3)

    plt.tight_layout()
    plt.savefig(filename, dpi=200)
    plt.close(fig)
