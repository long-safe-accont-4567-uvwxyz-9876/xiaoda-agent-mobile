"""Android entry point for the full Xiaoda Python backend.

This module only adapts process paths and runtime compatibility. The application and
all API routes are still provided by the original ``web.server`` module.
"""
from __future__ import annotations

import os
import shutil
import sys
import threading
import traceback
from pathlib import Path
from typing import Any

_server_thread: threading.Thread | None = None
_server_error: str | None = None
_started = threading.Event()


def _copy_missing_file(source: Path, target: Path) -> None:
    if source.is_file() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)


def _migrate_legacy_android_data(data_root: Path) -> None:
    """Move mutable files written by early mobile builds out of AssetFinder.

    The first embedded-runtime prototype let desktop fallback paths resolve
    relative to ``config.py``. On Chaquopy this is the extracted Python source
    directory. Copy only known mutable artifacts so repository modules are
    never mistaken for user data.
    """
    legacy_root = Path(__file__).resolve().parent
    legacy_db = legacy_root / "db"
    target_db = data_root / "db"
    for name in ("agent.db", "agent.db-wal", "agent.db-shm"):
        _copy_missing_file(legacy_db / name, target_db / name)
    for pattern in ("agent.db.backup*", "agent_*.db", "*.sqlite", "*.sqlite3"):
        for source in legacy_db.glob(pattern):
            _copy_missing_file(source, target_db / source.name)

    for directory in ("media", "files", "logs"):
        source_root = legacy_root / directory
        target_root = data_root / directory
        if not source_root.is_dir():
            continue
        for source in source_root.rglob("*"):
            if source.is_file():
                _copy_missing_file(source, target_root / source.relative_to(source_root))

def _configure_android_environment(files_dir: str, no_backup_dir: str, cache_dir: str) -> None:
    home = Path(files_dir).resolve()
    private_root = home / "xiaoda"
    data_root = private_root / ".ai-agent" / "data"
    private_root.mkdir(parents=True, exist_ok=True)
    # config._resolve_data_path deliberately treats a configured-but-missing
    # KIOXIA_DATA_DIR as an unavailable removable drive. Android uses the same
    # variable for its private durable store, so its parent must exist before
    # importing config or the backend would write into Chaquopy's extracted
    # source tree instead of the user's app data directory.
    data_root.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_android_data(data_root)
    os.environ.update(
        {
            "HOME": str(private_root),
            "XIAODA_MOBILE": "1",
            "XIAODA_ANDROID_FILES_DIR": str(home),
            "XIAODA_ANDROID_NO_BACKUP_DIR": str(Path(no_backup_dir).resolve()),
            "TMPDIR": str(Path(cache_dir).resolve()),
            "KIOXIA_DATA_DIR": str(data_root),
            "CREDENTIAL_SALT_FILE": str(private_root / ".ai-agent" / "config" / "credential_salt.bin"),
            "PYTHONUTF8": "1",
        }
    )
    os.chdir(private_root)


def _install_pydantic_compatibility() -> None:
    """Expose the Pydantic 2 names used by Xiaoda when Android runs Pydantic 1."""
    import pydantic

    if not hasattr(pydantic, "field_validator"):
        pydantic.field_validator = pydantic.validator  # type: ignore[attr-defined]
    base_model = pydantic.BaseModel
    if not hasattr(base_model, "model_dump"):
        base_model.model_dump = base_model.dict  # type: ignore[attr-defined]
    if not hasattr(base_model, "model_dump_json"):
        base_model.model_dump_json = base_model.json  # type: ignore[attr-defined]
    if not hasattr(base_model, "model_validate"):
        base_model.model_validate = classmethod(lambda cls, value: cls.parse_obj(value))  # type: ignore[attr-defined]


def _run_server(host: str, port: int) -> None:
    global _server_error
    try:
        _install_pydantic_compatibility()
        import uvicorn
        from web.server import app

        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="info",
            access_log=False,
            ws="websockets",
            loop="asyncio",
        )
        server = uvicorn.Server(config)
        _started.set()
        server.run()
        if not server.started and _server_error is None:
            _server_error = "Uvicorn stopped before accepting local connections"
    except BaseException:
        _server_error = traceback.format_exc()
        _started.set()


def start_server(files_dir: str, no_backup_dir: str, cache_dir: str, port: int = 8765) -> dict[str, Any]:
    """Start the original Xiaoda FastAPI application on Android loopback."""
    global _server_thread
    _configure_android_environment(files_dir, no_backup_dir, cache_dir)
    if _server_thread is None or not _server_thread.is_alive():
        _server_thread = threading.Thread(
            target=_run_server,
            args=("127.0.0.1", int(port)),
            name="xiaoda-python-backend",
            daemon=True,
        )
        _server_thread.start()
    _started.wait(timeout=30)
    return {
        "started": _server_thread.is_alive() and _server_error is None,
        "port": int(port),
        "error": _server_error or "",
        "python": sys.version,
    }


def startup_error() -> str:
    return _server_error or ""


