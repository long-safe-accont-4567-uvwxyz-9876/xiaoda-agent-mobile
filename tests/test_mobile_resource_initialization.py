from pathlib import Path

import config


def test_static_mobile_defaults_are_copied_without_overwriting_user_files(tmp_path: Path) -> None:
    bundled = tmp_path / "bundled"
    user = tmp_path / "user"
    bundled.mkdir()
    user.mkdir()
    names = (
        "agent_routing.json",
        "agent_routing_v2.json",
        "persona_levels.yaml",
        "provider_metadata.json",
        "security_patterns.yaml",
    )
    for name in names:
        (bundled / name).write_text(f"bundled:{name}", encoding="utf-8")
    (user / "provider_metadata.json").write_text("user-owned", encoding="utf-8")

    config._init_static_config_files(bundled, user)

    for name in names:
        expected = "user-owned" if name == "provider_metadata.json" else f"bundled:{name}"
        assert (user / name).read_text(encoding="utf-8") == expected
