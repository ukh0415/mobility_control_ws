"""Parser, source-editor, and local HTTP smoke tests without real serial I/O."""

import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import Request, urlopen

from pc.motor_control_tuning_ui import (
    AppState,
    TUNABLES,
    create_server,
    parse_telemetry_line,
    read_tuning_values,
    validate_tuning_values,
    write_tuning_values,
)


class TelemetryParserTests(unittest.TestCase):
    def test_normal_telemetry(self):
        sample = parse_telemetry_line(
            "TELEM_M37,1234,1,2,1,200,0,0,665,662,-70,1", host_time=5.0)
        self.assertTrue(sample.ok)
        self.assertEqual(sample.host_time, 5.0)
        self.assertEqual(sample.state, 2)
        self.assertEqual(sample.motor2_count, 665)
        self.assertEqual(sample.target_count, 662)
        self.assertEqual(sample.motor2_pwm, -70)
        self.assertEqual(sample.target_step, 1)

    def test_i2c_failure_telemetry(self):
        sample = parse_telemetry_line("TELEM_M37,2500,0,2,0", host_time=6.0)
        self.assertFalse(sample.ok)
        self.assertEqual(sample.write_error, 2)
        self.assertEqual(sample.bytes_received, 0)

    def test_rejects_wrong_version_prefix(self):
        with self.assertRaises(ValueError):
            parse_telemetry_line("TELEM_M36,1,1,0,0,0")


class TuningSourceTests(unittest.TestCase):
    def make_header(self, directory: str) -> tuple[Path, dict[str, int]]:
        values = {}
        lines = []
        for index, (name, _label, minimum, maximum, allowed) in enumerate(TUNABLES):
            if allowed:
                value = sorted(allowed)[0]
            else:
                value = max(minimum, min(maximum, index + 1))
            values[name] = value
            suffix = "U" if name.endswith("_MS") else ""
            lines.append(f"#define {name} {value}{suffix} /* keep comment */\n")
        path = Path(directory) / "carrier_test.h"
        path.write_text("".join(lines), encoding="utf-8")
        return path, values

    def test_read_and_write_defines_preserves_comment(self):
        with tempfile.TemporaryDirectory() as directory:
            path, values = self.make_header(directory)
            self.assertEqual(read_tuning_values(path), values)
            values["CARRIER_MOVE_PWM_PERCENT"] = 55
            values["CLUTCH_JOG_DURATION_MS"] = 420
            write_tuning_values(values, path)
            reread = read_tuning_values(path)
            self.assertEqual(reread["CARRIER_MOVE_PWM_PERCENT"], 55)
            self.assertEqual(reread["CLUTCH_JOG_DURATION_MS"], 420)
            text = path.read_text(encoding="utf-8")
            self.assertIn("420U /* keep comment */", text)

    def test_rejects_unsafe_pwm(self):
        with tempfile.TemporaryDirectory() as directory:
            _path, values = self.make_header(directory)
            values["CARRIER_MOVE_PWM_PERCENT"] = 101
            with self.assertRaises(ValueError):
                validate_tuning_values(values)


class LocalHttpTests(unittest.TestCase):
    def test_root_and_status_endpoints(self):
        state = AppState()
        server, state = create_server("127.0.0.1", 0, "COM7", state)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        base_url = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with urlopen(base_url + "/", timeout=2) as response:
                page = response.read().decode("utf-8")
            self.assertIn("모터2 위치제어 튜닝", page)
            self.assertIn("UI rev.2", page)
            self.assertIn("onclick=\"sendMotorCommand('k')\"", page)
            self.assertNotIn("onclick=\"command(", page)
            self.assertIn("logBox.scrollTop=logBox.scrollHeight", page)

            request = Request(base_url + "/api/command", method="POST",
                              data=b'{"command":"k"}',
                              headers={"Content-Type": "application/json"})
            with urlopen(request, timeout=2) as response:
                result = json.load(response)
            self.assertTrue(result["ok"])

            with urlopen(base_url + "/api/status", timeout=2) as response:
                status = json.load(response)
            self.assertFalse(status["connected"])
            self.assertEqual(status["samples"], [])
            self.assertIn("[명령] 전체 정지", status["logs"])
        finally:
            server.shutdown()
            server.server_close()
            state.close()
            worker.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
