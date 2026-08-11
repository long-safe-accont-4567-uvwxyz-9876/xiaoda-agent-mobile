from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_local_deploy_router_is_deleted_and_unregistered():
    assert not (ROOT / "web" / "routers" / "local_deploy.py").exists()
    server = (ROOT / "web" / "server.py").read_text(encoding="utf-8")
    assert "local_deploy_router" not in server
    assert "web.routers.local_deploy" not in server


def test_config_defaults_do_not_restore_local_deploy():
    from web.config_service import ConfigService

    missing = object()
    service = ConfigService(path=ROOT / "missing-overrides.json")
    assert service.get("local_deploy", missing) is missing


def test_bootstrap_does_not_consume_local_deploy_override():
    bootstrap = (ROOT / "core" / "bootstrap.py").read_text(encoding="utf-8")
    assert "local_deploy" not in bootstrap


def test_fastapi_has_no_local_deploy_paths():
    from web.server import create_app

    app = create_app()
    paths = app.openapi()["paths"]
    assert not [path for path in paths if path.startswith("/api/v1/local-deploy")]


def test_shared_gpu_capabilities_remain_available():
    detector = (ROOT / "core" / "capability_detector.py").read_text(encoding="utf-8")
    vision_service = (ROOT / "utils" / "vision_service.py").read_text(encoding="utf-8")
    assert "nvidia-smi" in detector
    assert "rocm-smi" in detector
    assert "set_vulkan_device(gpu_index)" in vision_service
