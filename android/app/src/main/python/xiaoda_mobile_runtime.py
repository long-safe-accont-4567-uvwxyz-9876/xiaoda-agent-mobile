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

def _configure_android_environment(files_dir: str, no_backup_dir: str, cache_dir: str, bundled_config: str = "") -> None:
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
    env = {
        "HOME": str(private_root),
        "XIAODA_MOBILE": "1",
        "XIAODA_ANDROID_FILES_DIR": str(home),
        "XIAODA_ANDROID_NO_BACKUP_DIR": str(Path(no_backup_dir).resolve()),
        "TMPDIR": str(Path(cache_dir).resolve()),
        "KIOXIA_DATA_DIR": str(data_root),
        "CREDENTIAL_SALT_FILE": str(private_root / ".ai-agent" / "config" / "credential_salt.bin"),
        "PYTHONUTF8": "1",
    }
    if bundled_config:
        # Chaquopy does not package the pure-data config/ directory, so the app
        # ships it as Android assets and copies them into app-private storage.
        # Point config._init_user_resources at that copy so it can seed the user
        # config dir (agent.json5, security_patterns.yaml, agents/, workspace/...).
        env["XIAODA_BUNDLED_CONFIG_DIR"] = str(Path(bundled_config).resolve())
    os.environ.update(env)
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
    _stderr = sys.stderr
    _stdout = sys.stdout
    try:
        _install_pydantic_compatibility()
        import asyncio
        import io
        import logging
        import uvicorn
        from web.server import app

        # 全量捕获诊断信息：uvicorn 的 lifespan 启动失败时只 logger.exception()
        # 后静默返回，异常不会向外抛出，导致 server.started 恒为 False 却看不到根因。
        # loguru（web/server.py 的 lifespan 用的就是它）默认写 sys.stderr，
        # 因此同时重定向 stderr/stdout 并让 uvicorn 日志走 DEBUG 级，才能拿到真实报错。
        log_buffer = io.StringIO()
        sys.stdout = log_buffer
        sys.stderr = log_buffer
        _uvicorn_handler = logging.StreamHandler(log_buffer)
        _uvicorn_handler.setFormatter(
            logging.Formatter("%(levelname)s %(name)s: %(message)s")
        )
        for _name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
            _uv_logger = logging.getLogger(_name)
            _uv_logger.handlers.clear()
            _uv_logger.setLevel(logging.DEBUG)
            _uv_logger.propagate = False
            _uv_logger.addHandler(_uvicorn_handler)

        config = uvicorn.Config(
            app,
            host=host,
            port=port,
            log_level="debug",
            access_log=False,
            ws="websockets",
            loop="asyncio",
            log_config=None,  # 阻止 uvicorn 内部 configure_logging 覆盖上面的 handler
        )
        server = uvicorn.Server(config)
        # Python 3.11 在非主线程中运行 asyncio/uvicorn 必须显式绑定一个事件循环，
        # 否则 uvicorn 无法在 Android 后台线程里监听端口（server.started 恒为 False）。
        asyncio.set_event_loop(asyncio.new_event_loop())
        _started.set()
        server.run()
        if not server.started and _server_error is None:
            _server_error = "Uvicorn stopped before accepting local connections"
            # 优先取 uvicorn 内部保存的真实 lifespan 异常（app 抛错时 uvicorn 会吞掉）
            _lifespan_exc = getattr(getattr(server, "lifespan", None), "exception", None)
            if _lifespan_exc is not None:
                import traceback as _tb
                _server_error += "\n--- lifespan exception ---\n" + "".join(
                    _tb.format_exception(type(_lifespan_exc), _lifespan_exc, _lifespan_exc.__traceback__)
                )
            _captured = log_buffer.getvalue().strip()
            if _captured:
                _server_error += "\n--- backend log ---\n" + _captured
    except BaseException:
        _server_error = traceback.format_exc()
        _started.set()
    finally:
        sys.stdout = _stdout
        sys.stderr = _stderr


def configure_environment(files_dir: str, no_backup_dir: str, cache_dir: str, bundled_config: str = "") -> dict[str, str]:
    """Configure HOME / data dirs / env BEFORE any module that imports config.

    Kotlin must call this before ``python.getModule("tools.android_browser_tools")``:
    importing that module transitively imports ``config.py``, which resolves
    ``Path.home()``-based paths at import time. If ``HOME`` is still the Chaquopy
    default (the app files dir), the backend would write to ``files/.ai-agent/``
    instead of the intended ``files/xiaoda/.ai-agent/``.
    """
    _configure_android_environment(files_dir, no_backup_dir, cache_dir, bundled_config)
    return dict(os.environ)


def start_server(files_dir: str, no_backup_dir: str, cache_dir: str, port: int = 8765, bundled_config: str = "") -> dict[str, Any]:
    """Start the original Xiaoda FastAPI application on Android loopback.

    Prefers a prior ``configure_environment`` call (so config.py is imported with
    the correct HOME), but re-runs the setup defensively in case start_server is
    invoked standalone.
    """
    global _server_thread
    _configure_android_environment(files_dir, no_backup_dir, cache_dir, bundled_config)
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


