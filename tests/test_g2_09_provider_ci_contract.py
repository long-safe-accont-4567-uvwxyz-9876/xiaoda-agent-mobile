from pathlib import Path


def test_provider_suite_is_a_strict_ci_gate():
    workflow = (Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci-tests.yml").read_text(encoding="utf-8")
    start = workflow.index("Run Provider tests (strict)")
    end = workflow.index("- name:", start + len("Run Provider tests (strict)"))
    step = workflow[start:end]
    for name in [
        "test_g2_01_error_protocol.py", "test_g2_01_provider_protocol.py",
        "test_g2_02_provider_urls.py", "test_g2_03_safe_outbound.py",
        "test_g2_04_provider_application_service.py", "test_g2_05_provider_references.py",
        "test_g2_06_provider_discovery.py", "test_g2_07_provider_diagnostics.py",
    ]:
        assert name in step
    assert "continue-on-error" not in step
    frontend_start = workflow.index("Run Provider frontend tests (strict)")
    frontend_end = workflow.index("- name:", frontend_start + len("Run Provider frontend tests (strict)"))
    frontend_step = workflow[frontend_start:frontend_end]
    assert "ProviderComponents.test.ts" in frontend_step
    assert "npm run typecheck" in frontend_step
    assert "continue-on-error" not in frontend_step
