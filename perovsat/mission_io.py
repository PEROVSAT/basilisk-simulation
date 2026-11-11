"""Telemetry snapshots and atomic files for the mission runner."""
from dataclasses import asdict, is_dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess

import numpy as np


def json_value(value):
    if is_dataclass(value):
        return json_value(asdict(value))
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, Path):
        return str(value)
    return value


def atomic_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    with temporary.open('w', encoding='utf-8') as stream:
        json.dump(json_value(value), stream, indent=2, allow_nan=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def source_info():
    root = Path(__file__).resolve().parents[1]
    paths = []
    for folder in ('perovsat', 'ExternalModules', 'messages', 'experiments/mission'):
        paths.extend(p for p in (root/folder).rglob('*')
                     if p.is_file() and p.suffix in ('.py', '.cpp', '.h', '.i'))
    paths.extend(root/name for name in ('Dockerfile', 'pyproject.toml', 'CMakeLists.txt'))
    try:
        revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root,
                                           stderr=subprocess.DEVNULL, timeout=5).decode().strip()
    except (OSError, subprocess.SubprocessError):
        revision = None
    return {'git_revision': revision, 'sha256': {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(paths)}}


def recorder_list(log):
    r = log._recorders
    return [r.scState, r.environment.mag, r.environment.eclipse,
            r.pmac.pmTorque, r.power.battery, *r.pmac.rodTorques.values(),
            *r.pmac.hysteresis.values(), *r.power.panels.values(), *r.power.sinks.values()]


def telemetry(log):
    log.validate()
    arrays = {
        'time_ns': np.asarray(log._recorders.scState.times()), 't_s': log.t,
        'position_N_m': log.attitude.r_BN_N,
        'velocity_N_m_s': np.asarray(log._recorders.scState.v_BN_N),
        'sigma_BN': log.attitude.sigma_BN, 'omega_B_rad_s': log.attitude.omega_B,
        'magnetic_field_N_T': log.mag.B_N,
        'permanent_magnet_torque_B_Nm': log.perm_magnet_torque,
        'battery_J': log.power.stored_ws, 'soc': log.power.soc,
        'generation_W': log.power.generation_w, 'consumption_W': log.power.consumption_w,
        'net_power_W': log.power.net_w, 'illumination': log.power.shadow_factor,
    }
    for name, values in log.power.panels.items():
        arrays[f'panel_{name}_W'] = values
    for name, values in log.power.sinks.items():
        arrays[f'load_{name}_W'] = values
    for name, rod in log.rods.items():
        arrays[f'{name}_torque_B_Nm'] = rod.torque_B
        arrays[f'{name}_H_A_m'] = rod.H
        arrays[f'{name}_M_A_m'] = rod.M
    for name, values in arrays.items():
        if len(values) != len(log.t) or not np.all(np.isfinite(values)):
            raise ValueError(f'invalid telemetry: {name}')
    return arrays


def atomic_npz(path, arrays):
    temporary = path.with_suffix('.npz.tmp')
    with temporary.open('wb') as stream:
        np.savez_compressed(stream, **arrays)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)
