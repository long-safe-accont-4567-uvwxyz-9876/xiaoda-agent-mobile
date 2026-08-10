import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from verify_termux_component import verify_archive, verify_component


class VerifyTermuxComponentTest(unittest.TestCase):
    def test_current_frozen_component_manifest_is_valid(self) -> None:
        root = Path(__file__).resolve().parents[1] / "feature" / "terminal-runtime"

        self.assertEqual([], verify_component(root))

    def test_archive_requires_both_64_bit_abis(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "runtime.aar"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("jni/arm64-v8a/libtermux.so", b"native")

            self.assertTrue(any("x86_64" in issue or "coverage" in issue for issue in verify_archive(archive)))

    def test_archive_rejects_32_bit_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "runtime.aar"
            with zipfile.ZipFile(archive, "w") as output:
                output.writestr("jni/arm64-v8a/libtermux.so", b"native")
                output.writestr("jni/x86_64/libtermux.so", b"native")
                output.writestr("jni/x86/libtermux.so", b"native")

            self.assertTrue(any("32-bit" in issue for issue in verify_archive(archive)))

    def test_source_tampering_is_detected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            upstream = root / "third_party" / "termux-terminal-emulator"
            (upstream / "src").mkdir(parents=True)
            (upstream / "src" / "file.java").write_text("changed", encoding="utf-8")
            for name in ("UPSTREAM_LICENSE.md", "LICENSE-APACHE-2.0.txt"):
                (upstream / name).write_text("license", encoding="utf-8")
            (upstream / "SOURCE_MANIFEST.json").write_text(json.dumps({"component":"termux/terminal-emulator","version":"0.118.3","commit":"5b657c6adf4304e5198951ce815fe0205dcac29c","files":{"src/file.java":"0"*64}}), encoding="utf-8")
            (upstream / "UPSTREAM.json").write_text(json.dumps({"name":"Termux terminal-emulator","tag":"v0.118.3","commit":"5b657c6adf4304e5198951ce815fe0205dcac29c"}), encoding="utf-8")
            (root / "compliance").mkdir()
            (root / "compliance" / "BOM.json").write_text(json.dumps({"components":[{"name":"termux/terminal-emulator","abis":["arm64-v8a","x86_64"]}],"releaseGates":{"legalApproved":False,"storeApproved":False,"terminalRuntimeEnabled":False}}), encoding="utf-8")

            self.assertTrue(any("source hash" in issue for issue in verify_component(root)))


if __name__ == "__main__":
    unittest.main()
