import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

MODULE = Path(__file__).resolve().parents[1] / "scripts/agent-update/release_manifest.py"
spec = importlib.util.spec_from_file_location("androidos_release_manifest", MODULE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class ReleaseManifestTests(unittest.TestCase):
    def test_next_version(self):
        self.assertEqual(module.checked_code("3", 0), 3)
        self.assertEqual(module.checked_code("4", 3), 4)

    def test_block_downgrade_invalid_and_replay(self):
        for value, previous in [("2", 0), ("3", 3), ("2", 3), ("-1", 0),
                                ("3abc", 0), ("03", 0), ("0", 0), ("1000000000", 0)]:
            with self.subTest(value=value, previous=previous):
                with self.assertRaises(ValueError):
                    module.checked_code(value, previous)

    def test_strict_manifest(self):
        obj = module.signed_release(3, "a" * 64, "b" * 64)
        self.assertEqual(obj["status"], "SIGNED_RELEASE")
        self.assertEqual(obj["version_code"], 3)
        self.assertEqual(obj["apk_url"], "https://github.com/Sharkecho/Public-Build-Farm/releases/download/gpt-androidos-v3/gpt-androidos.apk")
        self.assertEqual(obj["certificate_sha256"], "b" * 64)
        for digest in ("xyz", "", "0" * 63, "g" * 64):
            with self.assertRaises(ValueError):
                module.signed_release(3, digest, "b" * 64)

    def test_manifest_schema_guard(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "stable.json"
            path.write_text(json.dumps({"schema_version": 1, "version_code": 0}))
            self.assertEqual(module.current_code(path), 0)
            path.write_text(json.dumps({"schema_version": 7, "version_code": 0}))
            with self.assertRaises(ValueError):
                module.current_code(path)


if __name__ == "__main__":
    unittest.main()
