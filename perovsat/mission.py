"""Fixed-duration execution with bounded recorder buffers and persisted telemetry."""
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
import time
import warnings

import numpy as np

from perovsat import config
from perovsat.mission_config import MissionConfig, nanoseconds
from perovsat.mission_io import atomic_json, atomic_npz, json_value, recorder_list, source_info, telemetry
from perovsat.simulation import PerovSatSimulation
from perovsat.vizard import wait_for_vizard


class MissionRunner:
    """One mission per instance. Saved segments are telemetry, not restart state."""
    def __init__(self, cfg: MissionConfig):
        self.config = cfg
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        self.output_dir = Path(cfg.output_dir) if cfg.output_dir else Path('experiments/mission/output')/stamp
        self.completed_s = 0.0
        self._stop = False
        self._started = False
        self.sim = None
        self.manifest = {}
        self._last_time_ns = None
        self._last_eclipsed = None
        self._last_report = 0.0
        self._wall_start = None

    def request_stop(self):
        self._stop = True

    def _stop_requested(self):
        return self._stop

    def run(self):
        if self._started:
            raise RuntimeError('mission instances support one run')
        self.config.validate()
        config.validate_vehicle()
        self._started = True
        # Never replace previous results, even when the directory is empty.
        self.output_dir.mkdir(parents=True, exist_ok=False)
        cfg = self.config
        self.manifest = {
            'schema_version': 1, 'status': 'initializing',
            'started_utc': datetime.now(timezone.utc).isoformat(),
            'config': json_value(asdict(cfg)),
            'vehicle': {name: json_value(getattr(config, name)) for name in dir(config)
                        if name.isupper() and not name.startswith('_')},
            'source': source_info(), 'completed_s': 0.0, 'samples': 0,
            'segments': [], 'max_buffer_samples': 0, 'statistics': {},
        }
        self._write_status()
        self._wall_start = time.monotonic()
        try:
            # Reuse the exact existing vehicle construction and retain all owners.
            self.sim = PerovSatSimulation(cfg)
            self.sim.output_dir = self.output_dir
            self.sim._build()
            self.sim.scSim.SetProgressBar(False)
            if cfg.vizard_live:
                self.manifest['status'] = 'waiting for Vizard'
                self._write_status()
                wait_for_vizard(cfg.vizard_address, cfg.vizard_timeout_s)
            self.sim.scSim.InitializeSimulation()
            self.manifest['status'] = 'running'
            self._write_status()
            duration = nanoseconds(cfg.duration_s)
            control = nanoseconds(cfg.control_s)
            segment = nanoseconds(cfg.segment_s)
            current = 0
            next_segment = segment
            while current < duration and not self._stop_requested():
                target = min(current + control, next_segment, duration)
                self.sim.scSim.ConfigureStopTime(target)
                self.sim.scSim.ExecuteSimulation()
                actual = int(self.sim.scSim.TotalSim.CurrentNanos)
                if actual != target:
                    raise RuntimeError(f'simulation stopped at {actual} ns, expected {target} ns')
                current = target
                self.completed_s = current / 1_000_000_000
                self.manifest['completed_s'] = self.completed_s
                self.manifest['max_buffer_samples'] = max(
                    self.manifest['max_buffer_samples'], len(self.sim.log.t))
                if current >= next_segment or current == duration:
                    self._save_segment()
                    next_segment += segment
                self._progress()
            self._save_segment()
            self.manifest['status'] = 'complete' if current == duration else 'interrupted'
        except KeyboardInterrupt:
            self.manifest['status'] = 'interrupted'
            self._save_partial_best_effort()
        except Exception as exc:
            self.manifest['status'] = 'failed'
            pacer = self.sim.pacer if self.sim is not None else None
            reason = pacer.failure if pacer is not None and pacer.failure else str(exc)
            self.manifest['error'] = f'{type(exc).__name__}: {reason}'
            try:
                self._write_status()
            except OSError as write_error:
                warnings.warn(f'Could not update failure manifest: {write_error}')
            raise
        finally:
            # The status file only claims completed chunks/steps; no silent resume.
            if self.manifest['status'] != 'failed':
                self._write_status()
        self._progress(force=True)
        return self.manifest

    def _save_partial_best_effort(self):
        try:
            self._save_segment()
        except Exception as exc:
            self.manifest['partial_save_error'] = f'{type(exc).__name__}: {exc}'

    def _save_segment(self):
        if self.sim is None or self.sim.log is None or not len(self.sim.log.t):
            return
        arrays = telemetry(self.sim.log)
        times = arrays['time_ns']
        period = nanoseconds(self.config.record_period_s)
        expected_first = 0 if self._last_time_ns is None else self._last_time_ns + period
        if int(times[0]) != expected_first or np.any(np.diff(times) != period):
            raise ValueError('missing or duplicated telemetry timestamps')
        name = f'telemetry-{len(self.manifest["segments"]):06d}.npz'
        atomic_npz(self.output_dir/name, arrays)
        self.manifest['segments'].append({'file': name, 'samples': len(times),
            'first_s': float(arrays['t_s'][0]), 'last_s': float(arrays['t_s'][-1])})
        self.manifest['samples'] += len(times)
        self._last_time_ns = int(times[-1])
        self._statistics(arrays)
        # Persist the manifest before discarding any recorder data.
        self._write_status()
        for recorder in recorder_list(self.sim.log):
            recorder.clear()

    def _statistics(self, arrays):
        stats = self.manifest['statistics']
        radius = np.linalg.norm(arrays['position_N_m'], axis=1)/1000
        for key, values in (('soc', arrays['soc']), ('orbit_radius_km', radius)):
            stats[f'min_{key}'] = min(stats.get(f'min_{key}', float('inf')), float(np.min(values)))
            stats[f'max_{key}'] = max(stats.get(f'max_{key}', -float('inf')), float(np.max(values)))
        stats['last_sample_s'] = float(arrays['t_s'][-1])
        stats['last_soc'] = float(arrays['soc'][-1])
        stats['last_body_rate_rad_s'] = float(np.linalg.norm(arrays['omega_B_rad_s'][-1]))
        eclipsed = arrays['illumination'] < .5
        transitions = int(np.count_nonzero(np.diff(eclipsed)))
        if self._last_eclipsed is not None:
            transitions += int(bool(eclipsed[0]) != self._last_eclipsed)
        self._last_eclipsed = bool(eclipsed[-1])
        stats['sampled_eclipse_transitions'] = stats.get('sampled_eclipse_transitions', 0) + transitions

    def _write_status(self):
        self.manifest['updated_utc'] = datetime.now(timezone.utc).isoformat()
        if self._wall_start is not None:
            self.manifest['wall_elapsed_s_including_setup'] = time.monotonic() - self._wall_start
        if self.sim is not None and self.sim.pacer is not None:
            pacer = self.sim.pacer
            self.manifest['timing'] = {'paced_wall_s': pacer.elapsed_s,
                'max_lag_s': pacer.max_lag_s, 'overrun_ticks': pacer.overruns,
                'max_tick_work_s': pacer.max_work_s}
        atomic_json(self.output_dir/'manifest.json', self.manifest)
        lines = [f'Mission: {self.config.name}', f'Status: {self.manifest["status"]}',
                 f'Requested duration: {self.config.duration_s:g} s',
                 f'Completed execution: {self.manifest["completed_s"]:g} s',
                 f'Persisted samples: {self.manifest["samples"]}',
                 f'Telemetry segments: {len(self.manifest["segments"])}',
                 f'Maximum buffered samples: {self.manifest["max_buffer_samples"]}']
        lines.extend(f'{k}: {v}' for k, v in self.manifest['statistics'].items())
        lines.extend(f'{k}: {v}' for k, v in self.manifest.get('timing', {}).items())
        if 'error' in self.manifest:
            lines.append(self.manifest['error'])
        temporary = self.output_dir/'summary.txt.tmp'
        temporary.write_text('\n'.join(lines)+'\n', encoding='utf-8')
        temporary.replace(self.output_dir/'summary.txt')

    def _progress(self, force=False):
        now = time.monotonic()
        if force or now - self._last_report >= 5:
            stats = self.manifest['statistics']
            soc = stats.get('last_soc')
            label = 'pending' if soc is None else f'{100*soc:.1f}%'
            lag = self.manifest.get('timing', {}).get('max_lag_s', 0)
            print(f'Mission {100*self.completed_s/self.config.duration_s:.2f}% | '
                  f'{self.completed_s:g}/{self.config.duration_s:g} s | '
                  f'saved SOC {label} | max lag {lag:.3f} s | '
                  f'{self.manifest["status"]}', flush=True)
            self._last_report = now
