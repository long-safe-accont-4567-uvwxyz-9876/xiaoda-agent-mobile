from security.security import SecurityFilter


def test_retired_device_identity_is_still_filtered_as_private():
    security = SecurityFilter(owner_ids=["owner"])

    safe, replacement, matches = security.check_output_privacy("服务运行在 Orange Pi 5 Plus 上")

    assert safe is False
    assert replacement
    assert matches
