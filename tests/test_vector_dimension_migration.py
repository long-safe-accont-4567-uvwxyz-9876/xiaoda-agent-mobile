from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path

import pytest

TABLE_ROWS = {
    "memories_vec": [(1, "alpha memory"), (2, "beta memory")],
    "memories_child_vec": [(10, "alpha child")],
    "kg_entities_vec": [(20, "entity: alpha summary")],
    "kg_relations_vec": [(30, "alpha relates beta")],
}


def _connect_vec(path: Path):
    import sqlite_vec

    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _create_source_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE episodic_memories (id INTEGER PRIMARY KEY, summary TEXT NOT NULL);
        CREATE TABLE memory_child_chunks (id INTEGER PRIMARY KEY, embed_content TEXT NOT NULL);
        CREATE TABLE kg_entities_v2 (name TEXT NOT NULL, summary TEXT NOT NULL);
        CREATE TABLE kg_relations_v2 (fact TEXT NOT NULL);
        """
    )
    conn.executemany("INSERT INTO episodic_memories VALUES (?, ?)", TABLE_ROWS["memories_vec"])
    conn.executemany("INSERT INTO memory_child_chunks VALUES (?, ?)", TABLE_ROWS["memories_child_vec"])
    conn.execute("INSERT INTO kg_entities_v2(rowid, name, summary) VALUES (?, ?, ?)", (20, "entity", "alpha summary"))
    conn.execute("INSERT INTO kg_relations_v2(rowid, fact) VALUES (?, ?)", TABLE_ROWS["kg_relations_vec"][0])
    conn.commit()
    conn.close()


def _create_vector_db(path: Path, dimensions: int = 2) -> bytes:
    conn = _connect_vec(path)
    for table in TABLE_ROWS:
        conn.execute(f"CREATE VIRTUAL TABLE {table} USING vec0(embedding float[{dimensions}])")
        for row_id, _ in TABLE_ROWS[table]:
            conn.execute(
                f"INSERT INTO {table}(rowid, embedding) VALUES (?, vec_f32(?))",
                (row_id, json.dumps([0.5] * dimensions)),
            )
    conn.commit()
    conn.close()
    return path.read_bytes()


def _vector_for(text: str, dimensions: int = 4) -> list[float]:
    values = [float((sum(text.encode()) + index * 17) % 97 + 1) for index in range(dimensions)]
    norm = math.sqrt(sum(value * value for value in values))
    return [value / norm for value in values]


class RecordingEmbedder:
    def __init__(self, dimensions: int = 4, fail_on_call: int | None = None) -> None:
        self.dimensions = dimensions
        self.fail_on_call = fail_on_call
        self.calls: list[list[str]] = []

    async def __call__(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        if self.fail_on_call == len(self.calls):
            raise RuntimeError("temporary rate limit")
        return [_vector_for(text, self.dimensions) for text in texts]


@pytest.mark.asyncio
async def test_migrates_all_source_rows_to_target_dimension(tmp_path):
    from scripts.migrate_vector_dimensions import VectorDimensionMigrator

    source_db = tmp_path / "agent.db"
    vector_db = tmp_path / "agent_vec.db"
    _create_source_db(source_db)
    _create_vector_db(vector_db)

    result = await VectorDimensionMigrator(
        source_db=source_db,
        vector_db=vector_db,
        target_dimensions=4,
        embed_batch=RecordingEmbedder(),
        batch_size=2,
    ).migrate()

    assert result.source_dimensions == 2
    assert result.target_dimensions == 4
    assert result.total_rows == 5
    assert result.migrated_rows == 5
    assert result.backup_path.exists()
    conn = _connect_vec(vector_db)
    try:
        for table, rows in TABLE_ROWS.items():
            stored = conn.execute(f"SELECT rowid, embedding FROM {table} ORDER BY rowid").fetchall()
            assert [row[0] for row in stored] == [row[0] for row in rows]
            assert all(len(row[1]) == 4 * 4 for row in stored)
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_rejects_missing_remote_embedding_configuration_before_backup(tmp_path):
    from scripts.migrate_vector_dimensions import build_remote_embedder

    with pytest.raises(ValueError, match="EMBED_API_KEY"):
        build_remote_embedder(api_key="", model="embed-model")


@pytest.mark.asyncio
async def test_failure_preserves_original_and_checkpoint_resumes(tmp_path):
    from scripts.migrate_vector_dimensions import VectorDimensionMigrator

    source_db = tmp_path / "agent.db"
    vector_db = tmp_path / "agent_vec.db"
    _create_source_db(source_db)
    original = _create_vector_db(vector_db)
    failing = RecordingEmbedder(fail_on_call=2)
    migrator = VectorDimensionMigrator(
        source_db=source_db,
        vector_db=vector_db,
        target_dimensions=4,
        embed_batch=failing,
        batch_size=1,
        max_retries=0,
    )

    with pytest.raises(RuntimeError, match="rate limit"):
        await migrator.migrate()

    assert vector_db.read_bytes() == original
    assert migrator.checkpoint_path.exists()
    checkpoint = json.loads(migrator.checkpoint_path.read_text(encoding="utf-8"))
    assert checkpoint["completed"]["memories_vec"] == 1

    resumed = RecordingEmbedder()
    result = await VectorDimensionMigrator(
        source_db=source_db,
        vector_db=vector_db,
        target_dimensions=4,
        embed_batch=resumed,
        batch_size=1,
        max_retries=0,
    ).migrate()

    assert result.migrated_rows == 5
    assert len(resumed.calls) == 4
    assert not migrator.checkpoint_path.exists()


@pytest.mark.asyncio
async def test_retry_uses_backoff_and_completes(tmp_path):
    from scripts.migrate_vector_dimensions import VectorDimensionMigrator

    source_db = tmp_path / "agent.db"
    vector_db = tmp_path / "agent_vec.db"
    _create_source_db(source_db)
    _create_vector_db(vector_db)
    embedder = RecordingEmbedder(fail_on_call=1)
    delays = []

    result = await VectorDimensionMigrator(
        source_db=source_db,
        vector_db=vector_db,
        target_dimensions=4,
        embed_batch=embedder,
        max_retries=1,
        sleep=lambda delay: delays.append(delay),
    ).migrate()

    assert result.migrated_rows == 5
    assert delays == [1.0]


@pytest.mark.asyncio
async def test_failed_atomic_swap_preserves_original_database(tmp_path):
    from scripts.migrate_vector_dimensions import VectorDimensionMigrator

    source_db = tmp_path / "agent.db"
    vector_db = tmp_path / "agent_vec.db"
    _create_source_db(source_db)
    original = _create_vector_db(vector_db)

    def fail_replace(source, target):
        raise OSError("replace blocked")

    with pytest.raises(OSError, match="replace blocked"):
        await VectorDimensionMigrator(
            source_db=source_db,
            vector_db=vector_db,
            target_dimensions=4,
            embed_batch=RecordingEmbedder(),
            replace=fail_replace,
        ).migrate()

    assert vector_db.read_bytes() == original
