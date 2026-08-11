"""Wallpaper configuration validation and backward-compatible defaults."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

DEFAULT_WALLPAPER_FOCUS = {"x": 0.5, "y": 0.5}
DEFAULT_WALLPAPER_OVERLAY = 0.28
DEFAULT_WALLPAPER_MOTION = "auto"
WALLPAPER_MOTION_VALUES = frozenset({"auto", "reduced", "none"})
WALLPAPER_FIELDS = (
    "wallpaper",
    "wallpaper_focus",
    "wallpaper_overlay",
    "wallpaper_motion",
)


def _unit_float(value: Any, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} 必须是 0 到 1 之间的数字")
    number = float(value)
    if not 0.0 <= number <= 1.0:
        raise ValueError(f"{field} 必须在 0 到 1 之间")
    return number


def _focus(value: Any) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError("wallpaper_focus 必须包含 x 和 y")
    if "x" not in value or "y" not in value:
        raise ValueError("wallpaper_focus 必须包含 x 和 y")
    return {
        "x": _unit_float(value["x"], "wallpaper_focus.x"),
        "y": _unit_float(value["y"], "wallpaper_focus.y"),
    }


def normalize_wallpaper_fields(
    payload: Mapping[str, Any] | None,
    *,
    current: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a complete validated wallpaper record.

    Missing fields are filled from ``current`` and then from stable defaults, so
    pre-G4 records containing only ``wallpaper`` remain valid and reversible.
    """
    payload = payload or {}
    current = current or {}

    wallpaper = payload.get("wallpaper", current.get("wallpaper", ""))
    if wallpaper is None:
        wallpaper = ""
    if not isinstance(wallpaper, str):
        raise ValueError("wallpaper 必须是字符串")

    focus_value = payload.get(
        "wallpaper_focus",
        current.get("wallpaper_focus", DEFAULT_WALLPAPER_FOCUS),
    )
    overlay_value = payload.get(
        "wallpaper_overlay",
        current.get("wallpaper_overlay", DEFAULT_WALLPAPER_OVERLAY),
    )
    motion = payload.get(
        "wallpaper_motion",
        current.get("wallpaper_motion", DEFAULT_WALLPAPER_MOTION),
    )
    if motion not in WALLPAPER_MOTION_VALUES:
        allowed = ", ".join(sorted(WALLPAPER_MOTION_VALUES))
        raise ValueError(f"wallpaper_motion 必须是以下值之一：{allowed}")

    return {
        "wallpaper": wallpaper,
        "wallpaper_focus": deepcopy(_focus(focus_value)),
        "wallpaper_overlay": _unit_float(overlay_value, "wallpaper_overlay"),
        "wallpaper_motion": motion,
    }
