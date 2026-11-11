"""Fixed-duration mission settings, independent of the Basilisk runtime."""
from dataclasses import dataclass
from perovsat.run_config import RunConfig
from perovsat.validation import positive


def nanoseconds(value):
    return round(value * 1_000_000_000)


@dataclass
class MissionConfig(RunConfig):
    name: str = 'mission'
    duration_s: float = 3 * 86400.0
    record_period_s: float = 10.0
    realtime: bool = True
    segment_s: float = 300.0
    control_s: float = 5.0

    def validate(self):
        super().validate()
        for name in ('segment_s', 'control_s'):
            positive(name, getattr(self, name))
        tick = nanoseconds(self.timestep_s)
        if tick < 1:
            raise ValueError('timestep_s must be at least one nanosecond')
        for name in ('duration_s', 'record_period_s', 'segment_s', 'control_s'):
            value = nanoseconds(getattr(self, name))
            if value < tick or value % tick:
                raise ValueError(f'{name} must be a positive multiple of timestep_s')
        if nanoseconds(self.segment_s) % nanoseconds(self.record_period_s):
            raise ValueError('segment_s must be a multiple of record_period_s')
