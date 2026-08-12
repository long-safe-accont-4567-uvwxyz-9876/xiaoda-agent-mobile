"""Generate an SBOM (SPDX-lite JSON) and a NOTICE license archive for the Android release.

Sources covered:
- Android Gradle libraries (android/gradle/libs.versions.toml)
- Bundled Python packages (android/python-packages/*.whl|*.tar.gz)
- Frontend npm runtime dependencies (web/frontend/package.json -> dependencies)

The script is a deterministic, offline generator: package licensing metadata is
resolved through a small built-in table plus best-effort reading of the License
field from bundled wheel METADATA. Unknown licenses are recorded as
"SEE NOTICE" so a human can fill them in before release.

Outputs (default under android/app/build/release-artifacts/):
- sbom.spdx.json   : SPDX-lite document
- NOTICE           : human-readable license archive

Run:  python scripts/generate_sbom.py [output_dir]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# name(lowercase) -> (license_id, license_name)
KNOWN_LICENSES: dict[str, tuple[str, str]] = {
    # Python runtime deps (bundled in-app)
    "jieba": ("MIT", "MIT License"),
    "pdfplumber": ("MIT", "MIT License"),
    # Android / toolchain
    "androidx.core:core-ktx": ("Apache-2.0", "Apache License 2.0"),
    "androidx.appcompat:appcompat": ("Apache-2.0", "Apache License 2.0"),
    "androidx.webkit:webkit": ("Apache-2.0", "Apache License 2.0"),
    "androidx.test.ext:junit": ("Apache-2.0", "Apache License 2.0"),
    "androidx.test:core": ("Apache-2.0", "Apache License 2.0"),
    "androidx.test:runner": ("Apache-2.0", "Apache License 2.0"),
    "junit:junit": ("EPL-2.0", "Eclipse Public License 2.0"),
    "org.json:json": ("JSON", "The JSON License"),
    "com.squareup.okhttp3:mockwebserver": ("Apache-2.0", "Apache License 2.0"),
    # Frontend runtime
    "vue": ("MIT", "MIT License"),
    "vue-router": ("MIT", "MIT License"),
    "pinia": ("MIT", "MIT License"),
    "naive-ui": ("MIT", "MIT License"),
    "echarts": ("Apache-2.0", "Apache License 2.0"),
    "three": ("MIT", "MIT License"),
    "markdown-it": ("MIT", "MIT License"),
    "highlight.js": ("BSD-3-Clause", "BSD 3-Clause License"),
    "pinyin-pro": ("MIT", "MIT License"),
    "vuedraggable": ("MIT", "MIT License"),
    "@xterm/xterm": ("MIT", "MIT License"),
    "@xterm/addon-fit": ("MIT", "MIT License"),
    "@xterm/addon-unicode11": ("MIT", "MIT License"),
    "@xterm/addon-web-links": ("MIT", "MIT License"),
    "3d-force-graph": ("MIT", "MIT License"),
    # Server-side (documented for traceability; not bundled in APK)
    "fastapi": ("MIT", "MIT License"),
    "starlette": ("BSD-3-Clause", "BSD 3-Clause License"),
    "uvicorn": ("BSD-3-Clause", "BSD 3-Clause License"),
    "httpx": ("BSD-3-Clause", "BSD 3-Clause License"),
    "numpy": ("BSD-3-Clause", "BSD 3-Clause License"),
    "pillow": ("MIT-CMU", "MIT-CMU License"),
    "openai": ("Apache-2.0", "Apache License 2.0"),
    "loguru": ("MIT", "MIT License"),
}


def _wheel_metadata_license(path: Path) -> str | None:
    """Best-effort read of the License field from a bundled wheel METADATA."""
    try:
        with zipfile.ZipFile(path) as zf:
            name = next(n for n in zf.namelist() if n.endswith(".dist-info/METADATA"))
            text = zf.read(name).decode("utf-8", errors="replace")
        for idx, line in enumerate(text.splitlines()):
            if line.startswith("License:"):
                value = line.split(":", 1)[1].strip()
                # Multi-line continuations
                j = idx + 1
                while j < len(text.splitlines()) and text.splitlines()[j].startswith(" "):
                    value += " " + text.splitlines()[j].strip()
                    j += 1
                return value or None
    except Exception:
        return None
    return None


def _parse_python_archive(path: Path) -> tuple[str, str]:
    """Return (name, version) from a wheel or sdist file name."""
    stem = path.name
    m = re.search(r"^(.+?)-([0-9][^-]*)", stem)
    if not m:
        return stem, "unknown"
    name = m.group(1).replace("_", "-").replace(".", "-").lower()
    version = m.group(2)
    for suffix in (".tar.gz", ".tar.bz2", ".zip", ".whl"):
        if version.endswith(suffix):
            version = version[: -len(suffix)]
            break
    return name, version


def collect_python(patterns: list[str]) -> list[dict[str, Any]]:
    pkgs: list[dict[str, Any]] = []
    for pat in patterns:
        for p in ROOT.glob(pat):
            if not (p.suffix in (".whl", ".gz", ".zip") or p.name.endswith(".whl")):
                continue
            name, version = _parse_python_archive(p)
            lic = _wheel_metadata_license(p) or KNOWN_LICENSES.get(name, ("SEE NOTICE", "See NOTICE"))[0]
            pkgs.append({
                "name": name,
                "version": version,
                "license": lic,
                "source": str(p.relative_to(ROOT)),
            })
    return pkgs


def collect_android(toml_path: Path) -> list[dict[str, Any]]:
    text = toml_path.read_text(encoding="utf-8")
    versions: dict[str, str] = {}
    for m in re.finditer(r'^(\w+)\s*=\s*"([^"]+)"\s*$', text, re.MULTILINE):
        versions[m.group(1)] = m.group(2)
    libs: list[dict[str, Any]] = []
    lib_block = text.split("[libraries]", 1)[1].split("[plugins]", 1)[0]
    for line in lib_block.splitlines():
        line = line.strip()
        if not line or line.startswith("["):
            continue
        m = re.match(r'^(\S+)\s*=\s*\{\s*module\s*=\s*"([^"]+)"', line)
        if not m:
            continue
        key, module = m.group(1), m.group(2)
        vm = re.search(r'version\.ref\s*=\s*"(\w+)"', line)
        version = versions.get(vm.group(1), "unknown") if vm else "unknown"
        lic = KNOWN_LICENSES.get(module.lower(), ("SEE NOTICE", "See NOTICE"))[0]
        libs.append({"name": module, "version": version, "license": lic, "source": "android/gradle/libs.versions.toml"})
    return libs


def collect_frontend(package_json: Path) -> list[dict[str, Any]]:
    data = json.loads(package_json.read_text(encoding="utf-8"))
    deps = data.get("dependencies", {})
    out: list[dict[str, Any]] = []
    for name, ver in deps.items():
        lic = KNOWN_LICENSES.get(name.lower(), ("SEE NOTICE", "See NOTICE"))[0]
        out.append({"name": name, "version": ver, "license": lic, "source": "web/frontend/package.json"})
    out.sort(key=lambda d: d["name"])
    return out


def build_spdx(packages: list[dict[str, Any]], app_version: str) -> dict[str, Any]:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    spdx_id = "spdx.xiaoda-agent."
    packages_dec = []
    spdx_ids = []
    for i, p in enumerate(packages):
        pid = f"{spdx_id}{i}"
        spdx_ids.append(pid)
        packages_dec.append({
            "SPDXID": pid,
            "name": p["name"],
            "versionInfo": p["version"],
            "downloadLocation": "NOASSERTION",
            "licenseConcluded": p["license"] if p["license"] != "SEE NOTICE" else "NOASSERTION",
            "licenseDeclared": p["license"] if p["license"] != "SEE NOTICE" else "NOASSERTION",
            "copyrightText": "NOASSERTION",
            "sourceInfo": p["source"],
        })
    return {
        "spdxVersion": "SPDX-2.3",
        "dataLicense": "CC0-1.0",
        "SPDXID": "SPDXRef-DOCUMENT",
        "name": f"xiaoda-agent-android-v{app_version}",
        "documentNamespace": f"https://github.com/liu-runfe/xiaoda-agent/sbom/{app_version}-{now}",
        "creationInfo": {
            "created": now,
            "creators": ["Tool: generate_sbom.py"],
        },
        "packages": packages_dec,
        "relationships": [
            {
                "spdxElementId": "SPDXRef-DOCUMENT",
                "relationshipType": "DESCRIBES",
                "relatedSpdxElement": p,
            }
            for p in spdx_ids
        ],
    }


def build_notice(packages: list[dict[str, Any]], app_version: str) -> str:
    lines = [
        "Xiaoda Agent - Android - NOTICE",
        f"Version: {app_version}",
        "Generated by scripts/generate_sbom.py",
        "",
        "Third-party components and their licenses bundled in or referenced by this",
        "application. See each component's own license text for full terms.",
        "",
        "=" * 78,
    ]
    for p in sorted(packages, key=lambda d: d["name"].lower()):
        lines.append(f"{p['name']} {p.get('version', '')}  [{p.get('license', 'SEE NOTICE')}]")
    lines += [
        "",
        "Licenses referenced above:",
        "  MIT          https://opensource.org/licenses/MIT",
        "  Apache-2.0   https://www.apache.org/licenses/LICENSE-2.0",
        "  BSD-3-Clause https://opensource.org/licenses/BSD-3-Clause",
        "  EPL-2.0      https://www.eclipse.org/legal/epl-2.0/",
        "  JSON         https://www.json.org/license.html",
        "  MIT-CMU      https://opensource.org/license/mit-0-clarified-mit-cmu/",
        "",
        "Packages marked 'SEE NOTICE' require manual license confirmation before release.",
    ]
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate Android SBOM and NOTICE")
    ap.add_argument("out_dir", nargs="?", default=None, help="output directory (default: android/app/build/release-artifacts)")
    args = ap.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else ROOT / "android" / "app" / "build" / "release-artifacts"
    out_dir.mkdir(parents=True, exist_ok=True)

    version = re.search(r'^version\s*=\s*"([^"]+)"', (ROOT / "pyproject.toml").read_text(encoding="utf-8"), re.MULTILINE)
    app_version = version.group(1) if version else "0.0.0"

    packages: list[dict[str, Any]] = []
    packages += collect_python(["android/python-packages/*"])
    packages += collect_android(ROOT / "android" / "gradle" / "libs.versions.toml")
    packages += collect_frontend(ROOT / "web" / "frontend" / "package.json")

    spdx = build_spdx(packages, app_version)
    (out_dir / "sbom.spdx.json").write_text(json.dumps(spdx, indent=2), encoding="utf-8")
    (out_dir / "NOTICE").write_text(build_notice(packages, app_version), encoding="utf-8")

    see_notice = [p["name"] for p in packages if p["license"] == "SEE NOTICE"]
    print(f"SBOM + NOTICE written to {out_dir}")
    print(f"Packages: {len(packages)}; SEE NOTICE: {see_notice or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())