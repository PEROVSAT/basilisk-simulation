"""Listener readiness tests; no Basilisk installation or viewer required."""
import socket
import unittest
from unittest.mock import MagicMock, patch
from perovsat.vizard import wait_for_vizard


class VizardReadinessTests(unittest.TestCase):
    def test_retries_then_closes_probe(self):
        probe = MagicMock()
        with patch('perovsat.vizard.socket.create_connection', side_effect=[
                ConnectionRefusedError(), TimeoutError(), probe]) as connect, \
                patch('perovsat.vizard.time.sleep'):
            wait_for_vizard('127.0.0.1', 1)
        self.assertEqual(connect.call_count, 3)
        self.assertEqual(connect.call_args.args[0], ('127.0.0.1', 5556))
        probe.__exit__.assert_called_once()

    def test_timeout_limits_attempt_and_sleep(self):
        with patch('perovsat.vizard.time.monotonic', side_effect=[0, 0, .09, .1]), \
                patch('perovsat.vizard.time.sleep') as sleep, \
                patch('perovsat.vizard.socket.create_connection',
                      side_effect=ConnectionRefusedError()) as connect:
            with self.assertRaisesRegex(TimeoutError, 'not reachable within'):
                wait_for_vizard('127.0.0.1', .1)
        self.assertEqual(connect.call_args.kwargs['timeout'], .1)
        self.assertAlmostEqual(sleep.call_args.args[0], .01)

    def test_dns_error_is_actionable(self):
        with patch('perovsat.vizard.socket.create_connection',
                   side_effect=socket.gaierror('unknown host')):
            with self.assertRaisesRegex(ConnectionError, 'Cannot resolve Vizard host'):
                wait_for_vizard('invalid.example', 1)

    def test_interrupt_propagates(self):
        with patch('perovsat.vizard.socket.create_connection', side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                wait_for_vizard('127.0.0.1', 1)
