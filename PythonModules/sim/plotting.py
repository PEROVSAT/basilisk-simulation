"""
sim/plotting.py
Shared plotting utilities (SimLog + output_dir).
"""

from __future__ import annotations

import os

import matplotlib.pyplot as plt
import numpy as np

from sim.log import SimLog


def save_figure(fig, output_dir, filename, dpi=150):
    path = os.path.join(output_dir, filename)
    fig.tight_layout()
    fig.savefig(path, dpi=dpi)
    plt.close(fig)
    print(f"Saved: {path}")
    return path


def _time_scale(t_s: np.ndarray) -> tuple[float, str]:
    if t_s[-1] > 86400:
        return 86400.0, "Time (days)"
    return 3600.0, "Time (hours)"


def plot_detumble_curve(log: SimLog, output_dir, filename="detumble_curve.png"):
    att = log.attitude
    t_s = att.t
    if t_s is None or len(t_s) == 0:
        return

    omega_deg = att.omega_deg
    omega_mag_deg = att.omega_mag_deg
    if omega_deg is None or omega_mag_deg is None:
        return

    scale, label = _time_scale(t_s)
    t_plot = t_s / scale

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    ax1.plot(t_plot, omega_deg[:, 0], label=r"$\omega_x$", linewidth=0.7)
    ax1.plot(t_plot, omega_deg[:, 1], label=r"$\omega_y$", linewidth=0.7)
    ax1.plot(t_plot, omega_deg[:, 2], label=r"$\omega_z$", linewidth=0.7)
    ax1.set_ylabel("Body rate (deg/s)")
    ax1.set_title("PMAC Detumble Curve")
    ax1.grid(True, linestyle="--", alpha=0.6)
    ax1.legend()

    ax2.plot(t_plot, omega_mag_deg, color="k", linewidth=1.0)
    ax2.set_xlabel(label)
    ax2.set_ylabel(r"$|\omega|$ (deg/s)")
    ax2.grid(True, linestyle="--", alpha=0.6)

    save_figure(fig, output_dir, filename)
    reduction = (1 - omega_mag_deg[-1] / omega_mag_deg[0]) * 100
    print(
        f"\nDETUMBLE: {omega_mag_deg[0]:.3f} → {omega_mag_deg[-1]:.3f} deg/s "
        f"({reduction:+.1f}%)"
    )


def plot_power_history(log: SimLog, output_dir, filename="power_system.png"):
    pwr = log.power
    t_s = pwr.t
    if t_s is None or len(t_s) == 0:
        return

    gen = pwr.generation_w
    con = pwr.consumption_w
    net = pwr.net_w
    soc = pwr.soc
    if gen is None or con is None or net is None or soc is None:
        return

    t = t_s / 3600.0

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True)
    ax1.plot(t, gen, "g-", label="Generation", linewidth=0.8)
    ax1.plot(t, con, "r-", label="Consumption", linewidth=0.8)
    ax1.plot(t, net, "b--", label="Net", linewidth=0.8)
    ax1.axhline(0, color="k", linewidth=0.5)
    ax1.set_ylabel("Power (W)")
    ax1.set_title("Power Budget")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2.plot(t, soc * 100, "b-", linewidth=0.8)
    ax2.axhline(20, color="r", linestyle="--", label="SAFE")
    ax2.axhline(40, color="orange", linestyle="--", label="LOW")
    ax2.set_xlabel("Time (hours)")
    ax2.set_ylabel("State of Charge (%)")
    ax2.set_ylim(0, 105)
    ax2.legend()
    ax2.grid(True, alpha=0.3)

    save_figure(fig, output_dir, filename)


def plot_power_by_sink(log: SimLog, output_dir, filename="power_by_sink.png"):
    pwr = log.power
    t_s = pwr.t
    sinks = pwr.sinks
    if t_s is None or len(t_s) == 0 or not sinks:
        return

    t = t_s / 3600.0
    fig, ax = plt.subplots(figsize=(12, 5))
    for name, load_w in sinks.items():
        ax.plot(t, load_w, label=name, linewidth=0.8)
    ax.set_xlabel("Time (hours)")
    ax.set_ylabel("Load (W)")
    ax.set_title("Power by sink")
    ax.legend(fontsize=8)
    ax.grid(True, alpha=0.3)
    save_figure(fig, output_dir, filename)


