import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from verify_web_assets import verify_assets


class VerifyWebAssetsTest(unittest.TestCase):
    def test_accepts_complete_matching_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok", encoding="utf-8")
            digest = hashlib.sha256(b"ok").hexdigest()
            (root / "asset-manifest.json").write_text(
                json.dumps({"appVersion": "1.0", "files": {"index.html": digest}}),
                encoding="utf-8",
            )
            self.assertEqual([], verify_assets(root, "1.0"))

    def test_rejects_missing_changed_and_unlisted_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("changed", encoding="utf-8")
            (root / "extra.js").write_text("extra", encoding="utf-8")
            (root / "asset-manifest.json").write_text(
                json.dumps({"appVersion": "1.0", "files": {"index.html": "0" * 64, "missing.js": "1" * 64}}),
                encoding="utf-8",
            )
            issues = verify_assets(root, "1.0")
            self.assertTrue(any("哈希不匹配" in issue for issue in issues))
            self.assertTrue(any("资源缺失" in issue for issue in issues))
            self.assertTrue(any("未登记资源" in issue for issue in issues))

    def test_rejects_malformed_hashes_and_unsafe_manifest_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "index.html").write_text("ok", encoding="utf-8")
            (root / "asset-manifest.json").write_text(
                json.dumps({"appVersion": "1.0", "files": {"../index.html": "bad", "index.html": "abc"}}),
                encoding="utf-8",
            )

            issues = verify_assets(root, "1.0")

            self.assertTrue(any("非法资源路径" in issue for issue in issues))
            self.assertTrue(any("非法哈希" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
