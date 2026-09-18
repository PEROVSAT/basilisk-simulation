"""
sim/plotting.py
Shared plotting utilities.
"""

import os
import numpy as np
import matplotlib.pyplot as plt


def save_figure(fig, output_dir, filename, dpi=150):
    path = os.path.join(output_dir, filename)
    fig.tight_layout()
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    print(f"Saved: {path}")
    return path


def plot_detumble_curve(scStateRec, output_dir, filename="detumble_curve.png"):
    t_s = np.array(scStateRec.times()) * 1.0e-9
    omega = np.array(scStateRec.omega_BN_B)
    if len(t_s) == 0:
        return

    omega_deg = np.degrees(omega)
    omega_mag_deg = np.degrees(np.linalg.norm(omega, axis=1))

    if t_s[-1] > 3600 * 24:
        scale, label = 86400.0, "Time (days)"
    else:
        scale, label = 3600.0, "Time (hours)"
    t_plot = t_s / scale

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    ax1.plot(t_plot, omega_deg[:, 0], label=r"$\omega_x$", linewidth=0.7)
    ax1.plot(t_plot, omega_deg[:, 1], label=r"$\omega_y$", linewidth=0.7)
    ax1.plot(t_plot, omega_deg[:, 2], label=r"$\omega_z$", linewidth=0.7)
    ax1.set_ylabel("Body rate (deg/s)")
    ax1.set_title("PMAC Detumble Curve")
    ax1.grid(True, linestyle='--', alpha=0.6)
    ax1.legend()

    ax2.plot(t_plot, omega_mag_deg, color='k', linewidth=1.0)
    ax2.set_xlabel(label)
    ax2.set_ylabel(r"$|\omega|$ (deg/s)")
    ax2.grid(True, linestyle='--', alpha=0.6)

    save_figure(fig, output_dir, filename)
    reduction = (1 - omega_mag_deg[-1] / omega_mag_deg[0]) * 100
    print(f"\nDETUMBLE: {omega_mag_deg[0]:.3f} → {omega_mag_deg[-1]:.3f} deg/s "
          f"({reduction:+.1f}%)")


def plot_power_history(power_manager, output_dir, filename="power_system.png"):
    if not power_manager.history:
        return
    hist = power_manager.history
    t = np.array([h['time_s'] for h in hist]) / 3600.0

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    ax1.plot(t, [h['generation_w'] for h in hist], 'g-', label='Generation')
    ax1.plot(t, [h['consumption_w'] for h in hist], 'r-', label='Consumption')
    ax1.plot(t, [h['net_power_w'] for h in hist], 'b--', label='Net')
    ax1.axhline(0, color='k', linewidth=0.5)
    ax1.set_ylabel('Power (W)')
    ax1.set_title('Power Budget')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2.plot(t, [h['soc'] * 100 for h in hist], 'b-')
    ax2.axhline(20, color='r', linestyle='--', label='SAFE')
    ax2.axhline(40, color='orange', linestyle='--', label='LOW')
    ax2.set_xlabel('Time (hours)')
    ax2.set_ylabel('State of Charge (%)')
    ax2.set_ylim(0, 105)
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    save_figure(fig, output_dir, filename)


def plot_hysteresis_loops(hyst_recorders, output_dir, filename="hysteresis_loop.png"):
    n = len(hyst_recorders)
    if n == 0:
        return
    fig, axes = plt.subplots(1, n, figsize=(5 * n, 5))
    if n == 1:
        axes = [axes]

    for ax, (tag, rec) in zip(axes, hyst_recorders.items()):
        H = np.array(rec.H)
        M = np.array(rec.M)
        mask = np.isfinite(H) & np.isfinite(M)
        if not np.any(mask):
            ax.text(0.5, 0.5, "NO DATA", transform=ax.transAxes,
                    ha='center', va='center')
            continue
        H, M = H[mask], M[mask]
        ax.plot(H, M, 'b-', linewidth=0.8)
        ax.set_xlabel('H (A/m)')
        ax.set_ylabel('M (A/m)')
        ax.set_title(tag)
        ax.grid(True, alpha=0.5)

    fig.suptitle("Hysteresis Loops")
    save_figure(fig, output_dir, filename)


def plot_rod_torques(torque_recorders, output_dir, filename="rod_torques.png"):
    n = len(torque_recorders)
    if n == 0:
        return
    n_cols = 4
    n_rows = (n + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4 * n_rows))
    axes = axes.flatten() if n_rows > 1 else [axes]

    for idx, (tag, rec) in enumerate(torque_recorders.items()):
        t_s = np.array(rec.times()) * 1e-9
        torque = np.array(rec.torqueRequestBody)
        if len(t_s) == 0:
            continue
        t_days = t_s / 86400.0
        axes[idx].plot(t_days, torque[:, 0], label='x', linewidth=0.5)
        axes[idx].plot(t_days, torque[:, 1], label='y', linewidth=0.5)
        axes[idx].plot(t_days, torque[:, 2], label='z', linewidth=0.5)
        axes[idx].set_title(tag)
        axes[idx].set_xlabel('Time (days)')
        axes[idx].set_ylabel('Torque (Nm)')
        axes[idx].legend(fontsize=6)
        axes[idx].grid(True, alpha=0.3)

    for idx in range(n, len(axes)):
        axes[idx].set_visible(False)

    save_figure(fig, output_dir, filename)


def plot_magnetic_field(magRec, output_dir, filename="magnetic_field.png"):
    t_s = np.array(magRec.times()) * 1e-9
    try:
        B = np.array(magRec.magField_N)
    except AttributeError:
        try:
            B = np.array(magRec.magneticField_N)
        except AttributeError:
            return
    if len(t_s) == 0:
        return
    t_days = t_s / 86400.0
    B_mag = np.linalg.norm(B, axis=1)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8))
    ax1.plot(t_days, B[:, 0], label='Bx', linewidth=0.7)
    ax1.plot(t_days, B[:, 1], label='By', linewidth=0.7)
    ax1.plot(t_days, B[:, 2], label='Bz', linewidth=0.7)
    ax1.set_ylabel('B (T)')
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2.plot(t_days, B_mag, 'k-', linewidth=1.0)
    ax2.set_xlabel('Time (days)')
    ax2.set_ylabel('|B| (T)')
    ax2.grid(True, alpha=0.3)

    save_figure(fig, output_dir, filename)