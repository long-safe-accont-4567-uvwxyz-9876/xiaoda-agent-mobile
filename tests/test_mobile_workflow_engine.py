from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from web.workflow_engine import WorkflowEngine


class FakeToolExecutor:
    def __init__(self) -> None:
        self.active = 0
        self.max_active = 0
        self.calls: list[tuple[str, dict]] = []

    async def execute(self, name: str, arguments: dict, user_id: str = "") -> SimpleNamespace:
        self.calls.append((name, dict(arguments)))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        await asyncio.sleep(0.04)
        self.active -= 1
        if name == "fail":
            return SimpleNamespace(success=False, data=None, error="intentional failure")
        return SimpleNamespace(success=True, data={"tool": name, "arguments": arguments}, error="")


class FakeDispatcher:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    async def dispatch(self, name: str, task: str, context: str = "", **_: object) -> str:
        self.calls.append((name, task, context))
        return f"agent:{name}:{task}"


class FakeCompletions:
    async def create(self, **kwargs: object) -> SimpleNamespace:
        model = str(kwargs.get("model"))
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=f"model:{model}"))]
        )


class FakeRouter:
    def __init__(self) -> None:
        self._registry = SimpleNamespace(
            get_task_ref=lambda _: {"client": "local", "model": "default-model"}
        )
        self.client = SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))

    async def _select_client_for_provider(self, provider: str) -> object:
        assert provider == "local"
        return self.client

    async def route(self, *_: object, **__: object) -> str:
        return '{"passed": true, "reason": "ok"}'


class FakeDB:
    async def insert_audit_log(self, *_: object) -> None:
        return None

    async def commit(self) -> None:
        return None


@pytest.fixture
def core(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    import config

    monkeypatch.setattr(config, "WORKSPACE_DIR", tmp_path / "workspace")
    config.WORKSPACE_DIR.mkdir(parents=True)
    return SimpleNamespace(
        tool_executor=FakeToolExecutor(),
        dispatcher=FakeDispatcher(),
        router=FakeRouter(),
        db=FakeDB(),
        context=SimpleNamespace(current_address_term="User"),
    )


@pytest.mark.asyncio
async def test_workflow_runs_independent_roots_in_parallel_and_persists(core: SimpleNamespace) -> None:
    workflow = {
        "id": "mobile-dag",
        "name": "Mobile DAG",
        "enabled": True,
        "nodes": [
            {"id": "left", "type": "tool", "ref": "left_tool", "params": {"value": "${variables.value}"}},
            {"id": "right", "type": "tool", "ref": "right_tool", "params": {"source": "{{input}}"}},
            {"id": "agent", "type": "agent", "ref": "helper", "params": {"task": "merge {{nodes.left}}"}},
            {"id": "model", "type": "model", "ref": "local/test-model", "expect": "must return text"},
        ],
        "edges": [["left", "agent"], ["right", "agent"], ["agent", "model"]],
    }
    engine = WorkflowEngine(core)
    result = await engine.start(
        workflow,
        input_text="phone input",
        variables={"value": 7},
        wait=True,
    )

    assert result["status"] == "success"
    assert core.tool_executor.max_active == 2
    assert ("left_tool", {"value": 7}) in core.tool_executor.calls
    assert ("right_tool", {"source": "phone input"}) in core.tool_executor.calls
    assert result["outputs"]["model"] == "model:test-model"
    assert result["nodes"][-1]["expectation"]["passed"] is True
    assert core.dispatcher.calls[0][0] == "helper"
    assert "left_tool" in core.dispatcher.calls[0][1]

    persisted = core.__dict__["tool_executor"]  # keep core strongly referenced during file assertion
    assert persisted is core.tool_executor
    run_file = Path(__import__("config").WORKSPACE_DIR) / "workflow_runs" / f"{result['id']}.json"
    assert run_file.is_file()
    restored = WorkflowEngine(core).get(result["id"])
    assert restored["status"] == "success"


@pytest.mark.asyncio
async def test_workflow_failure_skips_dependent_nodes(core: SimpleNamespace) -> None:
    engine = WorkflowEngine(core)
    result = await engine.start(
        {
            "id": "failure",
            "name": "Failure",
            "nodes": [
                {"id": "bad", "type": "tool", "ref": "fail"},
                {"id": "after", "type": "agent", "ref": "helper"},
            ],
            "edges": [["bad", "after"]],
        },
        wait=True,
    )

    assert result["status"] == "failed"
    assert result["nodes"][0]["status"] == "failed"
    assert result["nodes"][1]["status"] == "skipped"
    assert core.dispatcher.calls == []


def test_workflow_rejects_cycles(core: SimpleNamespace) -> None:
    with pytest.raises(ValueError, match="cycle"):
        WorkflowEngine._normalize_graph(
            {
                "nodes": [
                    {"id": "a", "type": "step", "note": "a"},
                    {"id": "b", "type": "step", "note": "b"},
                ],
                "edges": [["a", "b"], ["b", "a"]],
            }
        )
