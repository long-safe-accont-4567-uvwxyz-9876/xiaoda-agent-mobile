from __future__ import annotations

import os

import pytest

from tools import code_tools_v2


@pytest.fixture
def mobile_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XIAODA_MOBILE", "1")


def test_mobile_python_executor_runs_in_embedded_interpreter(mobile_runtime: None) -> None:
    result = code_tools_v2.python_executor(
        "import json\nvalues = [n * n for n in range(5)]\nprint(json.dumps(values))\n_result = sum(values)"
    )
    assert result.success is True
    assert "[0, 1, 4, 9, 16]" in str(result.data)
    assert "result: 30" in str(result.data)


def test_mobile_python_executor_blocks_file_and_system_access(mobile_runtime: None) -> None:
    blocked_import = code_tools_v2.python_executor("import os\n_result = os.getcwd()")
    blocked_open = code_tools_v2.python_executor("_result = open('secret.txt').read()")
    assert blocked_import.success is False
    assert "os" in blocked_import.error
    assert blocked_open.success is False
    assert "open" in blocked_open.error


def test_mobile_python_executor_enforces_instruction_budget(
    mobile_runtime: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(code_tools_v2, "_MOBILE_MAX_TRACE_EVENTS", 500)
    result = code_tools_v2.python_executor("while True:\n    pass")
    assert result.success is False
    assert "step budget" in result.error


def test_desktop_path_remains_subprocess_based(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("XIAODA_MOBILE", raising=False)
    called = {"value": False}

    class FakeProcess:
        pid = 1

        def communicate(self, input: bytes, timeout: int):
            called["value"] = True
            return b"desktop\n", b""

    monkeypatch.setattr(code_tools_v2.os, "pipe", lambda: (10, 11))
    monkeypatch.setattr(code_tools_v2.os, "close", lambda _fd: None)
    monkeypatch.setattr(code_tools_v2.os, "read", lambda _fd, _size: b"")
    monkeypatch.setattr(code_tools_v2.subprocess, "Popen", lambda *args, **kwargs: FakeProcess())
    result = code_tools_v2.python_executor("print(1)")
    assert called["value"] is True
    assert result.success is True
    assert "desktop" in str(result.data)
