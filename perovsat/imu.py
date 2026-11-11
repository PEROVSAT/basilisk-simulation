"""Per-tick IMU stimulus from spacecraft truth, as a perovsat-protocol sample.

The C++ ``imuStimulus`` plugin fills a ``psp_sample`` with its IMU stimulus arm
each tick. This module logs that sample in rpm and, when a HITL bridge address
is configured, sends it to the bridge as a Sample frame and logs what the
emulated device reports back.
"""

from __future__ import annotations

import math
import threading
import time
from pathlib import Path

from Basilisk.architecture import sysModel

from perovsat.bridge import BridgeLink

# Samples stay in rad/s (protocol units); the log file and console use rpm.
RAD_S_PER_RPM = 2 * math.pi / 60

_FRAME_LOG = 3
_LOG_STATUS = 4
_STATUS_TIMEOUT_S = 2.0


def add_imu_stimulus(scSim, task_name, sc_state_msg, cfg, output_dir):
    """Add the protocol sample filler and its emitter after the spacecraft."""
    from perovsat_plugins.imuStimulus import ImuStimulus

    stimulus = ImuStimulus()
    stimulus.ModelTag = "imuStimulus"
    stimulus.scStateInMsg.subscribeTo(sc_state_msg)
    emitter = ImuStimulusEmitter(cfg, output_dir, stimulus)
    # After physics and recorders (priority 0); the filler runs before the
    # emitter, and both before the realtime pacer (-100).
    scSim.AddModelToTask(task_name, stimulus, -40)
    scSim.AddModelToTask(task_name, emitter, -50)
    return emitter


class ImuStimulusEmitter(sysModel.SysModel):
    """Log the filled sample each tick and optionally send it to the bridge.

    Holds the C++ ``ImuStimulus`` filler so SWIG does not free it while the
    simulation still points to it.
    """

    def __init__(self, cfg, output_dir: Path, stimulus):
        super().__init__()
        self.ModelTag = "imuStimulusEmitter"
        self.stimulus = stimulus
        self.print_every = cfg.imu_print_every
        self.bridge_address = cfg.imu_bridge
        self.destination = cfg.imu_destination
        self.source = cfg.imu_source
        self.path = Path(output_dir) / "imu_stimulus.log"
        self.bridge_log_path = Path(output_dir) / "bridge.log"
        self.emitted = 0
        self.frames_sent = 0
        self.link: BridgeLink | None = None
        self.status_before: str | None = None
        self.status_after: str | None = None
        self._file = None
        self._bridge_file = None
        self._lock = threading.Lock()
        self._status: str | None = None
        self._status_seen = threading.Event()
        self._request_id = 0

    def Reset(self, current_time):
        if not self.stimulus.scStateInMsg.isLinked():
            raise RuntimeError("imuStimulus.scStateInMsg is not linked to a spacecraft state")
        self.close()
        self._file = self.path.open("w")
        self._file.write("# time_s sequence gyro_x gyro_y gyro_z  (rpm, body frame)\n")
        if self.bridge_address:
            self._bridge_file = self.bridge_log_path.open("w")
            self.link = BridgeLink(self.bridge_address, self._on_frame)
            self._log(f"[bridge] connected to {self.bridge_address}; source {self.source}, "
                      f"sending IMU samples to device {self.destination}")
            self.status_before = self.request_status()

    def UpdateState(self, current_time):
        stimulus = self.stimulus
        if not stimulus.hasSample():
            raise RuntimeError("imuStimulus has not filled a sample; it must run before the emitter")
        sequence = stimulus.getSequence()
        wx, wy, wz = (stimulus.getGyro(axis) / RAD_S_PER_RPM for axis in range(3))
        # Six decimals: the sample is float32 (~7 significant digits).
        line = f"{current_time * 1e-9:.9f} {sequence} {wx:.6f} {wy:.6f} {wz:.6f}"
        self._file.write(line + "\n")
        self.emitted += 1
        if self.print_every and sequence % self.print_every == 0:
            print(f"[imu] {line}")
        if self.link is not None:
            frame = stimulus.sampleFrame(self.destination, self.source, time.time_ns())
            if not frame:
                raise RuntimeError(f"perovsat-protocol rejected IMU sample {sequence}")
            self.link.send(frame)
            self.frames_sent += 1

    def request_status(self) -> str | None:
        """Send GetStatus to the device and wait briefly for its status log."""
        from perovsat_plugins.imuStimulus import pspGetStatusFrame

        self._request_id += 1
        self._status_seen.clear()
        self.link.send(pspGetStatusFrame(self.destination, self.source, time.time_ns(),
                                         self._request_id))
        if not self._status_seen.wait(_STATUS_TIMEOUT_S):
            self._log(f"[bridge] no status reply from device {self.destination} "
                      f"within {_STATUS_TIMEOUT_S:g} s")
            return None
        return self._status

    def finish(self):
        """After a successful run, record what the device holds now."""
        if self.link is not None:
            self.status_after = self.request_status()

    def _on_frame(self, frame: bytes):
        """Bridge reader thread: log every frame the device sends."""
        from perovsat_plugins.imuStimulus import pspDescribeFrame

        if len(frame) < 21 or frame[2] != self.destination:
            return  # Bridge probes and other participants' traffic.
        text = pspDescribeFrame(frame)
        self._log(f"[device] {text}")
        if frame[19] == _FRAME_LOG and frame[20] == _LOG_STATUS:
            self._status = text
            self._status_seen.set()

    def _log(self, message: str):
        with self._lock:
            print(message, flush=True)
            if self._bridge_file is not None:
                self._bridge_file.write(message + "\n")
                self._bridge_file.flush()

    def close(self):
        if self.link is not None:
            self.link.close()
            self.link = None
        with self._lock:
            for name in ("_file", "_bridge_file"):
                handle = getattr(self, name)
                if handle is not None:
                    handle.close()
                    setattr(self, name, None)

    def summary(self):
        lines = [
            f"IMU stimulus samples: {self.emitted}",
            f"IMU stimulus log: {self.path}",
        ]
        if self.bridge_address:
            lines += [
                f"HITL bridge: {self.bridge_address} (source {self.source} -> device {self.destination})",
                f"IMU sample frames sent: {self.frames_sent}",
                f"Device status before: {self.status_before or 'no reply'}",
                f"Device status after: {self.status_after or 'no reply'}",
                f"Bridge log: {self.bridge_log_path}",
            ]
        return lines
