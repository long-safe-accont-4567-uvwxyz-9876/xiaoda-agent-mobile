"""Local Android workflow execution engine.

Workflow definitions and run records are stored under ``WORKSPACE_DIR``.
Orchestration, dependency resolution, state tracking, and tool/Agent calls run in the embedded Android Python process.
Only model nodes call the user-configured model Provider.
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from loguru import logger

from core.parallel_dag import NodeState, ToolDAG


class WorkflowExecutionError(RuntimeError):
    """Raised when a workflow or node cannot be executed."""


class WorkflowEngine:
    """Execute and persist local workflows with DAG concurrency and cancellation."""

    def __init__(self, core: Any) -> None:
        self.core = core
        self._tasks: dict[str, asyncio.Task[Any]] = {}
        self._records: dict[str, dict[str, Any]] = {}
        self._persist_lock = asyncio.Lock()

    @staticmethod
    def _runs_dir() -> Path:
        from config import WORKSPACE_DIR

        path = WORKSPACE_DIR / "workflow_runs"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @classmethod
    def _run_path(cls, run_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{16,32}", run_id or ""):
            raise WorkflowExecutionError("?? ID ??")
        return cls._runs_dir() / f"{run_id}.json"

    async def start(
        self,
        workflow: dict[str, Any],
        *,
        input_text: str = "",
        variables: dict[str, Any] | None = None,
        user_id: str = "webui",
        wait: bool = False,
    ) -> dict[str, Any]:
        """Create a private run record and start execution in this app process."""
        nodes, dependencies = self._normalize_graph(workflow)
        run_id = uuid.uuid4().hex[:20]
        now = time.time()
        record: dict[str, Any] = {
            "id": run_id,
            "workflow_id": str(workflow.get("id") or "adhoc"),
            "name": str(workflow.get("name") or workflow.get("id") or "未命名工作流"),
            "status": "pending",
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "input": input_text,
            "variables": self._json_safe(variables or {}),
            "nodes": [
                {
                    "id": node["id"],
                    "type": node["type"],
                    "label": node.get("label") or node["id"],
                    "ref": node.get("ref", ""),
                    "depends_on": dependencies[node["id"]],
                    "status": "pending",
                    "started_at": None,
                    "finished_at": None,
                    "duration_ms": 0,
                    "output": None,
                    "error": "",
                    "expectation": None,
                }
                for node in nodes
            ],
            "outputs": {},
            "error": "",
        }
        self._records[run_id] = record
        await self._persist(record)
        task = asyncio.create_task(
            self._execute(run_id, workflow, nodes, dependencies, input_text, variables or {}, user_id),
            name=f"workflow-{run_id}",
        )
        self._tasks[run_id] = task
        task.add_done_callback(lambda _task, rid=run_id: self._tasks.pop(rid, None))
        if wait:
            await task
        return self.get(run_id)

    def get(self, run_id: str) -> dict[str, Any]:
        record = self._records.get(run_id)
        if record is not None:
            return self._json_safe(record)
        path = self._run_path(run_id)
        if not path.exists():
            raise KeyError(run_id)
        record = json.loads(path.read_text(encoding="utf-8"))
        # A running task cannot survive Android process death; mark stale records interrupted.
        if record.get("status") in {"pending", "running"} and run_id not in self._tasks:
            record["status"] = "interrupted"
            record["error"] = "应用进程在工作流完成前被系统停止"
            record["finished_at"] = time.time()
            self._write_record_sync(record)
        self._records[run_id] = record
        return self._json_safe(record)

    def list_runs(self, workflow_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in self._runs_dir().glob("*.json"):
            try:
                item = json.loads(path.read_text(encoding="utf-8"))
                if workflow_id and item.get("workflow_id") != workflow_id:
                    continue
                if item.get("status") in {"pending", "running"} and item.get("id") not in self._tasks:
                    item["status"] = "interrupted"
                    item["error"] = "应用进程在工作流完成前被系统停止"
                    item["finished_at"] = time.time()
                    self._write_record_sync(item)
                records.append(item)
            except (OSError, ValueError, TypeError):
                logger.warning("workflow.run_record_invalid file={}", path.name)
        records.sort(key=lambda item: float(item.get("created_at") or 0), reverse=True)
        return self._json_safe(records[: max(1, min(limit, 200))])

    async def cancel(self, run_id: str) -> dict[str, Any]:
        record = self.get(run_id)
        task = self._tasks.get(run_id)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        elif record.get("status") not in {"success", "failed", "cancelled", "interrupted"}:
            record["status"] = "cancelled"
            record["finished_at"] = time.time()
            await self._persist(record)
        return self.get(run_id)

    async def _execute(
        self,
        run_id: str,
        workflow: dict[str, Any],
        nodes: list[dict[str, Any]],
        dependencies: dict[str, list[str]],
        input_text: str,
        variables: dict[str, Any],
        user_id: str,
    ) -> None:
        record = self._records[run_id]
        record["status"] = "running"
        record["started_at"] = time.time()
        await self._persist(record)
        dag = ToolDAG(max_concurrency=max(1, min(int(workflow.get("max_concurrency") or 4), 8)))
        outputs: dict[str, Any] = {}

        for node in nodes:
            node_id = node["id"]

            async def handler(_node: dict[str, Any] = node) -> Any:
                node_record = self._node_record(record, _node["id"])
                node_record["status"] = "running"
                node_record["started_at"] = time.time()
                await self._persist(record)
                try:
                    result = await self._execute_node(
                        _node,
                        input_text=input_text,
                        variables=variables,
                        outputs=outputs,
                        dependencies=dependencies[_node["id"]],
                        user_id=user_id,
                    )
                    expectation = await self._check_expectation(_node, result, input_text, outputs)
                    outputs[_node["id"]] = self._json_safe(result)
                    record["outputs"] = self._json_safe(outputs)
                    node_record["output"] = self._json_safe(result)
                    node_record["expectation"] = expectation
                    node_record["status"] = "success"
                    return result
                except asyncio.CancelledError:
                    node_record["status"] = "cancelled"
                    raise
                except Exception as exc:
                    node_record["status"] = "failed"
                    node_record["error"] = str(exc)
                    raise
                finally:
                    node_record["finished_at"] = time.time()
                    started = float(node_record.get("started_at") or node_record["finished_at"])
                    node_record["duration_ms"] = int((node_record["finished_at"] - started) * 1000)
                    await self._persist(record)

            dag.add_node(
                node_id,
                handler,
                depends_on=dependencies[node_id],
                timeout=float(node.get("timeout") or workflow.get("node_timeout") or 180),
                retries=max(0, min(int(node.get("retries") or 0), 3)),
            )

        try:
            result = await dag.execute()
            for node_id, dag_node in result.nodes.items():
                node_record = self._node_record(record, node_id)
                if dag_node.state == NodeState.SKIPPED:
                    node_record["status"] = "skipped"
                    node_record["error"] = "上游节点失败，未执行"
                    node_record["finished_at"] = time.time()
            record["outputs"] = self._json_safe(outputs)
            if result.failed_count:
                record["status"] = "failed"
                failures = [
                    f"{name}: {node.error}"
                    for name, node in result.nodes.items()
                    if node.state == NodeState.FAILED
                ]
                record["error"] = "; ".join(failures) or "工作流节点执行失败"
            else:
                record["status"] = "success"
        except asyncio.CancelledError:
            record["status"] = "cancelled"
            record["error"] = "运行已取消"
            raise
        except Exception as exc:
            record["status"] = "failed"
            record["error"] = str(exc)
            logger.exception("workflow.execute_failed run_id={}", run_id)
        finally:
            record["finished_at"] = time.time()
            await self._persist(record)
            try:
                await self.core.db.insert_audit_log(
                    "webui.workflows.run",
                    user_id,
                    json.dumps(
                        {
                            "run_id": run_id,
                            "workflow_id": record["workflow_id"],
                            "status": record["status"],
                        },
                        ensure_ascii=False,
                    ),
                )
                await self.core.db.commit()
            except Exception:
                logger.debug("workflow.run_audit_failed", exc_info=True)

    async def _execute_node(
        self,
        node: dict[str, Any],
        *,
        input_text: str,
        variables: dict[str, Any],
        outputs: dict[str, Any],
        dependencies: list[str],
        user_id: str,
    ) -> Any:
        scope = {
            "input": input_text,
            "variables": variables,
            "nodes": outputs,
            "dependencies": {name: outputs.get(name) for name in dependencies},
        }
        params = self._render_value(node.get("params") or {}, scope)
        note = str(self._render_value(node.get("note") or "", scope))
        ref = str(node.get("ref") or "").strip()
        node_type = node["type"]

        if node_type in {"tool", "mcp"}:
            return await self._run_tool(ref, params, user_id)
        if node_type == "agent":
            if not ref:
                raise WorkflowExecutionError("Agent 节点未选择目标 Agent")
            task = str(params.pop("task", "") or note or input_text or "请根据工作流上下文完成任务")
            context = self._context_text(input_text, variables, outputs, dependencies)
            result = await self.core.dispatcher.dispatch(
                ref,
                task,
                context=context,
                status_callback=None,
                address_term=getattr(self.core.context, "current_address_term", "??"),
            )
            if not result:
                raise WorkflowExecutionError(f"Agent {ref} 不可用或未返回结果")
            return result
        if node_type == "model":
            return await self._run_model(ref, note, params, input_text, variables, outputs, dependencies)
        if node_type == "skill":
            return await self._run_skill(ref, note, params, input_text, variables, outputs, dependencies, user_id)
        if node_type == "step":
            instruction = note or str(params.pop("instruction", ""))
            if not instruction:
                raise WorkflowExecutionError("步骤说明节点缺少操作说明")
            return await self._run_prompt(instruction, input_text, variables, outputs, dependencies, params)
        raise WorkflowExecutionError(f"不支持的节点类型: {node_type}")

    async def _run_tool(self, ref: str, params: dict[str, Any], user_id: str) -> Any:
        if not ref:
            raise WorkflowExecutionError("工具节点未选择工具")
        result = await self.core.tool_executor.execute(ref, params, user_id=user_id)
        if not getattr(result, "success", False):
            raise WorkflowExecutionError(getattr(result, "error", "工具执行失败") or "工具执行失败")
        return getattr(result, "data", result)

    async def _run_skill(
        self,
        ref: str,
        note: str,
        params: dict[str, Any],
        input_text: str,
        variables: dict[str, Any],
        outputs: dict[str, Any],
        dependencies: list[str],
        user_id: str,
    ) -> Any:
        if not ref:
            raise WorkflowExecutionError("技能节点未选择技能")
        # Compatibility: older UI versions allowed tools in the skill selector.
        from tool_engine.tool_registry import get_tool

        if get_tool(ref):
            return await self._run_tool(ref, params, user_id)
        if not re.fullmatch(r"[\w一-鿿.-]{1,128}", ref):
            raise WorkflowExecutionError("技能名称非法")
        from config import WORKSPACE_DIR

        skill_path = WORKSPACE_DIR / "skills" / (ref if ref.endswith(".md") else f"{ref}.md")
        if not skill_path.exists():
            raise WorkflowExecutionError(f"技能 {ref} 不存在")
        skill = skill_path.read_text(encoding="utf-8-sig").strip()
        instruction = skill + (f"\n\n本节点补充说明：{note}" if note else "")
        return await self._run_prompt(instruction, input_text, variables, outputs, dependencies, params)

    async def _run_prompt(
        self,
        instruction: str,
        input_text: str,
        variables: dict[str, Any],
        outputs: dict[str, Any],
        dependencies: list[str],
        params: dict[str, Any],
    ) -> str:
        messages = [
            {
                "role": "system",
                "content": "你正在执行手机本地工作流。严格完成当前节点，不要跳过，不要声称执行了未执行的操作。\n\n" + instruction,
            },
            {
                "role": "user",
                "content": self._context_text(input_text, variables, outputs, dependencies),
            },
        ]
        response = await self.core.router.route(
            str(params.pop("task_type", "chat") or "chat"),
            messages,
            temperature=float(params.pop("temperature", 0.2)),
            max_tokens=int(params.pop("max_tokens", 4096)),
        )
        text = self._extract_text(response)
        if not text:
            raise WorkflowExecutionError("模型未返回文本")
        return text

    async def _run_model(
        self,
        ref: str,
        note: str,
        params: dict[str, Any],
        input_text: str,
        variables: dict[str, Any],
        outputs: dict[str, Any],
        dependencies: list[str],
    ) -> str:
        provider = ""
        model = ""
        if "/" in ref:
            provider, model = ref.split("/", 1)
        if not provider or not model:
            route = self.core.router._registry.get_task_ref("chat") or {}
            provider = provider or str(route.get("client") or route.get("provider") or "")
            model = model or str(route.get("model") or "")
        if not provider or not model:
            raise WorkflowExecutionError("模型节点未选择有效的 Provider/模型")
        client = await self.core.router._select_client_for_provider(provider)
        messages = [
            {
                "role": "system",
                "content": note or "你正在执行手机本地工作流中的模型节点，请只完成当前节点。",
            },
            {
                "role": "user",
                "content": self._context_text(input_text, variables, outputs, dependencies),
            },
        ]
        response = await client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=float(params.pop("temperature", 0.2)),
            max_tokens=int(params.pop("max_tokens", 4096)),
            stream=False,
            **params,
        )
        text = self._extract_text(response)
        if not text:
            raise WorkflowExecutionError("模型节点未返回文本")
        return text

    async def _check_expectation(
        self,
        node: dict[str, Any],
        result: Any,
        input_text: str,
        outputs: dict[str, Any],
    ) -> dict[str, Any] | None:
        expect = str(node.get("expect") or "").strip()
        if not expect:
            return None
        prompt = (
            "判断下面的工作流节点输出是否满足预期。只输出 JSON："
            '{"passed":true 或 false,"reason":"简短中文理由"}。\n'
            f"原始输入：{input_text}\n预期：{expect}\n节点输出：{self._format_value(result)}\n"
            f"已有上游输出：{self._format_value(outputs)}"
        )
        response = await self.core.router.route(
            "tool_result_wrap",
            [{"role": "system", "content": "你是严格的工作流验收器。"}, {"role": "user", "content": prompt}],
            temperature=0,
            max_tokens=512,
        )
        text = self._extract_text(response)
        match = re.search(r"\{.*\}", text, re.S)
        if not match:
            raise WorkflowExecutionError(f"预期结果无法验收：{text[:200]}")
        try:
            verdict = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise WorkflowExecutionError("预期结果验收返回了无效 JSON") from exc
        normalized = {
            "passed": bool(verdict.get("passed")),
            "reason": str(verdict.get("reason") or ""),
            "expect": expect,
        }
        if not normalized["passed"]:
            raise WorkflowExecutionError(f"输出未达到预期：{normalized['reason'] or expect}")
        return normalized

    @staticmethod
    def _normalize_graph(workflow: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, list[str]]]:
        raw_nodes = workflow.get("nodes") or []
        if not isinstance(raw_nodes, list) or not raw_nodes:
            raise WorkflowExecutionError("工作流至少需要一个节点")
        nodes: list[dict[str, Any]] = []
        ids: set[str] = set()
        valid_types = {"tool", "skill", "mcp", "agent", "model", "step"}
        for index, raw in enumerate(raw_nodes, 1):
            if not isinstance(raw, dict):
                raise WorkflowExecutionError(f"第 {index} 个节点必须是对象")
            node = dict(raw)
            node_id = str(node.get("id") or f"n{index}").strip()
            if not re.fullmatch(r"[A-Za-z0-9_\-]{1,64}", node_id):
                raise WorkflowExecutionError(f"?? ID ??: {node_id}")
            if node_id in ids:
                raise WorkflowExecutionError(f"?? ID ??: {node_id}")
            node_type = str(node.get("type") or "step")
            if node_type not in valid_types:
                raise WorkflowExecutionError(f"节点类型非法: {node_type}")
            node["id"] = node_id
            node["type"] = node_type
            ids.add(node_id)
            nodes.append(node)

        dependencies = {node["id"]: [] for node in nodes}
        edges = workflow.get("edges") or []
        if edges:
            if not isinstance(edges, list):
                raise WorkflowExecutionError("edges 必须是数组")
            for edge in edges:
                if isinstance(edge, dict):
                    source, target = edge.get("from") or edge.get("source"), edge.get("to") or edge.get("target")
                elif isinstance(edge, (list, tuple)) and len(edge) == 2:
                    source, target = edge
                else:
                    raise WorkflowExecutionError(f"工作流连线格式非法: {edge}")
                source, target = str(source), str(target)
                if source not in ids or target not in ids:
                    raise WorkflowExecutionError(f"工作流连线引用未知节点: {source} -> {target}")
                if source == target:
                    raise WorkflowExecutionError(f"节点不能依赖自身: {source}")
                if source not in dependencies[target]:
                    dependencies[target].append(source)
        elif any(node.get("depends_on") for node in nodes):
            for node in nodes:
                deps = node.get("depends_on") or []
                if not isinstance(deps, list) or any(str(dep) not in ids for dep in deps):
                    raise WorkflowExecutionError(f"Node {node['id']} ? depends_on ??")
                dependencies[node["id"]] = [str(dep) for dep in deps]
        else:
            # Backward compatibility: without edges, original workflows execute linearly.
            for index in range(1, len(nodes)):
                dependencies[nodes[index]["id"]].append(nodes[index - 1]["id"])

        # Reuse the production DAG validator to reject cycles before execution.
        validator = ToolDAG()
        for node in nodes:
            validator.add_node(node["id"], lambda: None, depends_on=dependencies[node["id"]])
        validator._validate()
        return nodes, dependencies

    @staticmethod
    def _render_value(value: Any, scope: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {k: WorkflowEngine._render_value(v, scope) for k, v in value.items()}
        if isinstance(value, list):
            return [WorkflowEngine._render_value(item, scope) for item in value]
        if not isinstance(value, str):
            return value

        pattern = re.compile(r"(?:\$\{([^{}]+)\}|\{\{\s*([^{}]+?)\s*\}\})")

        def resolve(path: str) -> Any:
            current: Any = scope
            for part in path.strip().split("."):
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    return ""
            return current

        exact = pattern.fullmatch(value)
        if exact:
            return resolve(exact.group(1) or exact.group(2))

        def replace(match: re.Match[str]) -> str:
            resolved = resolve(match.group(1) or match.group(2))
            return WorkflowEngine._format_value(resolved)

        return pattern.sub(replace, value)

    @staticmethod
    def _context_text(
        input_text: str,
        variables: dict[str, Any],
        outputs: dict[str, Any],
        dependencies: list[str],
    ) -> str:
        dep_outputs = {name: outputs.get(name) for name in dependencies}
        return (
            f"工作流输入：\n{input_text or '（无）'}\n\n"
            f"变量：\n{WorkflowEngine._format_value(variables)}\n\n"
            f"直接上游节点输出：\n{WorkflowEngine._format_value(dep_outputs)}"
        )

    @staticmethod
    def _extract_text(response: Any) -> str:
        if isinstance(response, str):
            return response.strip()
        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError):
            return str(response or "").strip()
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            return "".join(
                str(item.get("text") or "") if isinstance(item, dict) else str(item)
                for item in content
            ).strip()
        return str(content or "").strip()

    @staticmethod
    def _format_value(value: Any) -> str:
        if isinstance(value, str):
            return value
        try:
            return json.dumps(WorkflowEngine._json_safe(value), ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(value)

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(k): WorkflowEngine._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [WorkflowEngine._json_safe(v) for v in value]
        if hasattr(value, "model_dump"):
            return WorkflowEngine._json_safe(value.model_dump())
        if hasattr(value, "__dict__"):
            return WorkflowEngine._json_safe(vars(value))
        return str(value)

    @staticmethod
    def _node_record(record: dict[str, Any], node_id: str) -> dict[str, Any]:
        for node in record["nodes"]:
            if node["id"] == node_id:
                return node
        raise KeyError(node_id)

    async def _persist(self, record: dict[str, Any]) -> None:
        async with self._persist_lock:
            await asyncio.to_thread(self._write_record_sync, self._json_safe(record))

    @classmethod
    def _write_record_sync(cls, record: dict[str, Any]) -> None:
        path = cls._run_path(str(record["id"]))
        temp = path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)
