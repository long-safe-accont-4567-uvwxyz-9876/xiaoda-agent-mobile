from pathlib import Path
import re


def read_project_version(root: Path) -> str:
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', text)
    if match is None:
        raise ValueError("project version not found")
    return match.group(1)


if __name__ == "__main__":
    print(read_project_version(Path(__file__).resolve().parents[1]))