def plot_hysteresis_loops(log: SimLog, output_dir, filename="hysteresis_loop.png"):
    rods = [
        rod
        for rod in log.rods.values()
        if rod.H is not None and rod.M is not None
    ]
    if not rods:
        return

    n = len(rods)
    n_cols = min(4, n)
    n_rows = (n + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(5 * n_cols, 5 * n_rows))
    axes = np.atleast_1d(axes).flatten()

    for ax, rod in zip(axes, rods):
        H = np.ravel(np.asarray(rod.H, dtype=float))
        M = np.ravel(np.asarray(rod.M, dtype=float))
        n_pts = min(len(H), len(M))
        if n_pts == 0:
            ax.text(
                0.5,
                0.5,
                "NO DATA",
                transform=ax.transAxes,
                ha="center",
                va="center",
            )
            ax.set_title(rod.tag)
            continue
        H, M = H[:n_pts], M[:n_pts]
        mask = np.isfinite(H) & np.isfinite(M)
        if not np.any(mask):
            ax.text(
                0.5,
                0.5,
                "NO DATA",
                transform=ax.transAxes,
                ha="center",
                va="center",
            )
            ax.set_title(rod.tag)
            continue
        ax.plot(H[mask], M[mask], "b-", linewidth=0.8)
        ax.set_xlabel("H (A/m)")
        ax.set_ylabel("M (A/m)")
        ax.set_title(rod.tag)
        ax.grid(True, alpha=0.5)

    for ax in axes[n:]:
        ax.set_visible(False)

    fig.suptitle("Hysteresis Loops")
    save_figure(fig, output_dir, filename)


def plot_rod_torques(log: SimLog, output_dir, filename="rod_torques.png"):
    entries = [
        (rod.tag, rod.torque_B)
        for rod in log.rods.values()
        if rod.torque_B is not None and len(rod.torque_B) > 0
    ]
    if not entries:
        return

    t_s = log.t
    if t_s is None or len(t_s) == 0:
        return
    t_days = t_s / 86400.0

    n = len(entries)
    n_cols = 4
    n_rows = (n + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(16, 4 * n_rows))
    axes = np.atleast_1d(axes).flatten()

    for idx, (tag, torque) in enumerate(entries):
        n_pts = min(len(t_days), len(torque))
        if n_pts == 0:
            continue
        t_plot = t_days[:n_pts]
        tau = np.asarray(torque[:n_pts])
        axes[idx].plot(t_plot, tau[:, 0], label="x", linewidth=0.5)
        axes[idx].plot(t_plot, tau[:, 1], label="y", linewidth=0.5)
        axes[idx].plot(t_plot, tau[:, 2], label="z", linewidth=0.5)
        axes[idx].set_title(tag)
        axes[idx].set_xlabel("Time (days)")
        axes[idx].set_ylabel("Torque (Nm)")
        axes[idx].legend(fontsize=6)
        axes[idx].grid(True, alpha=0.3)

    for idx in range(n, len(axes)):
        axes[idx].set_visible(False)

    save_figure(fig, output_dir, filename)


def plot_magnetic_field(log: SimLog, output_dir, filename="magnetic_field.png"):
    mag = log.mag
    t_s = mag.t
    B = mag.B_N
    if t_s is None or len(t_s) == 0 or B is None or len(B) == 0:
        return

    t_days = t_s / 86400.0
    B_mag = mag.B_mag
    if B_mag is None:
        B_mag = np.linalg.norm(B, axis=1)

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), sharex=True)
    ax1.plot(t_days, B[:, 0], label="Bx", linewidth=0.7)
    ax1.plot(t_days, B[:, 1], label="By", linewidth=0.7)
    ax1.plot(t_days, B[:, 2], label="Bz", linewidth=0.7)
    ax1.set_ylabel("B (T)")
    ax1.legend()
    ax1.grid(True, alpha=0.3)

    ax2.plot(t_days, B_mag, "k-", linewidth=1.0)
    ax2.set_xlabel("Time (days)")
    ax2.set_ylabel("|B| (T)")
    ax2.grid(True, alpha=0.3)

    save_figure(fig, output_dir, filename)
