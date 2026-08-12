import argparse
import re
import subprocess
import sys
import zipfile
from pathlib import Path

# Under the embedded-Python-backend architecture the APK intentionally bundles
# the full FastAPI app and a Chaquopy Python 3.11 runtime (fastapi, libpython,
# .py/.pyc, agentcore are all legitimate build content). Only genuinely retired
# local-AI artifacts and the mobile terminal remain forbidden.
FORBIDDEN_PATTERNS = (
    "ollama",
    "onnxruntime",
    "bge-small",
    ".onnx",
)

FORBIDDEN_APK_PATH_PATTERNS = ("chatterminal", "xterm")
MOBILE_TERMINAL_CONTENT_PATTERNS = ("terminal_start", "terminal_output", "terminal_resize", "terminal_kill")
FORBIDDEN_CONTENT_PATTERNS = tuple(
    pattern for pattern in FORBIDDEN_PATTERNS if pattern not in {".onnx", ".py", ".pyc"}
) + MOBILE_TERMINAL_CONTENT_PATTERNS

FORBIDDEN_SECRET_PATTERNS = (
    ("provider_key", re.compile(rb"\bsk-[a-z0-9_-]{20,}\b", re.IGNORECASE)),
    ("bearer_token", re.compile(rb"\bbearer\s+[a-z0-9._~+/-]{20,}", re.IGNORECASE)),
    ("google_api_key", re.compile(rb"\bAIza[a-z0-9_-]{35}\b", re.IGNORECASE)),
    ("aws_access_key", re.compile(rb"\bAKIA[A-Z0-9]{16}\b", re.IGNORECASE)),
    ("aws_temporary_access_key", re.compile(rb"\bASIA[A-Z0-9]{16}\b", re.IGNORECASE)),
    ("github_token", re.compile(rb"\bghp_[a-z0-9]{36}\b", re.IGNORECASE)),
    ("github_fine_grained_token", re.compile(rb"\bgithub_pat_[a-z0-9_]{20,}\b", re.IGNORECASE)),
    ("github_token", re.compile(rb"\bgh[ousr]_[a-z0-9]{36,}\b", re.IGNORECASE)),
    ("slack_token", re.compile(rb"\bxox(?:a|b|p|r|s)-[a-z0-9-]{20,}\b", re.IGNORECASE)),
    ("private_key", re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", re.IGNORECASE)),
)

CHUNK_SIZE = 1024 * 1024
SOURCE_SUFFIXES = {
    ".gradle",
    ".java",
    ".json",
    ".kts",
    ".kt",
    ".properties",
    ".txt",
    ".xml",
    ".yaml",
    ".yml",
}
SOURCE_EXCLUDED_PARTS = {"build", ".gradle"}
SIGNING_MATERIAL_SUFFIXES = {".jks", ".keystore", ".p12", ".pfx", ".pem", ".der", ".key"}


def _scan_entry(archive: zipfile.ZipFile, entry: zipfile.ZipInfo) -> list[str]:
    issues: list[str] = []
    overlap = max(
        max(len(pattern) for pattern in FORBIDDEN_CONTENT_PATTERNS),
        256,
    )
    tail = b""
    with archive.open(entry) as source:
        while chunk := source.read(CHUNK_SIZE):
            content = (tail + chunk).lower()
            for pattern in FORBIDDEN_CONTENT_PATTERNS:
                if pattern.encode() in content:
                    issues.append(f"禁止项出现在内容中: {pattern} -> {entry.filename}")
            for label, pattern in FORBIDDEN_SECRET_PATTERNS:
                if pattern.search(content):
                    issues.append(f"禁止项出现在内容中: {label} -> {entry.filename}")
            tail = content[-overlap:]
    return issues


def _is_git_ignored(path: Path) -> bool:
    """True if `path` is excluded by .gitignore (e.g. release keystore)."""
    try:
        result = subprocess.run(
            ["git", "check-ignore", "-q", str(path)],
            capture_output=True,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def verify_source_tree(source_root: Path) -> list[str]:
    issues: list[str] = []
    for path in source_root.rglob("*"):
        if not path.is_file():
            continue
        relative_parts = {part.lower() for part in path.relative_to(source_root).parts}
        if relative_parts & SOURCE_EXCLUDED_PARTS:
            continue
        if _is_git_ignored(path):
            # Release keystores and CI-provisioned secrets live outside VCS.
            continue
        if path.suffix.lower() in SIGNING_MATERIAL_SUFFIXES:
            issues.append(f"禁止签名材料出现在源码树中: signing_material -> {path}")
            continue
        if path.suffix.lower() not in SOURCE_SUFFIXES:
            continue
        # Test fixtures intentionally contain fake secrets (e.g. "sk-android-local-secret-123456")
        # to exercise the provider API without real credentials. Skip them.
        if "androidtest" in relative_parts or "test" in relative_parts:
            continue
        content = path.read_bytes()
        for label, pattern in FORBIDDEN_SECRET_PATTERNS:
            if pattern.search(content):
                issues.append(f"禁止项出现在源码中: {label} -> {path}")
    return sorted(set(issues))


def verify_apk(apk_path: Path) -> list[str]:
    if not apk_path.is_file():
        return [f"APK 不存在: {apk_path}"]
    issues: list[str] = []
    try:
        with zipfile.ZipFile(apk_path) as archive:
            for entry in archive.infolist():
                entry_name = entry.filename.lower()
                for pattern in FORBIDDEN_PATTERNS + FORBIDDEN_APK_PATH_PATTERNS:
                    if pattern in entry_name:
                        issues.append(f"禁止项出现在路径中: {pattern} -> {entry.filename}")
                issues.extend(_scan_entry(archive, entry))
    except zipfile.BadZipFile:
        return [f"APK 不是有效 ZIP 归档: {apk_path}"]
    return sorted(set(issues))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("apk", nargs="+", type=Path)
    parser.add_argument("--source-root", type=Path)
    args = parser.parse_args()
    failed = False
    if args.source_root:
        source_issues = verify_source_tree(args.source_root)
        if source_issues:
            failed = True
            print(f"FAIL {args.source_root}")
            for issue in source_issues:
                print(f"  {issue}")
        else:
            print(f"PASS {args.source_root}")
    for apk_path in args.apk:
        issues = verify_apk(apk_path)
        if issues:
            failed = True
            print(f"FAIL {apk_path}")
            for issue in issues:
                print(f"  {issue}")
        else:
            print(f"PASS {apk_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
