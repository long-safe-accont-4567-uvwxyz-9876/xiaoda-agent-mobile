from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from web import ws_hub


@pytest.fixture(autouse=True)
def clean_terminal_registry():
    with ws_hub._pty_sessions_lock:
        ws_hub._pty_sessions.clear()
        ws_hub._pty_pending.clear()
    yield
    with ws_hub._pty_sessions_lock:
        ws_hub._pty_sessions.clear()
        ws_hub._pty_pending.clear()


@pytest.mark.asyncio
async def test_terminal_start_rejects_invalid_sid_without_spawning(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(ws_hub.manager, "send_to", send)
    popen = Mock(side_effect=AssertionError("must not spawn"))
    monkeypatch.setattr(ws_hub, "_HAS_PTY", False)
    monkeypatch.setattr(ws_hub._subprocess, "Popen", popen)

    await ws_hub._handle_terminal_start("owner", {"shell": "cmd"}, "../../escape")

    popen.assert_not_called()
    event = send.await_args.args[1]
    assert event["type"] == "terminal_error"
    assert event["code"] == "INVALID_TERM_SID"


@pytest.mark.asyncio
async def test_terminal_start_rejects_duplicate_and_per_connection_limit(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(ws_hub.manager, "send_to", send)
    loop = asyncio.get_running_loop()
    with ws_hub._pty_sessions_lock:
        ws_hub._pty_sessions["same"] = {"conn_id": "owner", "alive": True, "loop": loop}

    await ws_hub._handle_terminal_start("owner", {}, "same")
    assert send.await_args.args[1]["code"] == "DUPLICATE_TERM_SID"

    send.reset_mock()
    with ws_hub._pty_sessions_lock:
        ws_hub._pty_sessions.clear()
        for index in range(ws_hub.TERMINAL_MAX_SESSIONS_PER_CONNECTION):
            ws_hub._pty_sessions[f"t{index}"] = {"conn_id": "owner", "alive": True, "loop": loop}

    await ws_hub._handle_terminal_start("owner", {}, "overflow")
    assert send.await_args.args[1]["code"] == "TERMINAL_SESSION_LIMIT"


@pytest.mark.asyncio
async def test_terminal_input_and_resize_enforce_limits_and_ownership(monkeypatch):
    writes: list[bytes] = []
    monkeypatch.setattr(ws_hub.os, "write", lambda _fd, data: writes.append(data))
    ioctl = Mock()
    monkeypatch.setattr(ws_hub, "fcntl", Mock(ioctl=ioctl), raising=False)
    monkeypatch.setattr(ws_hub, "termios", Mock(TIOCSWINSZ=1), raising=False)
    with ws_hub._pty_sessions_lock:
        ws_hub._pty_sessions["safe"] = {
            "conn_id": "owner", "alive": True, "is_windows": False, "fd": 7,
        }

    await ws_hub._handle_terminal_input("attacker", {"term_sid": "safe", "data": "whoami"})
    await ws_hub._handle_terminal_input("owner", {
        "term_sid": "safe", "data": "x" * (ws_hub.TERMINAL_MAX_INPUT_BYTES + 1),
    })
    assert writes == []

    await ws_hub._handle_terminal_input("owner", {"term_sid": "safe", "data": "pwd"})
    assert writes == [b"pwd"]

    ws_hub._handle_terminal_resize("owner", {"term_sid": "safe", "cols": 99999, "rows": -10})
    packed = ioctl.call_args.args[2]
    rows, cols, _, _ = ws_hub.struct.unpack("HHHH", packed)
    assert rows == ws_hub.TERMINAL_MIN_ROWS
    assert cols == ws_hub.TERMINAL_MAX_COLS


@pytest.mark.asyncio
async def test_terminal_input_write_does_not_block_event_loop(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()
    loop = asyncio.get_running_loop()

    def blocking_write(_fd: int, _data: bytes) -> None:
        asyncio.run_coroutine_threadsafe(_started(), loop).result(timeout=1)
        asyncio.run_coroutine_threadsafe(release.wait(), loop).result(timeout=1)

    async def _started() -> None:
        started.set()

    monkeypatch.setattr(ws_hub.os, "write", blocking_write)
    with ws_hub._pty_sessions_lock:
        ws_hub._pty_sessions["safe"] = {
            "conn_id": "owner", "alive": True, "is_windows": False, "fd": 7,
        }

    write_task = asyncio.create_task(ws_hub._handle_terminal_input(
        "owner", {"term_sid": "safe", "data": "pwd"},
    ))
    await asyncio.wait_for(started.wait(), timeout=0.5)
    await asyncio.wait_for(asyncio.sleep(0), timeout=0.2)
    release.set()
    await write_task


def test_cleanup_terminates_entire_process_tree(monkeypatch):
    loop = Mock()
    loop.call_soon_threadsafe = Mock()
    session = {
        "pid": 4242,
        "proc": Mock(),
        "conn_id": "owner",
        "alive": True,
        "loop": loop,
        "is_windows": True,
    }
    terminate_tree = Mock(return_value=23)
    monkeypatch.setattr(ws_hub, "_terminate_process_tree", terminate_tree)
    with ws_hub._pty_sessions_lock:
        ws_hub._pty_sessions["tree"] = session

    ws_hub._cleanup_pty("tree")

    terminate_tree.assert_called_once_with(session)
    assert "tree" not in ws_hub._pty_sessions


def test_windows_process_tree_fallback_uses_taskkill(monkeypatch):
    proc = Mock()
    proc.wait.side_effect = [TimeoutError(), 9]
    session = {"pid": 4242, "proc": proc, "is_windows": True}
    taskkill = Mock(return_value=0)
    monkeypatch.setattr(ws_hub, "_terminate_windows_process_tree", taskkill)

    assert ws_hub._terminate_process_tree(session) == 9

    taskkill.assert_called_once_with(4242)


def test_windows_process_tree_reports_taskkill_failure(monkeypatch):
    proc = Mock()
    proc.wait.side_effect = TimeoutError()
    monkeypatch.setattr(ws_hub, "_terminate_windows_process_tree", Mock(return_value=5))

    assert ws_hub._terminate_process_tree({
        "pid": 4242, "proc": proc, "is_windows": True,
    }) == -1
    proc.kill.assert_called_once()


def test_disconnect_cleanup_releases_pending_terminal_reservations():
    with ws_hub._pty_sessions_lock:
        ws_hub._pty_pending.update({"mine": "owner", "other": "peer"})

    ws_hub._cleanup_terminal_connection("owner")

    assert ws_hub._pty_pending == {"other": "peer"}


def test_disconnect_cleanup_only_terminates_owned_sessions(monkeypatch):
    loop = Mock()
    owned = {"conn_id": "owner", "alive": True, "loop": loop, "is_windows": True}
    foreign = {"conn_id": "peer", "alive": True, "loop": loop, "is_windows": True}
    with ws_hub._pty_sessions_lock:
        ws_hub._pty_sessions.update({"mine": owned, "other": foreign})
    cleanup = Mock()
    monkeypatch.setattr(ws_hub, "_cleanup_pty", cleanup)

    ws_hub._cleanup_terminal_connection("owner")

    cleanup.assert_called_once_with("mine")


def test_terminal_session_cannot_commit_after_owner_disconnects():
    session = {"conn_id": "owner", "alive": True}
    with ws_hub._pty_sessions_lock:
        ws_hub._pty_pending["late"] = "owner"

    ws_hub._cleanup_terminal_connection("owner")

    assert ws_hub._commit_terminal_session("owner", "late", session) is False
    assert "late" not in ws_hub._pty_sessions


@pytest.mark.asyncio
async def test_terminal_kill_cancels_owned_pending_start():
    with ws_hub._pty_sessions_lock:
        ws_hub._pty_pending["starting"] = "owner"

    await ws_hub._handle_terminal_kill("owner", {"term_sid": "starting"})

    assert "starting" not in ws_hub._pty_pending
    assert ws_hub._commit_terminal_session(
        "owner", "starting", {"conn_id": "owner", "alive": True},
    ) is False


@pytest.mark.asyncio
async def test_terminal_kill_cannot_cancel_foreign_pending_start():
    with ws_hub._pty_sessions_lock:
        ws_hub._pty_pending["starting"] = "owner"

    await ws_hub._handle_terminal_kill("attacker", {"term_sid": "starting"})

    assert ws_hub._pty_pending == {"starting": "owner"}


def test_unix_process_tree_uses_saved_process_group(monkeypatch):
    killpg = Mock()
    waitpid = Mock(return_value=(4242, 0))
    monkeypatch.setattr(ws_hub.os, "killpg", killpg, raising=False)
    monkeypatch.setattr(ws_hub.os, "waitpid", waitpid)
    monkeypatch.setattr(ws_hub.os, "WNOHANG", 1, raising=False)
    monkeypatch.setattr(ws_hub.os, "WIFEXITED", lambda _status: True, raising=False)
    monkeypatch.setattr(ws_hub.os, "WEXITSTATUS", lambda status: status, raising=False)

    rc = ws_hub._terminate_process_tree({
        "pid": 4242, "pgid": 4242, "is_windows": False,
    })

    assert rc == 0
    killpg.assert_called_once_with(4242, ws_hub.signal.SIGTERM)


@pytest.mark.asyncio
async def test_async_connection_cleanup_does_not_block_event_loop(monkeypatch):
    started = asyncio.Event()
    release = asyncio.Event()

    def slow_terminate(_session: dict) -> int:
        started_loop = asyncio.run_coroutine_threadsafe(_signal_started(), loop)
        started_loop.result(timeout=1)
        asyncio.run_coroutine_threadsafe(release.wait(), loop).result(timeout=1)
        return 0

    async def _signal_started() -> None:
        started.set()

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(ws_hub, "_terminate_process_tree", slow_terminate)
    with ws_hub._pty_sessions_lock:
        ws_hub._pty_sessions["slow"] = {
            "conn_id": "owner", "alive": True, "loop": loop,
            "is_windows": True, "pid": 4242,
        }

    cleanup_task = asyncio.create_task(ws_hub._cleanup_terminal_connection_async("owner"))
    await asyncio.wait_for(started.wait(), timeout=0.5)
    heartbeat_ran = False

    async def heartbeat() -> None:
        nonlocal heartbeat_ran
        await asyncio.sleep(0)
        heartbeat_ran = True

    await asyncio.wait_for(heartbeat(), timeout=0.2)
    assert heartbeat_ran is True
    release.set()
    await cleanup_task


@pytest.mark.asyncio
async def test_terminal_start_cleans_committed_session_when_reader_setup_fails(monkeypatch):
    send = AsyncMock()
    proc = Mock(pid=4242)
    cleanup = AsyncMock()
    monkeypatch.setattr(ws_hub.manager, "send_to", send)
    monkeypatch.setattr(ws_hub, "_HAS_PTY", False)
    monkeypatch.setattr(ws_hub._subprocess, "Popen", Mock(return_value=proc))
    monkeypatch.setattr(
        ws_hub, "_setup_win_pipe_reader", Mock(side_effect=RuntimeError("reader failed")),
    )
    monkeypatch.setattr(ws_hub, "_cleanup_pty_async", cleanup)

    await ws_hub._handle_terminal_start("owner", {"shell": "cmd"}, "reader-failure")

    cleanup.assert_awaited_once_with("reader-failure")


@pytest.mark.asyncio
async def test_terminal_start_reports_spawn_failure_before_commit(monkeypatch):
    send = AsyncMock()
    monkeypatch.setattr(ws_hub.manager, "send_to", send)
    monkeypatch.setattr(ws_hub, "_HAS_PTY", False)
    monkeypatch.setattr(
        ws_hub._subprocess, "Popen", Mock(side_effect=OSError("spawn failed")),
    )

    await ws_hub._handle_terminal_start("owner", {"shell": "cmd"}, "spawn-failure")

    assert send.await_args.args[1]["code"] == "TERMINAL_START_FAILED"
    assert "spawn-failure" not in ws_hub._pty_pending
