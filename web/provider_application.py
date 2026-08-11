from __future__ import annotations

import asyncio
import base64
import contextlib
import copy
import inspect
import json
import os
import re
import tempfile
import time
from collections.abc import Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from loguru import logger

from utils.credential_pool import Credential, CredentialPool
from web._provider_keys import _decode_key, _encode_key, _get_cred_dir
from web.custom_providers import build_client


_PROVIDER_ID_PATTERN = re.compile(r"[A-Za-z0-9_-]+", re.ASCII)


def validate_provider_id(provider_id: str) -> str:
    if not isinstance(provider_id, str) or _PROVIDER_ID_PATTERN.fullmatch(provider_id) is None:
        raise ValueError("provider_id must match [A-Za-z0-9_-]+")
    return provider_id


@dataclass(frozen=True)
class CredentialFileSnapshot:
    exists: bool
    content: bytes


@dataclass(frozen=True)
class RuntimeSnapshot:
    client: Any
    credentials: list[Credential]


@dataclass
class _LockEntry:
    lock: asyncio.Lock
    users: int = 0


class _KeyedLockPool:
    def __init__(self) -> None:
        self._entries: dict[str, _LockEntry] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def hold(self, key: str) -> Any:
        async with self._guard:
            entry = self._entries.setdefault(key, _LockEntry(asyncio.Lock()))
            entry.users += 1
        try:
            async with entry.lock:
                yield
        finally:
            async with self._guard:
                entry.users -= 1
                if entry.users == 0 and not entry.lock.locked():
                    self._entries.pop(key, None)

    @property
    def count(self) -> int:
        return len(self._entries)


class ProviderCompensationError(RuntimeError):
    def __init__(self, provider_id: str, failed_stages: tuple[str, ...], cause: Exception) -> None:
        self.provider_id = provider_id
        self.failed_stages = failed_stages
        self.cause = cause
        super().__init__(f"provider 补偿失败: {','.join(failed_stages)}")


