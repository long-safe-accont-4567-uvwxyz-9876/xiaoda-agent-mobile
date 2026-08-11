from pathlib import Path

FRONTEND = Path(__file__).resolve().parents[1] / "web" / "frontend" / "src"
ROUTE_VIEWS = {
    "ChatView.vue", "InsightView.vue", "ScheduleView.vue", "MediaView.vue",
    "HealthView.vue", "DashboardView.vue", "AgentsView.vue", "ModelsView.vue",
    "ToolsView.vue", "McpView.vue", "PluginsView.vue", "MailView.vue",
    "SettingsView.vue", "WorkflowView.vue", "DisclaimerView.vue", "SponsorView.vue",
}


def test_all_g4_routes_are_covered_by_shared_mobile_styles():
    css = (FRONTEND / "styles" / "mobile-pages.css").read_text(encoding="utf-8")
    routes = (FRONTEND / "routes.ts").read_text(encoding="utf-8")
    for view in ROUTE_VIEWS:
        assert view in routes, f"{view} missing from production routes"
    assert "@media (max-width: 767px)" in css
    assert "(orientation: landscape)" in css
    assert "min-height: 48px" in css
    assert "overflow-x: auto" in css
    assert "overflow-x: clip" in css


def test_terminal_component_is_mobile_sheet_and_keeps_sessions_alive():
    source = (FRONTEND / "components" / "chat" / "ChatTerminal.vue").read_text(encoding="utf-8")
    assert "visualViewport" in source
    assert "aria-modal=\"true\"" in source
    assert "term-sheet-scrim" in source
    assert "sheet-height" in source
    assert "confirm" in source.lower()
    assert 'v-show="panelOpen"' in source
    assert "safe-area-inset-bottom" in source
    assert "terminal_started" in source
    assert "terminal_error" in source
    assert "starting" in source
    assert "orientationchange" in source
    assert "terminal_resize" in source


def test_terminal_sheet_has_disconnect_and_accessibility_contract():
    source = (FRONTEND / "components" / "chat" / "ChatTerminal.vue").read_text(encoding="utf-8")
    for token in [
        "ws_disconnected", "trapFocus", "aria-live=\"polite\"",
        "role=\"tablist\"", "role=\"tab\"", ":aria-selected",
        "@keydown=\"handlePanelKeydown\"", "@keydown=\"handleTabKeydown",
    ]:
        assert token in source


def test_agent_shell_execution_isolated_from_interactive_terminal():
    source = (
        Path(__file__).resolve().parents[1] / "tools" / "file_tools_v2.py"
    ).read_text(encoding="utf-8")
    shell_body = source.split("async def shell_command", 1)[1].split("@register_tool", 1)[0]
    assert "execute_on_pty" not in shell_body
    assert 'execute_on_pty("all"' not in source


def test_wallpaper_backdrop_has_focus_overlay_motion_and_memory_degrade_contract():
    source = (FRONTEND / "components" / "layout" / "AgentBackdrop.vue").read_text(encoding="utf-8")
    for token in [
        "wallpaper_focus", "wallpaper_overlay", "wallpaper_motion",
        "backgroundPosition", "prefers-reduced-motion", "memorypressure",
        "backdrop-local-mask", "performanceTier",
    ]:
        assert token in source
