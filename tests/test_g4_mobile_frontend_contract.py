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


def test_terminal_is_desktop_only_and_not_mounted_for_mobile():
    """终端仅在桌面 Web 挂载；移动断点与 Android WebView 均不挂载。

    依据 ADR-MOB2-009/010：生产移动终端已取消，ChatTerminal 组件保留给
    桌面 Web。防复活契约：ChatView 在 mobileWebBuild 构建下将 ChatTerminal
    置为 null，且移动断点/Android WebView 下 terminalAvailable 为 false。
    """
    chat_view = (FRONTEND / "views" / "ChatView.vue").read_text(encoding="utf-8")
    assert "mobileWebBuild" in chat_view
    assert "import.meta.env.VITE_XIAODA_MOBILE_BUILD" in chat_view
    assert "ChatTerminal = mobileWebBuild ? null" in chat_view
    assert "terminalAvailable" in chat_view
    assert "!androidWebView" in chat_view or "!isAndroidWebView()" in chat_view
    # 移动键盘适配特征不应出现在桌面终端组件中
    terminal = (FRONTEND / "components" / "chat" / "ChatTerminal.vue").read_text(encoding="utf-8")
    assert "visualViewport" not in terminal


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
