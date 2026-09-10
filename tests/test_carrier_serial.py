"""No serial port or hardware is opened by these tests."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


def load_client():
    spec = importlib.util.spec_from_file_location(
        "carrier_client", Path(__file__).resolve().parents[1] / "pc/robot_control_client_serial.py")
    module = importlib.util.module_from_spec(spec)
    fake_serial = types.ModuleType("serial")
    with patch.dict(sys.modules, {"serial": fake_serial}):
        spec.loader.exec_module(module)
    return module


class ClientTests(unittest.TestCase):
    def test_command_pulse_changes_to_heartbeat(self):
        client = load_client()
        client.active_move_key = "p"
        client.command_until = 2.0
        sent = []
        ticks = iter([0.0, 1.0, 2.0])

        def sleep(_):
            if len(sent) == 3:
                client.running = False

        with patch.object(client, "send_command", sent.append), patch.object(
                client.time, "monotonic", side_effect=lambda: next(ticks)), patch.object(
                client.time, "sleep", sleep):
            client.repeat_sender()
        self.assertEqual(sent, ["p", "p", "h"])

    def test_reconnect_discards_previous_motion(self):
        client = load_client()
        client.active_move_key = "p"
        port = object()
        with patch.object(client, "connect", return_value=port), patch.object(
                client.time, "sleep", lambda _: setattr(client, "running", False)):
            client.connection_manager()
        self.assertIs(client.ser, port)
        self.assertEqual(client.active_move_key, "k")
        self.assertEqual(client.command_until, 0.0)
        self.assertIsNone(client.last_state)

    def test_ctrl_c_sends_stop(self):
        client = load_client()
        client.active_move_key = "p"
        with patch.object(client.threading, "Thread"), patch.object(client, "keyboard_loop", side_effect=KeyboardInterrupt), \
                patch.object(client.time, "sleep"), patch.object(client, "send_command") as send, patch("builtins.print"):
            client.main()
        send.assert_called_once_with("k")
        self.assertFalse(client.running)
        self.assertEqual(client.active_move_key, "k")
        self.assertEqual(client.command_until, 0.0)


if __name__ == "__main__":
    unittest.main()
