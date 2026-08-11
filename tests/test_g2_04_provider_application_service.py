from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from utils.credential_pool import Credential, CredentialPool
from web.config_service import ConfigService
from web.provider_application import (
    CredentialFileSnapshot,
    ProviderApplicationService,
    ProviderCompensationError,
    ProviderCredentialStore,
    ProviderRepository,
    ProviderRuntimeRegistry,
    ProviderTransactionJournal,
)


class FakeClient:
    def __init__(self, name: str) -> None:
        self.name = name
        self.closed = False
        self.close_error: Exception | None = None

    async def aclose(self) -> None:
        self.closed = True
        if self.close_error is not None:
            raise self.close_error


@dataclass
class Harness:
    service: ProviderApplicationService
    repository: ProviderRepository
    credentials: ProviderCredentialStore
    runtime: ProviderRuntimeRegistry
    router: Any
    pool: CredentialPool
    clients: list[FakeClient]


@pytest.fixture
def harness(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Harness:
    monkeypatch.setattr(CredentialPool, "_load_from_env", lambda self: None)
    config = ConfigService(path=tmp_path / "webui_overrides.json")
    repository = ProviderRepository(config)
    credentials = ProviderCredentialStore(
        tmp_path / "credentials",
        encoder=lambda key: f"encoded:{key}",
        decoder=lambda value: value.removeprefix("encoded:") if value.startswith("encoded:") else None,
    )
    router = SimpleNamespace(_custom_clients={})
    pool = CredentialPool()
    clients: list[FakeClient] = []

    def build_client(fmt: str, base_url: str, api_key: str) -> FakeClient:
        client = FakeClient(f"{fmt}:{base_url}:{api_key}")
        clients.append(client)
        return client

    runtime = ProviderRuntimeRegistry(router, pool, client_builder=build_client)
    service = ProviderApplicationService(
        repository,
        credentials,
        runtime,
        transaction_journal=ProviderTransactionJournal(tmp_path / "provider-journal"),
    )
    return Harness(service, repository, credentials, runtime, router, pool, clients)


def record(*, enabled: bool = True, base_url: str = "https://api.example.com/v1") -> dict[str, Any]:
    return {
        "label": "Example",
        "format": "openai",
        "base_url": base_url,
        "default_model": "example-chat",
        "enabled": enabled,
    }


def state(harness: Harness, provider_id: str = "example") -> tuple[Any, str, Any, list[Credential]]:
    return (
        harness.repository.get(provider_id),
        harness.credentials.load(provider_id),
        harness.runtime.get(provider_id),
        harness.pool.snapshot_provider(provider_id),
    )


@pytest.mark.parametrize(
    "provider_id",
    ["供应商", "éxample", "example.test", "example/test", "example test", "ＡPI"],
)
def test_provider_id_is_strict_ascii_across_persistence_boundaries(
    harness: Harness, provider_id: str
) -> None:
    with pytest.raises(ValueError, match="provider_id"):
        harness.repository.get(provider_id)
    with pytest.raises(ValueError, match="provider_id"):
        harness.credentials.snapshot(provider_id)
    with pytest.raises(ValueError, match="provider_id"):
        harness.service.transaction_journal.prepare(
            provider_id,
            None,
            CredentialFileSnapshot(False, b""),
        )


def test_provider_storage_rejects_ids_that_previously_collided(harness: Harness) -> None:
    harness.credentials.write("example", "secret-one")

    with pytest.raises(ValueError, match="provider_id"):
        harness.credentials.write("exam.ple", "secret-two")

    assert harness.credentials.load("example") == "secret-one"


def test_startup_recovery_quarantines_non_ascii_or_path_mapped_journals(
    harness: Harness, tmp_path: Path
) -> None:
    journal_dir = tmp_path / "provider-journal"
    journal_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "provider_id": "example.test",
        "record": record(),
        "credential_exists": False,
        "credential_content": "",
    }
    (journal_dir / "example.test.json").write_text(json.dumps(payload), encoding="utf-8")

    recovered = harness.service.recover_pending_transactions()

    assert recovered == []
    assert harness.repository.all() == {}
    assert list(journal_dir.glob("example.test.json.corrupt-*"))


