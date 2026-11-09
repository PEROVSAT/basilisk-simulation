"""IMU stimulus: protocol sample filling, sequencing, bridge link, no physics feedback."""

import importlib.util
from pathlib import Path
import socket
import struct
import tempfile
import threading
import unittest

import numpy as np


class ImuConfigTests(unittest.TestCase):
    def test_print_every_validation(self):
        from perovsat.run_config import RunConfig

        for bad in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                RunConfig(imu_print_every=bad)
        RunConfig(imu_print_every=0)

    def test_bridge_and_address_validation(self):
        from perovsat.run_config import RunConfig

        with self.assertRaisesRegex(ValueError, "requires imu_stimulus"):
            RunConfig(imu_bridge="127.0.0.1:4242")
        for bad in ("127.0.0.1", ":4242", "host:0", "host:port"):
            with self.assertRaises(ValueError):
                RunConfig(imu_stimulus=True, imu_bridge=bad)
        for kwargs in ({"imu_source": 254}, {"imu_source": 0}, {"imu_destination": 254},
                       {"imu_source": 1, "imu_destination": 1}, {"imu_destination": True}):
            with self.assertRaises(ValueError):
                RunConfig(**kwargs)
        RunConfig(imu_stimulus=True, imu_bridge="localhost:4242", imu_destination=0)


class BridgeEnvelopeTests(unittest.TestCase):
    def test_crc_and_envelope_match_hitl_bridge(self):
        from perovsat.bridge import Deframer, crc16_ccitt_false, encode_envelope

        # Same check value hitl-bridge's tests pin.
        self.assertEqual(crc16_ccitt_false(b"123456789"), 0x29B1)
        envelope = encode_envelope(b"123456789")
        self.assertEqual(envelope[:2], bytes((0xA5, 9)))
        self.assertEqual(int.from_bytes(envelope[-2:], "little"), 0x29B1)

        corrupt = bytearray(envelope)
        corrupt[-1] ^= 1
        stream = b"\x00\xa5" + bytes(corrupt) + envelope
        deframer = Deframer()
        self.assertEqual(deframer.push(stream[:7]) + deframer.push(stream[7:]), [b"123456789"])


def _log_frame(source, destination, kind, body):
    """A v3 Log frame as the emulator would send it."""
    return (bytes((3, destination, source)) + (0).to_bytes(8, "little") * 2
            + bytes((3, kind)) + body)


class FakeBridge:
    """TCP listener that records frames and answers GetStatus as device 1."""

    def __init__(self):
        from perovsat.bridge import Deframer, encode_envelope

        self._encode = encode_envelope
        self._deframer = Deframer()
        self.frames = []
        self.server = socket.create_server(("127.0.0.1", 0))
        self.address = f"127.0.0.1:{self.server.getsockname()[1]}"
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        conn, _ = self.server.accept()
        with conn:
            while data := conn.recv(4096):
                for frame in self._deframer.push(data):
                    self.frames.append(frame)
                    if frame[19] == 1 and frame[20] == 2:  # Command/GetStatus
                        request = frame[21:25]
                        source = frame[2]
                        result = request + bytes((2, 1))
                        status = struct.pack("<HIIIII", 1, 7, 0, 0, 0, 0)
                        for reply in (_log_frame(1, source, 3, result),
                                      _log_frame(1, source, 4, status)):
                            conn.sendall(self._encode(reply))

    def close(self):
        self.server.close()
        self.thread.join(timeout=2)


