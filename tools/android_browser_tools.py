"""Android-native browser automation tool.

On mobile this delegates to a dedicated hidden WebView owned by the Android shell.
It does not start Chromium, Playwright, Selenium, a desktop process, or a terminal.
"""
from __future__ import annotations

import json
import os
from typing import Any

from loguru import logger

from tool_engine.tool_registry import ToolPermission, ToolResult, register_tool


_android_browser_bridge: Any | None = None


def set_android_browser_bridge(bridge: Any) -> bool:
    """Install the live Android WebView bridge in this exact tool module."""
    global _android_browser_bridge
    if bridge is None:
        raise RuntimeError("Android browser automation bridge cannot be null")
    _android_browser_bridge = bridge
    return True


def _android_bridge() -> Any:
    if os.getenv("XIAODA_MOBILE") != "1":
        raise RuntimeError("Android browser automation is available only in the mobile app")
    if _android_browser_bridge is None:
        raise RuntimeError("Android browser automation bridge is not initialized")
    return _android_browser_bridge


@register_tool(
    name="browser_automation",
    description=(
        "使用手机本地 Android WebView 自动操作网页。支持 open/read/click/type/"
        "evaluate/scroll/back/reload/screenshot/state/close；页面和截图只在手机本地处理。"
    ),
    schema={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["open", "read", "click", "type", "evaluate", "scroll", "back", "reload", "screenshot", "state", "close"],
                "description": "要执行的浏览器动作",
            },
            "url": {"type": "string", "description": "open 动作要访问的 http/https URL"},
            "selector": {"type": "string", "description": "read/click/type 使用的 CSS 选择器；read 留空读取整页"},
            "value": {"type": "string", "description": "type 动作要输入的文本"},
            "script": {"type": "string", "description": "evaluate 动作执行的 JavaScript，脚本应使用 return 返回结果"},
            "delta_y": {"type": "integer", "description": "scroll 动作的垂直像素，默认 600", "default": 600},
            "name": {"type": "string", "description": "screenshot 的本地文件名"},
            "max_chars": {"type": "integer", "description": "read 返回的最大字符数，默认 20000", "default": 20000},
            "timeout_ms": {"type": "integer", "description": "动作超时毫秒数，范围 1000-120000", "default": 30000},
        },
        "required": ["action"],
    },
    permission=ToolPermission.EXECUTE,
    category="web",
    max_frequency=20,
)
def browser_automation(
    action: str,
    url: str = "",
    selector: str = "",
    value: str = "",
    script: str = "",
    delta_y: int = 600,
    name: str = "",
    max_chars: int = 20_000,
    timeout_ms: int = 30_000,
) -> ToolResult:
    request = {
        "action": (action or "").strip().lower(),
        "url": url or "",
        "selector": selector or "",
        "value": value or "",
        "script": script or "",
        "delta_y": int(delta_y),
        "name": name or "",
        "max_chars": max(1, min(int(max_chars), 200_000)),
        "timeout_ms": max(1_000, min(int(timeout_ms), 120_000)),
    }
    try:
        raw = str(_android_bridge().execute(json.dumps(request, ensure_ascii=False)))
        response = json.loads(raw)
    except Exception as exc:
        logger.warning("android_browser.execute_failed action={} error={}", request["action"], str(exc))
        return ToolResult.fail(str(exc))
    if not response.get("ok"):
        return ToolResult.fail(str(response.get("error") or "Android browser automation failed"))
    return ToolResult.ok(response.get("data") or {})
