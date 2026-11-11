"""Validate persisted mission telemetry without loading the whole run into memory."""
import argparse
import json
from pathlib import Path

import numpy as np

from perovsat.mission_config import nanoseconds


def validate_output(directory):
    directory = Path(directory)
    manifest = json.loads((directory/'manifest.json').read_text())
    period = nanoseconds(manifest['config']['record_period_s'])
    samples = 0
    expected = 0
    keys = None
    for segment in manifest['segments']:
        path = directory/segment['file']
        if path.resolve().parent != directory.resolve():
            raise ValueError('segment must be inside the mission directory')
        with np.load(path, allow_pickle=False) as data:
            if keys is None:
                keys = set(data.files)
            if set(data.files) != keys:
                raise ValueError('inconsistent telemetry channels')
            times = data['time_ns']
            if (not len(times) or times[0] != expected
                    or np.any(np.diff(times) != period)):
                raise ValueError('missing or duplicated timestamps')
            for key in data.files:
                if len(data[key]) != len(times) or not np.all(np.isfinite(data[key])):
                    raise ValueError(f'invalid channel: {key}')
            if not np.allclose(data['t_s'], times*1e-9, rtol=0, atol=1e-9):
                raise ValueError('inconsistent time units')
            if (len(times) != segment['samples'] or data['t_s'][0] != segment['first_s']
                    or data['t_s'][-1] != segment['last_s']):
                raise ValueError('segment metadata mismatch')
            if np.any((data['soc'] < -1e-9) | (data['soc'] > 1+1e-9)):
                raise ValueError('battery state of charge outside [0, 1]')
            samples += len(times)
            expected = int(times[-1])+period
    if samples != manifest['samples']:
        raise ValueError('manifest sample count mismatch')
    if manifest['status'] == 'complete':
        duration = manifest['config']['duration_s']
        if (nanoseconds(manifest['completed_s']) != nanoseconds(duration)
                or samples != nanoseconds(duration)//period+1):
            raise ValueError('incomplete mission marked complete')
    return {'status': manifest['status'], 'completed_s': manifest['completed_s'],
            'samples': samples, 'segments': len(manifest['segments']),
            'max_buffer_samples': manifest['max_buffer_samples'],
            'statistics': manifest['statistics'], 'timing': manifest.get('timing', {}),
            'wall_elapsed_s_including_setup': manifest.get('wall_elapsed_s_including_setup')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory')
    print(json.dumps(validate_output(parser.parse_args().directory), indent=2))