class ProviderTransactionJournal:
    def __init__(self, directory: Path) -> None:
        self._directory = directory

    def prepare(
        self,
        provider_id: str,
        record: dict[str, Any] | None,
        credential: CredentialFileSnapshot,
    ) -> None:
        validate_provider_id(provider_id)
        payload = json.dumps(
            {
                "version": 1,
                "provider_id": provider_id,
                "record": record,
                "credential_exists": credential.exists,
                "credential_content": base64.b64encode(credential.content).decode("ascii"),
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        ProviderCredentialStore._replace(self._path(provider_id), payload)

    def clear(self, provider_id: str) -> None:
        validate_provider_id(provider_id)
        self._path(provider_id).unlink(missing_ok=True)

    def prepare_reorder(self, records: dict[str, dict[str, Any]]) -> None:
        for provider_id in records:
            validate_provider_id(provider_id)
        payload = json.dumps(
            {"version": 1, "operation": "reorder", "records": records},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        ProviderCredentialStore._replace(self._reorder_path(), payload)

    def load_reorder(self) -> dict[str, dict[str, Any]]:
        payload = json.loads(self._reorder_path().read_text(encoding="utf-8"))
        records = payload.get("records")
        if payload.get("version") != 1 or payload.get("operation") != "reorder" or not isinstance(records, dict):
            raise ValueError("invalid provider reorder journal")
        for provider_id, record in records.items():
            validate_provider_id(provider_id)
            if not isinstance(record, dict):
                raise ValueError("invalid provider reorder record")
        return copy.deepcopy(records)

    def clear_reorder(self) -> None:
        self._reorder_path().unlink(missing_ok=True)

    def has_reorder(self) -> bool:
        return self._reorder_path().exists()

    def pending_provider_ids(self) -> list[str]:
        if not self._directory.exists():
            return []
        return sorted(path.stem for path in self._directory.glob("*.json"))

    def load(self, provider_id: str) -> tuple[dict[str, Any] | None, CredentialFileSnapshot]:
        validate_provider_id(provider_id)
        payload = json.loads(self._path(provider_id).read_text(encoding="utf-8"))
        if payload.get("version") != 1 or payload.get("provider_id") != provider_id:
            raise ValueError("invalid provider transaction journal")
        return payload.get("record"), CredentialFileSnapshot(
            bool(payload.get("credential_exists")),
            base64.b64decode(payload.get("credential_content", ""), validate=True),
        )

    def _path(self, provider_id: str) -> Path:
        return self._directory / f"{validate_provider_id(provider_id)}.json"

    def _reorder_path(self) -> Path:
        return self._directory / ".reorder.json"


class ProviderRepository:
    def __init__(self, config_service: Any) -> None:
        self._config = config_service

    def get(self, provider_id: str) -> dict[str, Any] | None:
        validate_provider_id(provider_id)
        value = self._config.get(f"models.providers.{provider_id}")
        return copy.deepcopy(value) if isinstance(value, dict) else None

    def set(self, provider_id: str, record: dict[str, Any]) -> None:
        validate_provider_id(provider_id)
        self._config.set(f"models.providers.{provider_id}", copy.deepcopy(record))

    def delete(self, provider_id: str) -> None:
        validate_provider_id(provider_id)
        self._config.delete(f"models.providers.{provider_id}")

    def restore(self, provider_id: str, record: dict[str, Any] | None) -> None:
        validate_provider_id(provider_id)
        if record is None:
            self._config.delete(f"models.providers.{provider_id}")
        else:
            self._config.set(f"models.providers.{provider_id}", copy.deepcopy(record))

    def set_many(self, records: dict[str, dict[str, Any]]) -> None:
        updates = {}
        for provider_id, record in records.items():
            validate_provider_id(provider_id)
            updates[f"models.providers.{provider_id}"] = copy.deepcopy(record)
        self._config.set_many(updates)

    def all(self) -> dict[str, dict[str, Any]]:
        value = self._config.get("models.providers", {}) or {}
        return copy.deepcopy(value) if isinstance(value, dict) else {}


class ProviderCredentialStore:
    def __init__(
        self,
        directory: Path | None = None,
        *,
        encoder: Callable[[str], str] = _encode_key,
        decoder: Callable[[str], str | None] = _decode_key,
    ) -> None:
        self._directory = directory or _get_cred_dir()
        self._encoder = encoder
        self._decoder = decoder

    def _path(self, provider_id: str) -> Path:
        return self._directory / f"provider_{validate_provider_id(provider_id)}.key"

    def snapshot(self, provider_id: str) -> CredentialFileSnapshot:
        path = self._path(provider_id)
        return CredentialFileSnapshot(path.exists(), path.read_bytes() if path.exists() else b"")

    def load(self, provider_id: str) -> str:
        path = self._path(provider_id)
        if not path.exists():
            return ""
        raw = path.read_text(encoding="utf-8").strip()
        if not raw:
            return ""
        decoded = self._decoder(raw)
        if decoded is not None:
            return decoded
        return "" if raw.startswith("enc:") else raw

    def write(self, provider_id: str, api_key: str) -> None:
        payload = (self._encoder(api_key) + "\n").encode("utf-8")
        self._replace(self._path(provider_id), payload)

    def delete(self, provider_id: str) -> None:
        self._path(provider_id).unlink(missing_ok=True)

    def restore(self, provider_id: str, snapshot: CredentialFileSnapshot) -> None:
        path = self._path(provider_id)
        if snapshot.exists:
            self._replace(path, snapshot.content)
        else:
            path.unlink(missing_ok=True)

    @staticmethod
    def _replace(path: Path, payload: bytes) -> None:
        from utils.atomic_write import fsync_directory_best_effort

        path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        temporary_path = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            with contextlib.suppress(OSError):
                os.chmod(temporary_path, 0o600)
            temporary_path.replace(path)
            fsync_directory_best_effort(path.parent)
        finally:
            temporary_path.unlink(missing_ok=True)


class ProviderRuntimeRegistry:
    def __init__(
        self,
        router: Any,
        credential_pool: CredentialPool,
        *,
        client_builder: Callable[[str, str, str], Any] = build_client,
    ) -> None:
        self._router = router
        self._pool = credential_pool
        self._client_builder = client_builder

    def build(self, record: dict[str, Any], api_key: str) -> Any:
        return self._client_builder(record.get("format", "openai"), record.get("base_url", ""), api_key)

    def get(self, provider_id: str) -> Any:
        return getattr(self._router, "_custom_clients", {}).get(provider_id)

    def snapshot(self, provider_id: str) -> RuntimeSnapshot:
        return RuntimeSnapshot(self.get(provider_id), self._pool.snapshot_provider(provider_id))

    def replace(self, provider_id: str, client: Any, api_key: str, base_url: str) -> Any:
        from web.custom_providers import _runtime_registration_coordinator
        with _runtime_registration_coordinator:
            clients = self._clients()
            old_client = clients.get(provider_id)
            clients[provider_id] = client
            try:
                self._pool.replace_provider(provider_id, Credential(api_key, provider_id, base_url))
            except Exception:
                if old_client is None:
                    clients.pop(provider_id, None)
                else:
                    clients[provider_id] = old_client
                raise
        return old_client

    def remove(self, provider_id: str) -> Any:
        from web.custom_providers import _runtime_registration_coordinator
        with _runtime_registration_coordinator:
            old_client = self._clients().pop(provider_id, None)
            try:
                self._pool.remove_provider(provider_id)
            except Exception:
                if old_client is not None:
                    self._clients()[provider_id] = old_client
                raise
        return old_client

    def restore(self, provider_id: str, snapshot: RuntimeSnapshot) -> None:
        from web.custom_providers import _runtime_registration_coordinator
        with _runtime_registration_coordinator:
            clients = self._clients()
            if snapshot.client is None:
                clients.pop(provider_id, None)
            else:
                clients[provider_id] = snapshot.client
            self._pool.restore_provider(provider_id, snapshot.credentials)

    async def close(self, client: Any) -> None:
        if client is None:
            return
        closer = getattr(client, "aclose", None) or getattr(client, "close", None)
        if closer is None:
            return
        result = closer()
        if inspect.isawaitable(result):
            await result

    def _clients(self) -> dict[str, Any]:
        if not hasattr(self._router, "_custom_clients"):
            self._router._custom_clients = {}
        return self._router._custom_clients


class ProviderApplicationService:
    def __init__(
        self,
        repository: ProviderRepository,
        credential_store: ProviderCredentialStore,
        runtime_registry: ProviderRuntimeRegistry,
        *,
        transaction_journal: ProviderTransactionJournal | None = None,
    ) -> None:
        self._repository = repository
        self._credentials = credential_store
        self._runtime = runtime_registry
        self._locks = _KeyedLockPool()
        self._journal = transaction_journal or ProviderTransactionJournal(
            credential_store._directory / "provider-transactions"
        )
        self.last_recovery_report: list[dict[str, str]] = []

    @property
    def transaction_journal(self) -> ProviderTransactionJournal:
        return self._journal

    def recover_pending_transactions(self) -> list[str]:
        from web.custom_providers import _runtime_registration_coordinator

        with _runtime_registration_coordinator:
            recovered = []
            report = []
            if self._journal.has_reorder():
                try:
                    self._repository.set_many(self._journal.load_reorder())
                    self._journal.clear_reorder()
                    recovered.append("reorder")
                except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
                    path = self._journal._reorder_path()
                    quarantine = path.with_name(f"{path.name}.corrupt-{time.time_ns()}")
                    try:
                        os.replace(path, quarantine)
                        from utils.atomic_write import fsync_directory_best_effort
                        fsync_directory_best_effort(path.parent)
                    except OSError:
                        logger.error(
                            "provider_application.journal_quarantine_failed journal={} error_type={}",
                            path.name,
                            type(error).__name__,
                        )
                    else:
                        report.append({
                            "journal": path.name,
                            "status": "quarantined",
                            "error_type": type(error).__name__,
                        })
            for provider_id in self._journal.pending_provider_ids():
                if provider_id == ".reorder":
                    continue
                try:
                    validate_provider_id(provider_id)
                    record, credential = self._journal.load(provider_id)
                except (OSError, UnicodeError, ValueError, json.JSONDecodeError) as error:
                    path = self._journal._directory / f"{provider_id}.json"
                    quarantine = path.with_name(f"{path.name}.corrupt-{time.time_ns()}")
                    try:
                        os.replace(path, quarantine)
                        from utils.atomic_write import fsync_directory_best_effort
                        fsync_directory_best_effort(path.parent)
                    except OSError:
                        logger.error(
                            "provider_application.journal_quarantine_failed journal={} error_type={}",
                            path.name,
                            type(error).__name__,
                        )
                        continue
                    report.append({
                        "journal": path.name,
                        "status": "quarantined",
                        "error_type": type(error).__name__,
                    })
                    logger.warning(
                        "provider_application.journal_quarantined journal={} error_type={}",
                        path.name,
                        type(error).__name__,
                    )
                    continue
                self._repository.restore(provider_id, record)
                self._credentials.restore(provider_id, credential)
                self._journal.clear(provider_id)
                recovered.append(provider_id)
            self.last_recovery_report = report
            return recovered

    async def create(self, provider_id: str, record: dict[str, Any], api_key: str) -> dict[str, Any]:
        async with self._locks.hold(provider_id):
            if self._repository.get(provider_id) is not None:
                raise ValueError(f"provider {provider_id} 已存在")
            return await self._mutate(provider_id, record, api_key, create=True)

    async def validate_candidate(
        self, provider_id: str, record: dict[str, Any], api_key: str
    ) -> dict[str, Any]:
        async with self._locks.hold(provider_id):
            candidate = self._runtime.build(record, api_key) if record.get("enabled", True) else None
            await self._shield_close_committed_client(provider_id, candidate)
            return copy.deepcopy(record)

    async def update(
        self,
        provider_id: str,
        record: dict[str, Any],
        *,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        async with self._locks.hold(provider_id):
            current = self._repository.get(provider_id)
            if current is None:
                raise KeyError(provider_id)
            merged = dict(current)
            merged.update(record)
            final_key = api_key if api_key is not None else self._credentials.load(provider_id)
            return await self._mutate(provider_id, merged, final_key, write_key=api_key is not None)

    async def set_key(self, provider_id: str, api_key: str) -> dict[str, Any]:
        async with self._locks.hold(provider_id):
            record = self._repository.get(provider_id)
            if record is None:
                raise KeyError(provider_id)
            return await self._mutate(provider_id, record, api_key, write_key=True)

    async def delete(self, provider_id: str) -> None:
        async with self._locks.hold(provider_id):
            from web.custom_providers import _runtime_registration_coordinator

            with _runtime_registration_coordinator:
                old_record = self._repository.get(provider_id)
                if old_record is None:
                    raise KeyError(provider_id)
                credential_snapshot = self._credentials.snapshot(provider_id)
                runtime_snapshot = self._runtime.snapshot(provider_id)
                self._journal.prepare(provider_id, old_record, credential_snapshot)
                completed: list[tuple[str, Callable[[], None]]] = []
                try:
                    await self._remove_runtime(provider_id)
                    completed.append(("runtime", lambda: self._runtime.restore(provider_id, runtime_snapshot)))
                    await self._delete_repository(provider_id)
                    completed.append(("repository", lambda: self._repository.restore(provider_id, old_record)))
                    await self._delete_credentials(provider_id)
                    completed.append(
                        ("credentials", lambda: self._credentials.restore(provider_id, credential_snapshot))
                    )
                except BaseException as error:
                    failures = await self._compensate(provider_id, completed)
                    if failures:
                        if not isinstance(error, Exception):
                            logger.error(
                                "provider_application.cancelled_compensation_failed provider={} stages={}",
                                provider_id,
                                ",".join(failures),
                            )
                        else:
                            raise ProviderCompensationError(provider_id, tuple(failures), error) from error
                    raise
                self._journal.clear(provider_id)
            await self._shield_close_committed_client(provider_id, runtime_snapshot.client)

    async def upsert_from_setup(
        self, provider_id: str, record: dict[str, Any], api_key: str
    ) -> dict[str, Any]:
        async with self._locks.hold(provider_id):
            current = self._repository.get(provider_id)
            return await self._mutate(
                provider_id,
                current or record,
                api_key,
                create=current is None,
                write_key=True,
            )

    async def reorder(self, provider_ids: list[str]) -> None:
        requested_ids = list(dict.fromkeys(provider_ids))
        async with contextlib.AsyncExitStack() as stack:
            for provider_id in sorted(requested_ids):
                await stack.enter_async_context(self._locks.hold(provider_id))
            records = self._repository.all()
            ordered_ids = [provider_id for provider_id in requested_ids if provider_id in records]
            old_records = {provider_id: records[provider_id] for provider_id in ordered_ids}
            new_records = copy.deepcopy(old_records)
            for index, provider_id in enumerate(ordered_ids):
                new_records[provider_id]["order"] = index
            if not new_records:
                return
            self._journal.prepare_reorder(old_records)
            try:
                self._repository.set_many(new_records)
            except BaseException as error:
                failures = await self._compensate(
                    "reorder",
                    [("repository", lambda: self._repository.set_many(old_records))],
                )
                if failures:
                    if not isinstance(error, Exception):
                        logger.error(
                            "provider_application.cancelled_compensation_failed provider=reorder stages={}",
                            ",".join(failures),
                        )
                    else:
                        raise ProviderCompensationError("reorder", tuple(failures), error) from error
                self._journal.clear_reorder()
                raise
            self._journal.clear_reorder()

    async def _mutate(
        self,
        provider_id: str,
        record: dict[str, Any],
        api_key: str,
        *,
        create: bool = False,
        write_key: bool = True,
    ) -> dict[str, Any]:
        from web.custom_providers import _runtime_registration_coordinator

        with _runtime_registration_coordinator:
            if record.get("enabled", True) and not api_key:
                raise ValueError("api_key 不能为空")
            old_record = self._repository.get(provider_id)
            credential_snapshot = self._credentials.snapshot(provider_id)
            runtime_snapshot = self._runtime.snapshot(provider_id)
            candidate = self._runtime.build(record, api_key) if record.get("enabled", True) else None
            self._journal.prepare(provider_id, old_record, credential_snapshot)
            completed: list[tuple[str, Callable[[], None]]] = []
            try:
                await self._set_repository(provider_id, record)
                completed.append(("repository", lambda: self._repository.restore(provider_id, old_record)))
                if write_key or create:
                    await self._write_credentials(provider_id, api_key)
                    completed.append(
                        ("credentials", lambda: self._credentials.restore(provider_id, credential_snapshot))
                    )
                if candidate is None:
                    await self._remove_runtime(provider_id)
                else:
                    await self._replace_runtime(provider_id, candidate, api_key, record.get("base_url", ""))
                completed.append(("runtime", lambda: self._runtime.restore(provider_id, runtime_snapshot)))
            except BaseException as error:
                failures = await self._compensate(provider_id, completed)
                if candidate is not runtime_snapshot.client:
                    if not await self._shield_close_failed_candidate(provider_id, candidate):
                        failures.append("candidate_close")
                if failures:
                    if not isinstance(error, Exception):
                        logger.error(
                            "provider_application.cancelled_compensation_failed provider={} stages={}",
                            provider_id,
                            ",".join(failures),
                        )
                    else:
                        raise ProviderCompensationError(provider_id, tuple(failures), error) from error
                raise
            self._journal.clear(provider_id)
        if runtime_snapshot.client is not candidate:
            await self._shield_close_committed_client(provider_id, runtime_snapshot.client)
        return copy.deepcopy(record)

    async def _set_repository(self, provider_id: str, record: dict[str, Any]) -> None:
        self._repository.set(provider_id, record)

    async def _write_credentials(self, provider_id: str, api_key: str) -> None:
        self._credentials.write(provider_id, api_key)

    async def _delete_credentials(self, provider_id: str) -> None:
        self._credentials.delete(provider_id)

    async def _delete_repository(self, provider_id: str) -> None:
        self._repository.delete(provider_id)

    async def _replace_runtime(self, provider_id: str, client: Any, api_key: str, base_url: str) -> None:
        self._runtime.replace(provider_id, client, api_key, base_url)

    async def _remove_runtime(self, provider_id: str) -> None:
        self._runtime.remove(provider_id)

    async def _compensate(
        self, provider_id: str, completed: list[tuple[str, Callable[[], None]]]
    ) -> list[str]:
        failures: list[str] = []
        for stage, operation in reversed(completed):
            task = asyncio.create_task(self._run_compensation(stage, operation))
            try:
                await asyncio.shield(task)
            except BaseException as rollback_error:
                if isinstance(rollback_error, asyncio.CancelledError) and not task.done():
                    await self._await_task_despite_cancellation(task)
                if isinstance(rollback_error, asyncio.CancelledError) and task.done() and not task.cancelled():
                    task_error = task.exception()
                    if task_error is None:
                        continue
                    rollback_error = task_error
                failures.append(stage)
                logger.error(
                    "provider_application.rollback_failed provider={} stage={} error_type={}",
                    provider_id,
                    stage,
                    type(rollback_error).__name__,
                )
        return failures

    async def _run_compensation(self, stage: str, operation: Callable[[], None]) -> None:
        operation()

    async def _await_task_despite_cancellation(self, task: asyncio.Task[Any]) -> None:
        current = asyncio.current_task()
        uncancel = getattr(current, "uncancel", None)
        if uncancel is not None:
            uncancel()
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                if uncancel is not None:
                    uncancel()
                continue

    async def _shield_close_failed_candidate(self, provider_id: str, client: Any) -> bool:
        task = asyncio.create_task(self._close_failed_candidate(provider_id, client))
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            await self._await_task_despite_cancellation(task)
            return task.result()

    async def _close_committed_client(self, provider_id: str, client: Any) -> None:
        try:
            await self._runtime.close(client)
        except Exception as error:
            logger.warning(
                "provider_application.committed_client_close_failed provider={} error_type={}",
                provider_id,
                type(error).__name__,
            )

    async def _shield_close_committed_client(self, provider_id: str, client: Any) -> None:
        task = asyncio.create_task(self._close_committed_client(provider_id, client))
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            await self._await_task_despite_cancellation(task)
            raise

    async def _close_failed_candidate(self, provider_id: str, client: Any) -> bool:
        try:
            await self._runtime.close(client)
            return True
        except Exception as error:
            logger.warning(
                "provider_application.candidate_close_failed provider={} error_type={}",
                provider_id,
                type(error).__name__,
            )
            return False

    @property
    def lock_count(self) -> int:
        return self._locks.count
