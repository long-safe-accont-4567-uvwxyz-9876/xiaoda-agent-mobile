import tempfile
import unittest
import zipfile
from pathlib import Path

from verify_apk import FORBIDDEN_PATTERNS, verify_apk, verify_source_tree


class VerifyApkTest(unittest.TestCase):
    def create_apk(self, entries: dict[str, bytes]) -> Path:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        apk = Path(directory.name) / "app.apk"
        with zipfile.ZipFile(apk, "w") as archive:
            for name, content in entries.items():
                archive.writestr(name, content)
        return apk

    def test_accepts_minimal_android_archive(self) -> None:
        apk = self.create_apk({"AndroidManifest.xml": b"binary-manifest"})

        self.assertEqual([], verify_apk(apk))

    def test_rejects_forbidden_runtime_file(self) -> None:
        apk = self.create_apk({"assets/models/model.onnx": b"model"})

        self.assertTrue(any(".onnx" in issue for issue in verify_apk(apk)))

    def test_rejects_embedded_python_runtime(self) -> None:
        apk = self.create_apk({"lib/arm64-v8a/libpython3.11.so": b"runtime"})

        self.assertTrue(any("libpython" in issue for issue in verify_apk(apk)))

    def test_rejects_forbidden_content_case_insensitively(self) -> None:
        apk = self.create_apk({"assets/config.json": b'{"provider": "OlLaMa"}'})

        self.assertTrue(any("ollama" in issue.lower() for issue in verify_apk(apk)))

    def test_rejects_forbidden_content_in_large_entry(self) -> None:
        apk = self.create_apk({"assets/payload.bin": b"x" * (9 * 1024 * 1024) + b"ollama"})

        self.assertTrue(any("ollama" in issue.lower() for issue in verify_apk(apk)))

    def test_rejects_embedded_provider_key(self) -> None:
        apk = self.create_apk({"assets/config.json": b'{"api_key":"sk-1234567890abcdefghijklmnop"}'})

        self.assertTrue(any("provider_key" in issue for issue in verify_apk(apk)))

    def test_rejects_provider_key_in_android_source_tree(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        source = Path(directory.name) / "src" / "main" / "res" / "values"
        source.mkdir(parents=True)
        (source / "config.xml").write_text("sk-1234567890abcdefghijklmnop", encoding="utf-8")

        self.assertTrue(any("provider_key" in issue for issue in verify_source_tree(Path(directory.name))))

    def test_rejects_common_provider_credentials_in_apk(self) -> None:
        credentials = {
            "google_api_key": b"AIza" + b"a" * 35,
            "aws_access_key": b"AKIA" + b"A" * 16,
            "aws_temporary_access_key": b"ASIA" + b"A" * 16,
            "github_token": b"ghp_" + b"a" * 36,
            "github_fine_grained_token": b"github_pat_" + b"a" * 82,
            "slack_token": b"xoxb-" + b"1234567890-1234567890-abcdefghijklmnop",
            "private_key": b"-----BEGIN PRIVATE KEY-----",
        }

        for label, credential in credentials.items():
            with self.subTest(label=label):
                apk = self.create_apk({"assets/config.bin": credential})
                self.assertTrue(any(label in issue for issue in verify_apk(apk)))

    def test_rejects_common_provider_credentials_in_source_tree(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        source = Path(directory.name) / "src" / "main" / "config.properties"
        source.parent.mkdir(parents=True)
        source.write_text("google.key=AIza" + "a" * 35, encoding="utf-8")

        self.assertTrue(any("google_api_key" in issue for issue in verify_source_tree(Path(directory.name))))

    def test_rejects_signing_material_anywhere_in_source_tree(self) -> None:
        for filename in ("release.jks", "release.keystore", "release.p12", "release.pfx", "release.pem", "release.der", "release.key"):
            with self.subTest(filename=filename):
                directory = tempfile.TemporaryDirectory()
                self.addCleanup(directory.cleanup)
                signing_file = Path(directory.name) / "app" / "signing" / filename
                signing_file.parent.mkdir(parents=True)
                signing_file.write_bytes(b"signing-material")
                self.assertTrue(any("signing_material" in issue for issue in verify_source_tree(Path(directory.name))))

    def test_scans_test_sources_for_real_credentials(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        source = Path(directory.name) / "app" / "src" / "test" / "fixture.properties"
        source.parent.mkdir(parents=True)
        source.write_text("token=ghp_" + "a" * 36, encoding="utf-8")

        self.assertTrue(any("github_token" in issue for issue in verify_source_tree(Path(directory.name))))


    def test_generic_file_suffix_bytes_do_not_false_positive_inside_dex(self) -> None:
        apk = self.create_apk({"classes.dex": b"\x00\x00.pY\x00binary-offset-table"})

        self.assertEqual([], verify_apk(apk))

    def test_rejects_python_source_by_archive_path(self) -> None:
        apk = self.create_apk({"assets/bootstrap.py": b"print('blocked')"})

        self.assertTrue(any(".py" in issue for issue in verify_apk(apk)))

    def test_patterns_cover_prohibited_android_payloads(self) -> None:
        patterns = " ".join(FORBIDDEN_PATTERNS)

        for value in ("agentcore", "fastapi", "ollama", "onnxruntime", "bge-small", "libpython", ".py", ".onnx"):
            self.assertIn(value, patterns)


if __name__ == "__main__":
    unittest.main()
