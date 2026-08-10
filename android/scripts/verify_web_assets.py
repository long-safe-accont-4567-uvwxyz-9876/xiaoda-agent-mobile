import argparse
import hashlib
import json
import re
import sys
from pathlib import Path


def verify_assets(root: Path, app_version: str) -> list[str]:
    manifest_path = root / "asset-manifest.json"
    if not manifest_path.is_file():
        return ["资源清单缺失"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return [f"资源清单不可读: {exc}"]
    issues: list[str] = []
    if manifest.get("appVersion") != app_version:
        issues.append("应用版本不匹配")
    expected = manifest.get("files")
    if not isinstance(expected, dict) or not expected:
        return issues + ["资源清单为空"]
    safe_expected: dict[str, str] = {}
    for relative, digest in expected.items():
        path = Path(relative) if isinstance(relative, str) else None
        if path is None or path.is_absolute() or ".." in path.parts or "\\" in relative:
            issues.append(f"非法资源路径: {relative}")
            continue
        if not isinstance(digest, str) or re.fullmatch(r"[a-f0-9]{64}", digest) is None:
            issues.append(f"非法哈希: {relative}")
            continue
        safe_expected[relative] = digest
    actual_paths = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != manifest_path
    }
    expected_paths = set(safe_expected)
    for relative in sorted(expected_paths - actual_paths):
        issues.append(f"资源缺失: {relative}")
    for relative in sorted(actual_paths - expected_paths):
        issues.append(f"未登记资源: {relative}")
    for relative in sorted(expected_paths & actual_paths):
        digest = hashlib.sha256((root / relative).read_bytes()).hexdigest()
        if digest != safe_expected[relative]:
            issues.append(f"哈希不匹配: {relative}")
    return issues


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("app_version")
    args = parser.parse_args()
    issues = verify_assets(args.root, args.app_version)
    for issue in issues:
        print(issue)
    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
