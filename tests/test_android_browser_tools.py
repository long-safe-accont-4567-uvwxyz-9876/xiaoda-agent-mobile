from __future__ import annotations

import json
from tools.android_browser_tools import browser_automation, set_android_browser_bridge


class FakeAndroidBrowser:
    requests: list[dict] = []

    @classmethod
    def execute(cls, payload: str) -> str:
        request = json.loads(payload)
        cls.requests.append(request)
        if request["action"] == "read":
            return json.dumps({"ok": True, "data": {"value": {"title": "Local", "text": "hello"}}})
        return json.dumps({"ok": False, "error": "failed"})


def test_android_browser_tool_delegates_to_native_webview(monkeypatch):
    FakeAndroidBrowser.requests.clear()
    monkeypatch.setenv("XIAODA_MOBILE", "1")
    set_android_browser_bridge(FakeAndroidBrowser)

    result = browser_automation("read", selector="#content", max_chars=1234)

    assert result.success is True
    assert result.data["value"]["text"] == "hello"
    assert FakeAndroidBrowser.requests == [{
        "action": "read",
        "url": "",
        "selector": "#content",
        "value": "",
        "script": "",
        "delta_y": 600,
        "name": "",
        "max_chars": 1234,
        "timeout_ms": 30000,
    }]


def test_android_browser_tool_surfaces_native_error(monkeypatch):
    monkeypatch.setenv("XIAODA_MOBILE", "1")
    set_android_browser_bridge(FakeAndroidBrowser)
    result = browser_automation("click", selector="#missing")
    assert result.success is False
    assert result.error == "failed"


def test_android_browser_tool_rejects_desktop_runtime(monkeypatch):
    monkeypatch.delenv("XIAODA_MOBILE", raising=False)
    result = browser_automation("state")
    assert result.success is False
    assert "mobile app" in result.error