@pytest.mark.asyncio
async def test_create_publishes_configuration_key_client_and_pool(harness: Harness) -> None:
    result = await harness.service.create("example", record(), "secret-one")

    config, key, client, credentials = state(harness)
    assert result == record()
    assert config == record()
    assert key == "secret-one"
    assert client is harness.clients[0]
    assert [(item.api_key, item.provider, item.base_url) for item in credentials] == [
        ("secret-one", "example", "https://api.example.com/v1")
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["repository.set", "credentials.write", "runtime.replace"])
async def test_create_failure_restores_empty_four_state(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    target, method = failure.split(".")
    component = getattr(harness, target)
    original = getattr(component, method)

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise OSError(failure)

    monkeypatch.setattr(component, method, fail)
    with pytest.raises(OSError, match=failure):
        await harness.service.create("example", record(), "secret-one")

    assert state(harness) == (None, "", None, [])
    assert harness.clients[0].closed is True
    monkeypatch.setattr(component, method, original)


@pytest.mark.asyncio
async def test_client_build_failure_keeps_create_empty(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(harness.runtime, "build", lambda *args: (_ for _ in ()).throw(OSError("build")))

    with pytest.raises(OSError, match="build"):
        await harness.service.create("example", record(), "secret-one")

    assert state(harness) == (None, "", None, [])


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["repository.set", "credentials.write", "runtime.replace"])
async def test_update_failure_restores_previous_four_state(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    await harness.service.create("example", record(), "secret-one")
    before = state(harness)
    old_client = before[2]
    target, method = failure.split(".")
    component = getattr(harness, target)

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise OSError(failure)

    monkeypatch.setattr(component, method, fail)
    with pytest.raises(OSError, match=failure):
        await harness.service.update(
            "example",
            record(base_url="https://new.example.com/v1"),
            api_key="secret-two",
        )

    after = state(harness)
    assert after[0] == before[0]
    assert after[1] == before[1]
    assert after[2] is old_client
    assert after[3] == before[3]
    assert old_client.closed is False
    assert harness.clients[-1].closed is True


@pytest.mark.asyncio
async def test_update_commits_new_state_then_closes_old_client(harness: Harness) -> None:
    await harness.service.create("example", record(), "secret-one")
    old_client = harness.runtime.get("example")
    updated = record(base_url="https://new.example.com/v1")

    result = await harness.service.update("example", updated, api_key="secret-two")

    assert result == updated
    assert state(harness)[0:2] == (updated, "secret-two")
    assert harness.runtime.get("example") is harness.clients[-1]
    assert old_client.closed is True


@pytest.mark.asyncio
async def test_update_old_client_close_failure_keeps_committed_state(harness: Harness) -> None:
    await harness.service.create("example", record(), "secret-one")
    old_client = harness.runtime.get("example")
    old_client.close_error = OSError("close failed")
    updated = record(base_url="https://new.example.com/v1")

    result = await harness.service.update("example", updated, api_key="secret-two")

    assert result == updated
    assert state(harness)[0:2] == (updated, "secret-two")
    assert harness.runtime.get("example") is harness.clients[-1]
    assert old_client.closed is True


@pytest.mark.asyncio
async def test_committed_update_shields_old_client_close_from_cancellation(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    await harness.service.create("example", record(), "secret-one")
    old_client = harness.runtime.get("example")
    close_entered = asyncio.Event()
    close_release = asyncio.Event()

    async def blocked_close(client: Any) -> None:
        close_entered.set()
        await close_release.wait()
        client.closed = True

    monkeypatch.setattr(harness.runtime, "close", blocked_close)
    operation = asyncio.create_task(
        harness.service.update("example", record(base_url="https://new.example.com/v1"))
    )
    await close_entered.wait()
    operation.cancel()
    await asyncio.sleep(0)

    assert operation.done() is False
    assert state(harness)[0] == record(base_url="https://new.example.com/v1")
    close_release.set()
    with pytest.raises(asyncio.CancelledError):
        await operation
    assert old_client.closed is True


def test_startup_recovery_restores_pre_transaction_persistent_state(harness: Harness) -> None:
    harness.repository.set("example", record())
    harness.credentials.write("example", "secret-one")
    journal = harness.service.transaction_journal
    journal.prepare(
        "example",
        harness.repository.get("example"),
        harness.credentials.snapshot("example"),
    )
    harness.repository.set("example", record(base_url="https://partial.example.com/v1"))
    harness.credentials.write("example", "secret-two")

    recovered = harness.service.recover_pending_transactions()

    assert recovered == ["example"]
    assert harness.repository.get("example") == record()
    assert harness.credentials.load("example") == "secret-one"
    assert journal.pending_provider_ids() == []


def test_startup_recovery_removes_partially_created_provider(harness: Harness) -> None:
    journal = harness.service.transaction_journal
    journal.prepare(
        "example",
        None,
        harness.credentials.snapshot("example"),
    )
    harness.repository.set("example", record())
    harness.credentials.write("example", "secret-one")

    harness.service.recover_pending_transactions()

    assert state(harness)[0:2] == (None, "")
    assert journal.pending_provider_ids() == []


@pytest.mark.asyncio
async def test_set_key_replaces_client_pool_and_closes_old_client(harness: Harness) -> None:
    await harness.service.create("example", record(), "secret-one")
    old_client = harness.runtime.get("example")

    await harness.service.set_key("example", "secret-two")

    assert harness.credentials.load("example") == "secret-two"
    assert harness.pool.snapshot_provider("example")[0].api_key == "secret-two"
    assert harness.runtime.get("example") is not old_client
    assert old_client.closed is True


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["credentials.write", "runtime.replace"])
async def test_set_key_failure_restores_previous_four_state(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    await harness.service.create("example", record(), "secret-one")
    before = state(harness)
    target, method = failure.split(".")
    component = getattr(harness, target)
    monkeypatch.setattr(
        component,
        method,
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError(failure)),
    )

    with pytest.raises(OSError, match=failure):
        await harness.service.set_key("example", "secret-two")

    after = state(harness)
    assert after[0] == before[0]
    assert after[1] == before[1]
    assert after[2] is before[2]
    assert after[3] == before[3]
    assert before[2].closed is False
    assert harness.clients[-1].closed is True


@pytest.mark.asyncio
async def test_disable_removes_runtime_state_but_preserves_configuration_and_key(harness: Harness) -> None:
    await harness.service.create("example", record(), "secret-one")
    old_client = harness.runtime.get("example")

    await harness.service.update("example", record(enabled=False))

    assert state(harness) == (record(enabled=False), "secret-one", None, [])
    assert old_client.closed is True


@pytest.mark.asyncio
async def test_enable_rebuilds_runtime_state_from_preserved_key(harness: Harness) -> None:
    await harness.service.create("example", record(enabled=False), "secret-one")
    assert state(harness)[2:] == (None, [])

    await harness.service.update("example", record(enabled=True))

    assert harness.runtime.get("example") is harness.clients[-1]
    assert harness.pool.snapshot_provider("example")[0].api_key == "secret-one"


@pytest.mark.asyncio
async def test_disable_runtime_failure_restores_previous_four_state(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    await harness.service.create("example", record(), "secret-one")
    before = state(harness)
    monkeypatch.setattr(
        harness.runtime,
        "remove",
        lambda *args: (_ for _ in ()).throw(OSError("runtime.remove")),
    )

    with pytest.raises(OSError, match="runtime.remove"):
        await harness.service.update("example", record(enabled=False))

    after = state(harness)
    assert after[0] == before[0]
    assert after[1] == before[1]
    assert after[2] is before[2]
    assert after[3] == before[3]
    assert before[2].closed is False


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["runtime.remove", "repository.delete", "credentials.delete"])
async def test_delete_failure_restores_previous_four_state(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    await harness.service.create("example", record(), "secret-one")
    before = state(harness)
    target, method = failure.split(".")
    component = getattr(harness, target)

    def fail(*args: Any, **kwargs: Any) -> Any:
        raise OSError(failure)

    monkeypatch.setattr(component, method, fail)
    with pytest.raises(OSError, match=failure):
        await harness.service.delete("example")

    after = state(harness)
    assert after[0] == before[0]
    assert after[1] == before[1]
    assert after[2] is before[2]
    assert after[3] == before[3]
    assert before[2].closed is False


@pytest.mark.asyncio
async def test_delete_removes_four_state_and_closes_old_client(harness: Harness) -> None:
    await harness.service.create("example", record(), "secret-one")
    old_client = harness.runtime.get("example")

    await harness.service.delete("example")

    assert state(harness) == (None, "", None, [])
    assert old_client.closed is True


@pytest.mark.asyncio
async def test_compensation_failure_raises_safe_observable_error(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from web.provider_application import ProviderCompensationError

    await harness.service.create("example", record(), "secret-one")
    monkeypatch.setattr(
        harness.runtime,
        "replace",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("publish secret-two failed")),
    )
    monkeypatch.setattr(
        harness.credentials,
        "restore",
        lambda *args, **kwargs: (_ for _ in ()).throw(OSError("restore secret-one failed")),
    )

    with pytest.raises(ProviderCompensationError) as error:
        await harness.service.update("example", record(), api_key="secret-two")

    assert error.value.provider_id == "example"
    assert error.value.failed_stages == ("credentials",)
    assert "secret-one" not in str(error.value)
    assert "secret-two" not in str(error.value)


@pytest.mark.asyncio
async def test_success_persists_files_without_temporary_artifacts(harness: Harness, tmp_path: Path) -> None:
    await harness.service.create("example", record(), "secret-one")

    config_path = tmp_path / "webui_overrides.json"
    credential_path = tmp_path / "credentials" / "provider_example.key"
    assert '"example"' in config_path.read_text(encoding="utf-8")
    assert credential_path.read_text(encoding="utf-8").strip() == "encoded:secret-one"
    assert list(tmp_path.rglob(".provider_example.key.*")) == []
    assert list(tmp_path.rglob(".atomic_*")) == []


@pytest.mark.asyncio
async def test_persist_failure_cleans_temporary_files_and_router_side_effects(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    await harness.service.create("example", record(), "secret-one")
    before = state(harness)
    original_replace = Path.replace
    replacements = 0

    def fail_config_replace(path: Path, target: Path) -> Path:
        nonlocal replacements
        if Path(target).name == "provider_example.key":
            replacements += 1
        if Path(target).name == "provider_example.key" and replacements == 1:
            raise OSError("replace failed")
        return original_replace(path, target)

    monkeypatch.setattr(Path, "replace", fail_config_replace)

    with pytest.raises(OSError, match="replace failed"):
        await harness.service.update(
            "example",
            record(base_url="https://new.example.com/v1"),
            api_key="secret-two",
        )

    after = state(harness)
    assert after[0] == before[0]
    assert after[1] == before[1]
    assert after[2] is before[2]
    assert after[3] == before[3]
    assert list(tmp_path.rglob(".provider_example.key.*")) == []
    assert list(tmp_path.rglob(".atomic_*")) == []


@pytest.mark.asyncio
async def test_same_provider_mutations_are_serialized(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    await harness.service.create("example", record(), "secret-one")
    active = 0
    maximum = 0
    original = harness.repository.set

    async def gate(provider_id: str, value: dict[str, Any]) -> None:
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        await asyncio.sleep(0.01)
        original(provider_id, value)
        active -= 1

    monkeypatch.setattr(harness.service, "_set_repository", gate)
    await asyncio.gather(
        harness.service.update("example", record(base_url="https://one.example.com/v1")),
        harness.service.update("example", record(base_url="https://two.example.com/v1")),
    )

    assert maximum == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["repository", "credentials", "runtime"])
async def test_cancelled_create_shields_completed_stage_compensation_and_reraises(
    harness: Harness, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    transaction_task = asyncio.current_task()
    compensated: list[tuple[str, asyncio.Task[Any] | None]] = []
    original_restore = {
        "repository": harness.repository.restore,
        "credentials": harness.credentials.restore,
        "runtime": harness.runtime.restore,
    }

    async def compensate(name: str, operation: Any) -> None:
        await asyncio.sleep(0)
        compensated.append((name, asyncio.current_task()))
        operation()

    monkeypatch.setattr(harness.service, "_run_compensation", compensate)
    target = {
        "repository": "_set_repository",
        "credentials": "_write_credentials",
        "runtime": "_replace_runtime",
    }[stage]

    async def cancel(*args: Any, **kwargs: Any) -> None:
        raise asyncio.CancelledError()

    monkeypatch.setattr(harness.service, target, cancel)

    with pytest.raises(asyncio.CancelledError):
        await harness.service.create("example", record(), "secret-one")

    assert state(harness) == (None, "", None, [])
    expected = {
        "repository": [],
        "credentials": ["repository"],
        "runtime": ["credentials", "repository"],
    }[stage]
    assert [name for name, _ in compensated] == expected
    assert all(task is not transaction_task for _, task in compensated)
    assert all(name in original_restore for name in expected)


@pytest.mark.asyncio
async def test_repeated_cancellation_cannot_interrupt_candidate_cleanup(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    close_entered = asyncio.Event()
    close_release = asyncio.Event()

    async def close_candidate(client: Any) -> None:
        close_entered.set()
        await close_release.wait()
        client.closed = True

    async def cancel_after_repository(*args: Any, **kwargs: Any) -> None:
        raise asyncio.CancelledError()

    monkeypatch.setattr(harness.runtime, "close", close_candidate)
    monkeypatch.setattr(harness.service, "_write_credentials", cancel_after_repository)

    transaction = asyncio.create_task(harness.service.create("example", record(), "secret-one"))
    await close_entered.wait()
    transaction.cancel()
    await asyncio.sleep(0)
    transaction.cancel()
    await asyncio.sleep(0)

    assert transaction.done() is False
    close_release.set()
    with pytest.raises(asyncio.CancelledError):
        await transaction
    assert harness.clients[0].closed is True
    assert state(harness) == (None, "", None, [])


@pytest.mark.asyncio
async def test_compensation_runs_reverse_completed_steps_and_isolates_runtime_failure(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    await harness.service.create("example", record(), "secret-one")
    before = state(harness)
    events: list[str] = []

    monkeypatch.setattr(
        harness.repository,
        "delete",
        lambda *args: (_ for _ in ()).throw(OSError("delete")),
    )

    async def compensate(name: str, operation: Any) -> None:
        events.append(name)
        if name == "runtime":
            raise OSError("runtime restore")
        operation()

    monkeypatch.setattr(harness.service, "_run_compensation", compensate)

    with pytest.raises(ProviderCompensationError) as error:
        await harness.service.delete("example")

    assert events == ["runtime"]
    assert error.value.failed_stages == ("runtime",)
    assert state(harness)[0:2] == before[0:2]


@pytest.mark.asyncio
async def test_base_exception_is_reraised_after_all_compensations_despite_runtime_restore_failure(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    class AbortTransaction(BaseException):
        pass

    original = AbortTransaction("abort")
    events: list[str] = []

    async def compensate(name: str, operation: Any) -> None:
        events.append(name)
        if name == "runtime":
            raise OSError("runtime restore")
        operation()

    async def abort_after_runtime(*args: Any, **kwargs: Any) -> None:
        raise original

    monkeypatch.setattr(harness.service, "_run_compensation", compensate)
    monkeypatch.setattr(harness.service, "_replace_runtime", abort_after_runtime)

    with pytest.raises(AbortTransaction) as error:
        await harness.service.create("example", record(), "secret-one")

    assert error.value is original
    assert events == ["credentials", "repository"]
    assert state(harness) == (None, "", None, [])


@pytest.mark.asyncio
async def test_compensation_continues_in_reverse_order_after_runtime_restore_failure(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    events: list[str] = []

    async def compensate(name: str, operation: Any) -> None:
        events.append(name)
        operation()

    monkeypatch.setattr(harness.service, "_run_compensation", compensate)

    failures = await harness.service._compensate(
        "example",
        [
            ("repository", lambda: events.append("repository.restored")),
            ("credentials", lambda: events.append("credentials.restored")),
            ("runtime", lambda: (_ for _ in ()).throw(OSError("runtime restore"))),
        ],
    )

    assert failures == ["runtime"]
    assert events == [
        "runtime",
        "credentials",
        "credentials.restored",
        "repository",
        "repository.restored",
    ]


@pytest.mark.asyncio
async def test_keyed_locks_are_reclaimed_after_high_cardinality_mutations(harness: Harness) -> None:
    for index in range(300):
        provider_id = f"provider-{index}"
        await harness.service.create(provider_id, record(), f"secret-{index}")

    assert harness.service.lock_count == 0


@pytest.mark.asyncio
async def test_reorder_and_setup_upsert_share_provider_mutation_lock(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    await harness.service.create("example", record(), "secret-one")
    entered = asyncio.Event()
    release = asyncio.Event()
    original_set = harness.repository.set

    async def gated_set(provider_id: str, value: dict[str, Any]) -> None:
        entered.set()
        await release.wait()
        original_set(provider_id, value)

    monkeypatch.setattr(harness.service, "_set_repository", gated_set)
    setup_task = asyncio.create_task(
        harness.service.upsert_from_setup("example", record(), "secret-two")
    )
    await entered.wait()
    reorder_task = asyncio.create_task(harness.service.reorder(["example"]))
    await asyncio.sleep(0)

    assert reorder_task.done() is False
    release.set()
    await asyncio.gather(setup_task, reorder_task)
    assert harness.repository.get("example")["order"] == 0


@pytest.mark.asyncio
async def test_reorder_reads_provider_snapshot_only_inside_service_mutation_lock(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    await harness.service.create("example", record(), "secret-one")
    setup_entered = asyncio.Event()
    setup_release = asyncio.Event()
    snapshot_read = asyncio.Event()
    original_set = harness.repository.set
    original_all = harness.repository.all

    async def gated_set(provider_id: str, value: dict[str, Any]) -> None:
        setup_entered.set()
        await setup_release.wait()
        original_set(provider_id, value)

    def tracked_all() -> dict[str, dict[str, Any]]:
        snapshot_read.set()
        return original_all()

    monkeypatch.setattr(harness.service, "_set_repository", gated_set)
    monkeypatch.setattr(harness.repository, "all", tracked_all)
    setup_task = asyncio.create_task(
        harness.service.upsert_from_setup("example", record(), "secret-two")
    )
    await setup_entered.wait()
    reorder_task = asyncio.create_task(harness.service.reorder(["example"]))
    await asyncio.sleep(0)

    assert snapshot_read.is_set() is False
    setup_release.set()
    await asyncio.gather(setup_task, reorder_task)
    assert snapshot_read.is_set() is True


@pytest.mark.asyncio
async def test_reorder_compensation_failure_is_reported_after_reverse_rollback(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    await harness.service.create("one", record(), "secret-one")
    await harness.service.create("two", record(), "secret-two")
    events: list[str] = []

    def fail_batch_write(records: dict[str, dict[str, Any]]) -> None:
        raise OSError("batch write")

    async def fail_compensation(name: str, operation: Any) -> None:
        events.append(name)
        raise OSError("restore failed")

    monkeypatch.setattr(harness.repository, "set_many", fail_batch_write)
    monkeypatch.setattr(harness.service, "_run_compensation", fail_compensation)

    with pytest.raises(ProviderCompensationError) as error:
        await harness.service.reorder(["one", "two"])

    assert events == ["repository"]
    assert error.value.provider_id == "reorder"
    assert error.value.failed_stages == ("repository",)
    assert isinstance(error.value.cause, OSError)


@pytest.mark.asyncio
async def test_reorder_commits_all_records_with_one_set_many_call(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    await harness.service.create("one", record(), "secret-one")
    await harness.service.create("two", record(), "secret-two")
    calls: list[dict[str, Any]] = []
    original = harness.repository._config.set_many

    def tracked(updates: dict[str, Any]) -> None:
        calls.append(updates)
        original(updates)

    monkeypatch.setattr(harness.repository._config, "set_many", tracked)

    await harness.service.reorder(["two", "one"])

    assert len(calls) == 1
    assert set(calls[0]) == {"models.providers.two", "models.providers.one"}
    assert harness.repository.get("two")["order"] == 0
    assert harness.repository.get("one")["order"] == 1


def test_reorder_recovers_entire_old_batch_after_real_process_exit(tmp_path: Path) -> None:
    config_path = tmp_path / "webui_overrides.json"
    journal_path = tmp_path / "provider-journal"
    script = """
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from utils.credential_pool import CredentialPool
from web.config_service import ConfigService
from web.provider_application import (
    ProviderApplicationService,
    ProviderCredentialStore,
    ProviderRepository,
    ProviderRuntimeRegistry,
    ProviderTransactionJournal,
)

config = ConfigService(path=Path(sys.argv[1]))
repository = ProviderRepository(config)
repository.set("one", {"label": "One", "order": 7})
repository.set("two", {"label": "Two", "order": 3})
journal = ProviderTransactionJournal(Path(sys.argv[2]))
service = ProviderApplicationService(
    repository,
    ProviderCredentialStore(Path(sys.argv[2]) / "credentials"),
    ProviderRuntimeRegistry(SimpleNamespace(_custom_clients={}), CredentialPool()),
    transaction_journal=journal,
)
journal.clear_reorder = lambda: os._exit(23)
asyncio.run(service.reorder(["two", "one"]))
"""

    crashed = subprocess.run(
        [sys.executable, "-c", script, str(config_path), str(journal_path)],
        cwd=Path(__file__).resolve().parent.parent,
        check=False,
    )

    assert crashed.returncode == 23
    config = ConfigService(path=config_path)
    repository = ProviderRepository(config)
    assert repository.get("two")["order"] == 0
    assert repository.get("one")["order"] == 1
    recovery = ProviderApplicationService(
        repository,
        ProviderCredentialStore(tmp_path / "credentials"),
        ProviderRuntimeRegistry(SimpleNamespace(_custom_clients={}), CredentialPool()),
        transaction_journal=ProviderTransactionJournal(journal_path),
    )

    recovered = recovery.recover_pending_transactions()

    assert recovered == ["reorder"]
    assert repository.get("one")["order"] == 7
    assert repository.get("two")["order"] == 3
    assert not (journal_path / ".reorder.json").exists()


@pytest.mark.asyncio
async def test_setup_auto_registration_delegates_to_shared_application_service(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    from web.routers import setup

    calls: list[tuple[str, dict[str, Any], str]] = []

    class Service:
        async def upsert_from_setup(
            self, provider_id: str, value: dict[str, Any], api_key: str
        ) -> dict[str, Any]:
            calls.append((provider_id, value, api_key))
            return value

    app = SimpleNamespace(state=SimpleNamespace(core=SimpleNamespace(router=SimpleNamespace())))
    monkeypatch.setattr("web.app_ref.get_app", lambda: app)
    monkeypatch.setattr(
        "web.routers.models.get_provider_application_service",
        lambda actual_app: Service(),
    )

    await setup._auto_register_providers({"DEEPSEEK_API_KEY": "secret-one"})

    assert calls == [
        (
            "deepseek",
            {
                "label": "DeepSeek",
                "format": "openai",
                "base_url": "https://api.deepseek.com/v1",
                "default_model": "",
                "enabled": True,
                "order": 2,
            },
            "secret-one",
        )
    ]


def test_config_delete_save_failure_restores_memory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = ConfigService(path=tmp_path / "config.json")
    config.set("models.providers.example", record())
    monkeypatch.setattr(config, "_save", lambda: (_ for _ in ()).throw(OSError("save")))

    with pytest.raises(OSError, match="save"):
        config.delete("models.providers.example")

    assert config.get("models.providers.example") == record()


def test_credential_pool_snapshot_replace_remove_are_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(CredentialPool, "_load_from_env", lambda self: None)
    pool = CredentialPool()
    original = Credential("one", "example", "https://api.example.com/v1")
    pool.replace_provider("example", original)

    snapshot = pool.snapshot_provider("example")
    pool.replace_provider("example", Credential("two", "example"))
    pool.restore_provider("example", snapshot)
    snapshot[0].api_key = "mutated"

    assert pool.snapshot_provider("example")[0].api_key == "one"
    removed = pool.remove_provider("example")
    assert removed[0].api_key == "one"
    assert pool.snapshot_provider("example") == []


@pytest.mark.asyncio
async def test_router_provider_lifecycle_delegates_to_application_service(monkeypatch: pytest.MonkeyPatch) -> None:
    from web.routers import models

    calls: list[tuple[Any, ...]] = []

    class Service:
        async def create(self, provider_id: str, value: dict[str, Any], api_key: str) -> dict[str, Any]:
            calls.append(("create", provider_id, value, api_key))
            return value

        async def update(
            self, provider_id: str, value: dict[str, Any], *, api_key: str | None = None
        ) -> dict[str, Any]:
            calls.append(("update", provider_id, value, api_key))
            return value

        async def set_key(self, provider_id: str, api_key: str) -> dict[str, Any]:
            calls.append(("key", provider_id, api_key))
            return record()

        async def delete(self, provider_id: str) -> None:
            calls.append(("delete", provider_id))

    config = SimpleNamespace(
        get=lambda path, default=None: record() if path == "models.providers.example" else default
    )
    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(core=SimpleNamespace(router=SimpleNamespace(_custom_clients={})))),
        headers={"X-Confirm": "yes"},
    )

    monkeypatch.setattr(models, "_cfg", lambda request: config)
    monkeypatch.setattr(models, "_provider_service", lambda request: Service())
    monkeypatch.setattr(models, "_audit", lambda *args: asyncio.sleep(0))
    monkeypatch.setattr(models, "invalidate_discovery_cache", lambda: asyncio.sleep(0))
    monkeypatch.setattr(models, "_broadcast_changed", lambda: asyncio.sleep(0))
    monkeypatch.setattr("model_router.ROUTE_TABLE", {})

    await models.create_provider(
        {
            "id": "created",
            "format": "openai",
            "base_url": "https://api.example.com/v1",
            "api_key": "secret-one",
        },
        request,
    )
    await models.update_provider("example", {"enabled": False}, request)
    await models.set_provider_key("example", {"api_key": "secret-two"}, request)
    await models.delete_provider("example", request)

    assert [call[0] for call in calls] == ["create", "update", "key", "delete"]
    assert calls[0][1] == "created"
    assert calls[1][2]["enabled"] is False
    assert calls[2] == ("key", "example", "secret-two")


@pytest.mark.asyncio
async def test_router_maps_provider_transaction_failure_to_stable_protocol(monkeypatch: pytest.MonkeyPatch) -> None:
    from core.app_exception import ProtocolError
    from web.routers import models

    class Service:
        async def update(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            raise OSError("secret material must not escape")

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(core=SimpleNamespace(router=SimpleNamespace(_custom_clients={})))),
        headers={},
    )
    monkeypatch.setattr(
        models,
        "_cfg",
        lambda request: SimpleNamespace(
            get=lambda path, default=None: record() if path == "models.providers.example" else default
        ),
    )
    monkeypatch.setattr(models, "_provider_service", lambda request: Service())

    with pytest.raises(ProtocolError) as error:
        await models.update_provider("example", {"enabled": False}, request)

    assert error.value.code == "PROVIDER_OPERATION_FAILED"
    assert error.value.stage == "persist"
    assert error.value.retryable is False
    assert error.value.message == "provider 操作失败"
    assert isinstance(error.value.cause, OSError)


@pytest.mark.asyncio
async def test_key_success_invalidates_cache_and_broadcasts(monkeypatch: pytest.MonkeyPatch) -> None:
    from web.routers import models

    effects: list[str] = []

    class Service:
        async def set_key(self, provider_id: str, api_key: str) -> dict[str, Any]:
            return record()

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(core=SimpleNamespace(router=SimpleNamespace(_custom_clients={})))),
        headers={},
    )
    monkeypatch.setattr(models, "_cfg", lambda request: SimpleNamespace(get=lambda *args: record()))
    monkeypatch.setattr(models, "_provider_service", lambda request: Service())
    monkeypatch.setattr(models, "_audit", lambda *args: asyncio.sleep(0))

    async def invalidate() -> None:
        effects.append("invalidate")

    async def broadcast() -> None:
        effects.append("broadcast")

    monkeypatch.setattr(models, "invalidate_discovery_cache", invalidate)
    monkeypatch.setattr(models, "_broadcast_changed", broadcast)

    await models.set_provider_key("example", {"api_key": "secret-two"}, request)

    assert effects == ["invalidate", "broadcast"]


@pytest.mark.asyncio
async def test_update_rejects_invalid_format_before_transaction(monkeypatch: pytest.MonkeyPatch) -> None:
    from fastapi import HTTPException

    from web.routers import models

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()), headers={})
    monkeypatch.setattr(models, "_cfg", lambda request: SimpleNamespace(get=lambda *args: record()))

    with pytest.raises(HTTPException, match="format 必须是 openai 或 anthropic") as error:
        await models.update_provider("example", {"format": "unknown"}, request)

    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_create_validate_only_validates_candidate_without_mutation_or_probe(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    from web.routers import models

    calls: list[str] = []

    class Service:
        async def validate_candidate(self, provider_id: str, value: dict[str, Any], api_key: str) -> dict[str, Any]:
            calls.append("validate")
            return value

        async def create(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
            calls.append("create")
            raise AssertionError("validate_only must not mutate")

    config = SimpleNamespace(get=lambda path, default=None: default)
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()), headers={})
    monkeypatch.setattr(models, "_cfg", lambda request: config)
    monkeypatch.setattr(models, "_provider_service", lambda request: Service())

    result = await models.create_provider(
        {
            "id": "example",
            "label": "Example",
            "format": "openai",
            "base_url": "https://api.example.com",
            "default_model": "example-chat",
            "api_key": "secret-one",
            "validate_only": True,
        },
        request,
    )

    assert calls == ["validate"]
    assert result.data["validated"] is True
    assert result.data["probe_performed"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("label", "x" * 129),
        ("default_model", "x" * 257),
        ("api_key", "x" * 8193),
        ("enabled", "false"),
    ],
)
async def test_create_rejects_unsafe_field_candidates_before_service(
    monkeypatch: pytest.MonkeyPatch, field: str, value: Any
) -> None:
    from fastapi import HTTPException

    from web.routers import models

    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace()), headers={})
    monkeypatch.setattr(models, "_cfg", lambda request: SimpleNamespace(get=lambda path, default=None: default))
    monkeypatch.setattr(
        models,
        "_provider_service",
        lambda request: (_ for _ in ()).throw(AssertionError("invalid candidate reached service")),
    )
    body = {
        "id": "example",
        "label": "Example",
        "format": "openai",
        "base_url": "https://api.example.com",
        "default_model": "example-chat",
        "api_key": "secret-one",
    }
    body[field] = value

    with pytest.raises(HTTPException) as error:
        await models.create_provider(body, request)

    assert error.value.status_code == 400


@pytest.mark.asyncio
async def test_validate_candidate_builds_and_closes_temporary_client(harness: Harness) -> None:
    result = await harness.service.validate_candidate("example", record(), "secret-one")

    assert result == record()
    assert harness.clients[0].closed is True
    assert state(harness) == (None, "", None, [])


def test_real_subprocess_crash_recovers_service_persistence_journal(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parent.parent
    child_root = tmp_path / "child"
    code = f"""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, {str(project_root)!r})
from utils.credential_pool import CredentialPool
from web.config_service import ConfigService
from web.provider_application import ProviderApplicationService, ProviderCredentialStore, ProviderRepository, ProviderRuntimeRegistry, ProviderTransactionJournal
root = Path({str(child_root)!r})
config = ConfigService(path=root / 'webui_overrides.json')
credentials = ProviderCredentialStore(root / 'credentials', encoder=lambda key: 'encoded:' + key, decoder=lambda value: value.removeprefix('encoded:') if value.startswith('encoded:') else None)
service = ProviderApplicationService(ProviderRepository(config), credentials, ProviderRuntimeRegistry(SimpleNamespace(_custom_clients={{}}), CredentialPool(), client_builder=lambda *args: SimpleNamespace()), transaction_journal=ProviderTransactionJournal(root / 'journal'))
def crash_write(provider_id, api_key):
    os._exit(23)
credentials.write = crash_write
asyncio.run(service.create('crashed', {record()!r}, 'secret-one'))
"""

    result = subprocess.run([sys.executable, "-c", code], check=False)

    assert result.returncode == 23
    config = ConfigService(path=child_root / "webui_overrides.json")
    credentials = ProviderCredentialStore(
        child_root / "credentials",
        encoder=lambda key: f"encoded:{key}",
        decoder=lambda value: value.removeprefix("encoded:") if value.startswith("encoded:") else None,
    )
    service = ProviderApplicationService(
        ProviderRepository(config),
        credentials,
        ProviderRuntimeRegistry(SimpleNamespace(_custom_clients={}), CredentialPool()),
        transaction_journal=ProviderTransactionJournal(child_root / "journal"),
    )
    assert config.get("models.providers.crashed") == record()
    assert service.recover_pending_transactions() == ["crashed"]
    assert config.get("models.providers.crashed") is None
    assert credentials.load("crashed") == ""
    assert service.transaction_journal.pending_provider_ids() == []


def test_lazy_registration_cannot_observe_delete_partial_state(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    from model_router import ModelRouter
    from web import custom_providers

    asyncio.run(harness.service.create("example", record(), "secret-one"))
    delete_entered = threading.Event()
    delete_release = threading.Event()
    original_delete = harness.repository.delete

    def gated_delete(provider_id: str) -> None:
        original_delete(provider_id)
        delete_entered.set()
        delete_release.wait(timeout=2)

    monkeypatch.setattr(harness.repository, "delete", gated_delete)
    monkeypatch.setattr("web.config_service.get_config_service", lambda: harness.repository._config)
    monkeypatch.setattr("web._provider_keys.load_provider_key", lambda provider_id: harness.credentials.load(provider_id))
    registrations: list[str] = []
    monkeypatch.setattr(
        custom_providers,
        "register_into_router",
        lambda router, provider_id, fmt, base_url, api_key: registrations.append(provider_id),
    )
    router = SimpleNamespace(_custom_clients={})
    delete_thread = threading.Thread(target=lambda: asyncio.run(harness.service.delete("example")))
    lazy_thread = threading.Thread(target=ModelRouter._lazy_register_provider, args=(router, "example"))

    delete_thread.start()
    assert delete_entered.wait(timeout=2)
    lazy_thread.start()
    lazy_thread.join(timeout=0.05)
    assert lazy_thread.is_alive() is True
    delete_release.set()
    delete_thread.join(timeout=2)
    lazy_thread.join(timeout=2)

    assert registrations == []
    assert state(harness) == (None, "", None, [])


@pytest.mark.asyncio
async def test_server_creates_service_and_recovers_before_startup_registration(
    monkeypatch: pytest.MonkeyPatch
) -> None:
    from web import server

    events: list[str] = []
    core = SimpleNamespace()
    app = SimpleNamespace(state=SimpleNamespace(core=core))

    class Registry:
        async def load_persisted(self) -> None:
            events.append("registry")

    monkeypatch.setattr(server, "_run_startup_config_migrations", lambda: events.append("migration"))
    monkeypatch.setattr("web.config_service.get_config_service", lambda: "config")
    monkeypatch.setattr("web.agent_registry.AgentRegistry", lambda actual_core: Registry())
    monkeypatch.setattr(
        "web.routers.models.get_provider_application_service",
        lambda actual_app, config: events.append("service_recovered") or SimpleNamespace(),
    )

    await server._init_lifespan_resources(app)

    assert events == ["migration", "service_recovered", "registry"]


def test_all_runtime_registration_entries_share_global_coordinator(monkeypatch: pytest.MonkeyPatch) -> None:
    from web import custom_providers

    router = SimpleNamespace(_custom_clients={})
    active = 0
    maximum = 0
    entered = threading.Event()
    release = threading.Event()

    def build_client(*args: Any) -> FakeClient:
        nonlocal active, maximum
        active += 1
        maximum = max(maximum, active)
        if active == 1:
            entered.set()
            release.wait(timeout=2)
        client = FakeClient(str(args))
        active -= 1
        return client

    monkeypatch.setattr(custom_providers, "build_client", build_client)
    first = threading.Thread(
        target=custom_providers.register_into_router,
        args=(router, "one", "openai", "https://one.example.com/v1", "one"),
    )
    second = threading.Thread(
        target=custom_providers.register_into_router,
        args=(router, "two", "openai", "https://two.example.com/v1", "two"),
    )
    first.start()
    assert entered.wait(timeout=2)
    second.start()
    second.join(timeout=0.05)

    assert second.is_alive() is True
    release.set()
    first.join(timeout=2)
    second.join(timeout=2)
    assert maximum == 1


@pytest.mark.asyncio
async def test_update_reads_and_merges_current_record_inside_provider_lock(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    await harness.service.create("example", record(), "secret-one")
    entered = asyncio.Event()
    release = asyncio.Event()
    original_mutate = harness.service._mutate

    async def gated_mutate(*args: Any, **kwargs: Any) -> dict[str, Any]:
        entered.set()
        await release.wait()
        return await original_mutate(*args, **kwargs)

    monkeypatch.setattr(harness.service, "_mutate", gated_mutate)
    first = asyncio.create_task(harness.service.update("example", {"label": "First"}))
    await entered.wait()
    second = asyncio.create_task(harness.service.update("example", {"default_model": "second-model"}))
    release.set()
    await asyncio.gather(first, second)

    assert harness.repository.get("example") == {
        **record(),
        "label": "First",
        "default_model": "second-model",
    }


def test_key_migration_shares_global_runtime_lock_and_serializes_threads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from web import _provider_keys, custom_providers

    path = tmp_path / "provider_example.key"
    path.write_text("plain-secret", encoding="utf-8")
    monkeypatch.setattr(_provider_keys, "_key_file", lambda provider_id: path)
    monkeypatch.setattr(_provider_keys, "_encode_key", lambda value: f"encoded:{value}")
    monkeypatch.setattr("security.credential_vault.is_encrypted", lambda value: value.startswith("encoded:"))
    custom_providers._runtime_registration_coordinator.acquire()
    results: list[bool] = []
    workers = [threading.Thread(target=lambda: results.append(_provider_keys.migrate_provider_key("example"))) for _ in range(8)]
    try:
        for worker in workers:
            worker.start()
        for worker in workers:
            worker.join(timeout=0.05)
        assert all(worker.is_alive() for worker in workers)
    finally:
        custom_providers._runtime_registration_coordinator.release()
    for worker in workers:
        worker.join(timeout=2)

    assert results.count(True) == 1
    assert path.read_text(encoding="utf-8").strip() == "encoded:plain-secret"


def test_lazy_and_discovery_ignore_disabled_provider(harness: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    from model_router import ModelRouter
    from web import custom_providers
    from web.routers import model_discovery

    harness.repository.set("example", record(enabled=False))
    harness.credentials.write("example", "secret-one")
    monkeypatch.setattr("web.config_service.get_config_service", lambda: harness.repository._config)
    monkeypatch.setattr("web._provider_keys.load_provider_key", lambda provider_id: harness.credentials.load(provider_id))
    registrations: list[str] = []
    monkeypatch.setattr(
        custom_providers,
        "register_into_router",
        lambda router, provider_id, fmt, base_url, api_key: registrations.append(provider_id),
    )

    ModelRouter._lazy_register_provider(SimpleNamespace(_custom_clients={}), "example")

    assert registrations == []
    assert model_discovery._get_all_providers() == []


def test_corrupt_journal_is_quarantined_and_recovery_continues_safely(
    harness: Harness, caplog: pytest.LogCaptureFixture
) -> None:
    journal = harness.service.transaction_journal
    journal.prepare("example", record(), harness.credentials.snapshot("example"))
    corrupt = journal._directory / "secret-provider.json"
    corrupt.write_text('{"api_key":"do-not-report"', encoding="utf-8")
    harness.repository.set("example", record(base_url="https://partial.example.com/v1"))

    recovered = harness.service.recover_pending_transactions()

    assert recovered == ["example"]
    assert harness.repository.get("example") == record()
    assert not corrupt.exists()
    assert len(list(journal._directory.glob("secret-provider.json.corrupt-*"))) == 1
    assert harness.service.last_recovery_report == [
        {"journal": "secret-provider.json", "status": "quarantined", "error_type": "JSONDecodeError"}
    ]
    assert "do-not-report" not in caplog.text


def test_journal_and_credential_replace_attempt_parent_directory_persistence(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[Path] = []
    monkeypatch.setattr("utils.atomic_write.fsync_directory_best_effort", lambda path: calls.append(Path(path)))

    harness.credentials.write("example", "secret-one")
    harness.service.transaction_journal.prepare(
        "example", record(), harness.credentials.snapshot("example")
    )

    assert calls == [
        harness.credentials._directory,
        harness.service.transaction_journal._directory,
    ]
