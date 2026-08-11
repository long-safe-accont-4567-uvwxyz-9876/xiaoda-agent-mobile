from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = ROOT / "web" / "frontend" / "src"


def _read(relative: str) -> str:
    return (FRONTEND_SRC / relative).read_text(encoding="utf-8")


def test_local_deploy_page_is_deleted():
    assert not (FRONTEND_SRC / "views" / "LocalDeployView.vue").exists()


def test_routes_and_navigation_do_not_expose_local_deploy():
    routes = _read("routes.ts")
    sidebar = _read("components/layout/SideBar.vue")
    assert "local-deploy" not in routes
    assert "LocalDeploy" not in routes
    assert "local-deploy" not in sidebar
    assert "localDeploy" not in sidebar


def test_translations_and_icons_do_not_contain_local_deploy():
    for relative in ("i18n/zh.ts", "i18n/en.ts"):
        text = _read(relative)
        assert "localDeploy" not in text
        assert "localDeployView" not in text
    icons = _read("components/fx/SumeruIcon.vue")
    assert "chip:" not in icons
    assert "本地部署" not in icons


def test_router_has_generic_not_found_page():
    routes = _read("routes.ts")
    not_found = FRONTEND_SRC / "views" / "NotFoundView.vue"
    assert "/:pathMatch(.*)*" in routes
    assert "NotFoundView.vue" in routes
    assert not_found.exists()
    text = not_found.read_text(encoding="utf-8")
    assert "local-deploy" not in text.lower()


def test_built_assets_do_not_contain_local_deploy_chunk():
    assets = ROOT / "web" / "dist" / "assets"
    assert not list(assets.glob("LocalDeployView-*"))