@unittest.skipUnless(importlib.util.find_spec("Basilisk"), "Basilisk is not installed")
class ImuStimulusTests(unittest.TestCase):
    def _run(self, directory, **kwargs):
        from perovsat.simulation import PerovSatSimulation, RunConfig

        sim = PerovSatSimulation(RunConfig(
            duration_s=2, timestep_s=.1, record_period_s=.1,
            output_dir=directory, imu_stimulus=True, **kwargs))
        return sim, sim.run()

    def test_log_matches_body_rate_and_sequence_increments(self):
        from perovsat.imu import RAD_S_PER_RPM

        with tempfile.TemporaryDirectory() as directory:
            sim, log = self._run(directory)
            rows = np.loadtxt(Path(directory, "imu_stimulus.log"), ndmin=2)

            self.assertEqual(sim.imu.emitted, len(log.t))
            self.assertEqual(len(rows), len(log.t))
            np.testing.assert_allclose(rows[:, 0], log.t, rtol=0, atol=1e-9)
            np.testing.assert_array_equal(rows[:, 1], np.arange(len(rows)))
            # Logged in rpm at six decimals from the float32 protocol sample.
            np.testing.assert_allclose(rows[:, 2:5] * RAD_S_PER_RPM, log.attitude.omega_B,
                                       rtol=0, atol=1e-7)
            self.assertIn("IMU stimulus samples: 21",
                          Path(directory, "summary.txt").read_text())

    def test_protocol_sample_is_filled_completely(self):
        from perovsat_plugins.imuStimulus import PSP_SAMPLE_IMU_STIMULUS, pspDescribeFrame

        with tempfile.TemporaryDirectory() as directory:
            sim, log = self._run(directory)
            stimulus = sim.imu.stimulus

            self.assertTrue(stimulus.hasSample())
            self.assertEqual(stimulus.getKind(), PSP_SAMPLE_IMU_STIMULUS)
            self.assertEqual(stimulus.getSequence(), len(log.t) - 1)
            gyro = [stimulus.getGyro(axis) for axis in range(3)]
            np.testing.assert_array_equal(gyro, log.attitude.omega_B[-1].astype(np.float32))
            accel = [stimulus.getAccel(axis) for axis in range(3)]
            self.assertTrue(np.all(np.isfinite(accel)))
            self.assertFalse(stimulus.getTemperaturePresent())

            frame = stimulus.sampleFrame(1, 252, 123)
            self.assertEqual(len(frame), 50)  # 20-byte prefix + kind + 29-byte IMU arm
            self.assertEqual(frame[:3], bytes((3, 1, 252)))
            self.assertIn(f"sample imu_stimulus seq={len(log.t) - 1}", pspDescribeFrame(frame))

    def test_first_sample_has_no_nan_specific_force(self):
        from perovsat_plugins.imuStimulus import ImuStimulus
        from Basilisk.simulation import spacecraft
        from Basilisk.utilities import SimulationBaseClass, macros

        sim = SimulationBaseClass.SimBaseClass()
        sim.CreateNewProcess("p").addTask(sim.CreateNewTask("t", macros.sec2nano(.1)))
        sc = spacecraft.Spacecraft()
        sim.AddModelToTask("t", sc)
        stimulus = ImuStimulus()
        stimulus.scStateInMsg.subscribeTo(sc.scStateOutMsg)
        sim.AddModelToTask("t", stimulus, -40)
        sim.InitializeSimulation()
        sim.ConfigureStopTime(0)
        sim.ExecuteSimulation()
        self.assertTrue(np.isnan(sc.scStateOutMsg.read().nonConservativeAccelpntB_B).all())
        self.assertEqual([stimulus.getAccel(axis) for axis in range(3)], [0.0, 0.0, 0.0])
        self.assertTrue(stimulus.sampleFrame(1, 252, 0))

    def test_samples_are_sent_to_bridge_and_status_logged(self):
        bridge = FakeBridge()
        try:
            with tempfile.TemporaryDirectory() as directory:
                sim, log = self._run(directory, imu_bridge=bridge.address)
                summary = Path(directory, "summary.txt").read_text()
                bridge_log = Path(directory, "bridge.log").read_text()
        finally:
            bridge.close()

        samples = [f for f in bridge.frames if f[19] == 2]
        self.assertEqual(len(samples), len(log.t))
        self.assertEqual([int.from_bytes(f[21:25], "little") for f in samples],
                         list(range(len(log.t))))
        self.assertTrue(all(f[:3] == bytes((3, 1, 252)) for f in samples))
        self.assertEqual(sum(f[19] == 1 for f in bridge.frames), 2)  # GetStatus before/after
        self.assertIn(f"IMU sample frames sent: {len(log.t)}", summary)
        self.assertIn("Device status after: src=1 dst=252 log status sample_present=1 "
                      "clock_corrected=0 active_sample=7", summary)
        self.assertIn("log result request=2 command=2 status=1", bridge_log)

    def test_emitter_does_not_change_physics(self):
        with tempfile.TemporaryDirectory() as directory:
            from perovsat.simulation import PerovSatSimulation, RunConfig

            runs = [
                PerovSatSimulation(RunConfig(
                    duration_s=2, timestep_s=.1, record_period_s=.1,
                    output_dir=directory, imu_stimulus=imu)).run()
                for imu in (False, True)
            ]
            a, b = runs
            for x, y in ((a.t, b.t), (a.attitude.sigma_BN, b.attitude.sigma_BN),
                         (a.attitude.omega_B, b.attitude.omega_B),
                         (a.attitude.r_BN_N, b.attitude.r_BN_N)):
                np.testing.assert_array_equal(x, y)

    def test_unlinked_reader_fails_on_reset(self):
        from perovsat.imu import ImuStimulusEmitter
        from perovsat.run_config import RunConfig
        from perovsat_plugins.imuStimulus import ImuStimulus

        with tempfile.TemporaryDirectory() as directory:
            emitter = ImuStimulusEmitter(RunConfig(), Path(directory), ImuStimulus())
            with self.assertRaisesRegex(RuntimeError, "not linked"):
                emitter.Reset(0)


if __name__ == "__main__":
    unittest.main()
