"""Per-tick IMU stimulus taken from spacecraft truth state.

Fields follow ``psp_sample_imu_stimulus`` in perovsat-protocol so a later
encoder can serialize ``ImuStimulus`` without renaming anything. Only the gyro
is populated for now; nothing is encoded or transmitted yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from Basilisk.architecture import messaging, sysModel

# psp_sample_imu_stimulus rejects this sequence value.
_SEQUENCE_INVALID = 0xFFFFFFFF


@dataclass
class ImuStimulus:
    sequence: int
    time_ns: int
    gyro_rad_s: tuple[float, float, float]
    accel_m_s2: tuple[float, float, float] = (0.0, 0.0, 0.0)
    temperature_present: int = 0
    temperature_c: float = 0.0


class ImuStimulusEmitter(sysModel.SysModel):
    """Read ``omega_BN_B`` once per task tick and log it as a stimulus sample.

    Read-only: it subscribes to the spacecraft state and never feeds back into
    the dynamics. Add it after the spacecraft (negative priority) so each tick
    sees that tick's propagated state.
    """

    def __init__(self, cfg, output_dir: Path):
        super().__init__()
        self.ModelTag = "imuStimulus"
        self.scStateInMsg = messaging.SCStatesMsgReader()
        self.print_every = cfg.imu_print_every
        self.path = Path(output_dir) / "imu_stimulus.log"
        self.sequence = 0
        self.emitted = 0
        self.last: ImuStimulus | None = None
        self._file = None

    def Reset(self, current_time):
        if not self.scStateInMsg.isLinked():
            raise RuntimeError("imuStimulus.scStateInMsg is not linked to a spacecraft state")
        self.close()
        self._file = self.path.open("w")
        self._file.write("# time_s sequence gyro_x gyro_y gyro_z  (rad/s, body frame)\n")

    def UpdateState(self, current_time):
        state = self.scStateInMsg()
        sample = ImuStimulus(
            sequence=self.sequence,
            time_ns=current_time,
            gyro_rad_s=tuple(state.omega_BN_B),
        )
        self.last = sample
        self.emitted += 1

        wx, wy, wz = sample.gyro_rad_s
        line = f"{current_time * 1e-9:.9f} {sample.sequence} {wx:.9e} {wy:.9e} {wz:.9e}"
        self._file.write(line + "\n")
        if self.print_every and sample.sequence % self.print_every == 0:
            print(f"[imu] {line}")

        self.sequence = (self.sequence + 1) % _SEQUENCE_INVALID

    def close(self):
        if self._file is not None:
            self._file.close()
            self._file = None

    def summary(self):
        return [
            f"IMU stimulus samples: {self.emitted}",
            f"IMU stimulus log: {self.path}",
        ]
