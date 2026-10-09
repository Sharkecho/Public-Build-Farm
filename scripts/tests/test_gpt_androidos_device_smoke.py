"""Targeted tests for the opt-in ADB phone relay: no Android device required."""
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

MODULE = Path(__file__).resolve().parents[1] / "gpt-androidos-device-smoke.py"
spec = importlib.util.spec_from_file_location("device_smoke", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fake_adb_calls(calls, multiple=False):
    def command(adb, parts, serial=None, timeout=30):
        calls.append((serial, tuple(parts)))
        if parts == ["devices"]:
            if multiple:
                return "List of devices attached\nABC123\tdevice\nXYZ456\tdevice"
            return "List of devices attached\nABC123\tdevice"
        if parts[:2] == ["shell", "getprop"]:
            return {"ro.product.model": "SM-N960N", "ro.build.version.sdk": "29",
                    "sys.boot_completed": "1"}[parts[2]]
        if parts[:3] == ["shell", "pm", "path"]:
            return "package:/data/app/base.apk"
        if parts[:1] == ["install"]:
            return "Performing Streamed Install\nSuccess"
        if parts[:1] == ["shell"] and "monkey" in parts:
            return "Events injected: 1"
        raise AssertionError(f"Unexpected ADB action: {parts}")
    return command


class DeviceSmokeTests(unittest.TestCase):
    def test_read_only_default_does_not_install_or_launch(self):
        calls = []
        with patch.object(module, "adb_run", side_effect=fake_adb_calls(calls)):
            result = module.smoke("adb")
        self.assertEqual(result["result"], "SMOKE_PASS")
        self.assertFalse(result["apk_installed_this_run"])
        self.assertFalse(result["agent_launched"])
        self.assertNotIn("install", [p[0] for _, p in calls])
        self.assertNotIn("monkey", str(calls))
        self.assertEqual(result["audio_ipc"], "NOT_IMPLEMENTED")

    def test_requires_exact_one_device(self):
        with patch.object(module, "adb_run", side_effect=fake_adb_calls([], multiple=True)):
            with self.assertRaises(module.DeviceError):
                module.smoke("adb")

    def test_no_install_without_explicit_flag(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "test.apk"
            apk.write_bytes(b"dummy")
            with patch.object(module, "adb_run", side_effect=fake_adb_calls(calls)):
                module.smoke("adb", apk=apk, expected_sha256="0" * 64)
        self.assertFalse(any(p[0] == "install" for _, p in calls))

    def test_install_rejects_wrong_checksum(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "test.apk"
            apk.write_bytes(b"dummy")
            with patch.object(module, "adb_run", side_effect=fake_adb_calls(calls)):
                with self.assertRaisesRegex(module.DeviceError, "SHA-256"):
                    module.smoke("adb", apk=apk, expected_sha256="0" * 64, install=True)
        self.assertFalse(any(p[0] == "install" for _, p in calls))

    def test_opt_in_ui_capture_saves_local_png_and_xml_and_cleans_remote(self):
        from types import SimpleNamespace
        calls = []
        def adb(adb, parts, serial=None, timeout=30):
            calls.append(tuple(parts))
            if parts[:3] == ["shell", "uiautomator", "dump"]:
                return "UI hiercharchy dumped"
            if parts[:2] == ["exec-out", "cat"]:
                return '<?xml version="1.0"?><hierarchy rotation="0"></hierarchy>'
            if parts[:3] == ["shell", "rm", "-f"]:
                return ""
            raise AssertionError(f"unexpected ADB operation: {parts}")
        with tempfile.TemporaryDirectory() as d:
            with patch.object(module, "adb_run", side_effect=adb):
                with patch.object(module.subprocess, "run", return_value=SimpleNamespace(
                    returncode=0, stdout=bytes.fromhex("89504e470d0a1a0a") + b"fake")):
                    data = module.capture_ui_evidence("adb", "ABC123", Path(d))
            self.assertTrue((Path(d) / "agent-screen.png").is_file())
            self.assertIn("hierarchy", (Path(d) / "agent-ui.xml").read_text())
            self.assertTrue(data["evidence_local_only"])
            self.assertTrue(any(p[:3] == ("shell", "rm", "-f") for p in calls))

    def test_ui_capture_rejects_non_png(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as d:
            with patch.object(module.subprocess, "run", return_value=SimpleNamespace(
                returncode=0, stdout=b"not a PNG")):
                with self.assertRaisesRegex(module.DeviceError, "not PNG"):
                    module.capture_ui_evidence("adb", "ABC123", Path(d))
            self.assertFalse((Path(d) / "agent-screen.png").exists())

    def test_explicit_install_then_launch(self):
        calls = []
        with tempfile.TemporaryDirectory() as directory:
            apk = Path(directory) / "test.apk"
            apk.write_bytes(b"dummy")
            with patch.object(module, "adb_run", side_effect=fake_adb_calls(calls)):
                report = module.smoke("adb", apk=apk, expected_sha256=module.hash_file(apk),
                                      install=True, launch_agent=True)
        self.assertTrue(report["apk_installed_this_run"])
        self.assertTrue(report["agent_launched"])
        self.assertEqual(sum(p[0] == "install" for _, p in calls), 1)
        self.assertEqual(report["rom_integration"], "UNVERIFIED")


if __name__ == "__main__":
    unittest.main()
