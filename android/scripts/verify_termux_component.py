import argparse
import hashlib
import json
import sys
import zipfile
from pathlib import Path

EXPECTED_COMPONENT = "termux/terminal-emulator"
EXPECTED_VERSION = "0.118.3"
EXPECTED_COMMIT = "5b657c6adf4304e5198951ce815fe0205dcac29c"
EXPECTED_ABIS = {"arm64-v8a", "x86_64"}
MAX_NATIVE_BYTES = 64 * 1024
MAX_AAR_BYTES = 256 * 1024


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_component(source_root: Path) -> list[str]:
    issues: list[str] = []
    upstream = source_root / "third_party" / "termux-terminal-emulator"
    manifest_path = upstream / "SOURCE_MANIFEST.json"
    metadata_path = upstream / "UPSTREAM.json"
    bom_path = source_root / "compliance" / "BOM.json"
    for required in (manifest_path, metadata_path, bom_path, upstream / "UPSTREAM_LICENSE.md", upstream / "LICENSE-APACHE-2.0.txt"):
        if not required.is_file():
            issues.append(f"missing required component file: {required}")
    if issues:
        return issues
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    bom = json.loads(bom_path.read_text(encoding="utf-8"))
    if manifest.get("component") != EXPECTED_COMPONENT or metadata.get("name") != "Termux terminal-emulator":
        issues.append("component identity mismatch")
    if manifest.get("version") != EXPECTED_VERSION or metadata.get("tag") != f"v{EXPECTED_VERSION}":
        issues.append("component version mismatch")
    if manifest.get("commit") != EXPECTED_COMMIT or metadata.get("commit") != EXPECTED_COMMIT:
        issues.append("component commit mismatch")
    expected_files = manifest.get("files", {})
    actual_files = {
        str(path.relative_to(upstream)).replace("\\", "/"): sha256(path)
        for path in sorted((upstream / "src").rglob("*"))
        if path.is_file()
    }
    if actual_files != expected_files:
        issues.append("vendored Termux source hash manifest mismatch")
    components = bom.get("components", [])
    if len(components) != 1 or components[0].get("name") != EXPECTED_COMPONENT:
        issues.append("BOM must contain exactly the frozen Termux terminal-emulator component")
    elif set(components[0].get("abis", [])) != EXPECTED_ABIS:
        issues.append("BOM ABI set mismatch")
    gates = bom.get("releaseGates", {})
    if gates.get("legalApproved") or gates.get("storeApproved") or gates.get("terminalRuntimeEnabled"):
        issues.append("release gates must remain closed until written approvals exist")
    return issues


def verify_archive(archive_path: Path) -> list[str]:
    issues: list[str] = []
    if not archive_path.is_file():
        return [f"archive does not exist: {archive_path}"]
    if archive_path.suffix.lower() == ".aar" and archive_path.stat().st_size > MAX_AAR_BYTES:
        issues.append(f"Termux runtime AAR exceeds {MAX_AAR_BYTES} bytes")
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        found: set[str] = set()
        for abi in EXPECTED_ABIS:
            candidates = (f"jni/{abi}/libtermux.so", f"lib/{abi}/libtermux.so")
            name = next((candidate for candidate in candidates if candidate in names), None)
            if name is None:
                issues.append(f"missing libtermux.so for {abi}")
                continue
            data = archive.read(name)
            found.add(abi)
            if len(data) > MAX_NATIVE_BYTES:
                issues.append(f"libtermux.so for {abi} exceeds {MAX_NATIVE_BYTES} bytes")
        for unsupported in ("armeabi-v7a", "x86"):
            if any(name in names for name in (f"jni/{unsupported}/libtermux.so", f"lib/{unsupported}/libtermux.so")):
                issues.append(f"unsupported 32-bit Termux ABI packaged: {unsupported}")
        if found != EXPECTED_ABIS:
            issues.append("Termux runtime ABI coverage is incomplete")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--archive", type=Path, action="append", default=[])
    args = parser.parse_args()
    issues = verify_component(args.source_root)
    for archive in args.archive:
        issues.extend(verify_archive(archive))
    if issues:
        print("FAIL Termux runtime component")
        for issue in sorted(set(issues)):
            print(f"  {issue}")
        return 1
    print("PASS Termux runtime component")
    return 0


if __name__ == "__main__":
    sys.exit(main())
