from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
import shutil
import sqlite3
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

TABLE_SOURCES = {
    "memories_vec": "SELECT id, summary FROM episodic_memories WHERE TRIM(summary) != '' ORDER BY id",
    "memories_child_vec": "SELECT id, embed_content FROM memory_child_chunks WHERE TRIM(embed_content) != '' ORDER BY id",
    "kg_entities_vec": "SELECT rowid, name || ': ' || summary FROM kg_entities_v2 WHERE TRIM(name || summary) != '' ORDER BY rowid",
    "kg_relations_vec": "SELECT rowid, fact FROM kg_relations_v2 WHERE TRIM(fact) != '' ORDER BY rowid",
}

EmbedBatch = Callable[[list[str]], Awaitable[list[list[float]]]]


@dataclass(frozen=True)
class MigrationResult:
    source_dimensions: int
    target_dimensions: int
    total_rows: int
    migrated_rows: int
    backup_path: Path


def _connect_vector_db(path: Path) -> sqlite3.Connection:
    import sqlite_vec

    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def _table_dimensions(conn: sqlite3.Connection, table: str) -> int | None:
    try:
        row = conn.execute(f"SELECT embedding FROM {table} LIMIT 1").fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None or not isinstance(row[0], (bytes, bytearray)):
        return None
    return len(row[0]) // 4


def inspect_vector_dimensions(path: Path) -> dict[str, int | None]:
    conn = _connect_vector_db(path)
    try:
        return {table: _table_dimensions(conn, table) for table in TABLE_SOURCES}
    finally:
        conn.close()


def build_remote_embedder(api_key: str, model: str) -> EmbedBatch:
    if not api_key.strip():
        raise ValueError("EMBED_API_KEY is required")
    if not model.strip():
        raise ValueError("EMBED_MODEL is required")

    from openai import AsyncOpenAI

    client = AsyncOpenAI(
        api_key=api_key.strip(),
        base_url="https://api.siliconflow.cn/v1",
        max_retries=0,
    )

    async def embed(texts: list[str]) -> list[list[float]]:
        response = await client.embeddings.create(model=model.strip(), input=texts)
        ordered = sorted(response.data, key=lambda item: item.index)
        return [list(item.embedding) for item in ordered]

    return embed


class VectorDimensionMigrator:
    def __init__(
        self,
        source_db: Path,
        vector_db: Path,
        target_dimensions: int,
        embed_batch: EmbedBatch,
        batch_size: int = 32,
        max_retries: int = 3,
        sleep: Callable[[float], object] = asyncio.sleep,
        replace: Callable[[str | Path, str | Path], None] = os.replace,
    ) -> None:
        if target_dimensions <= 0:
            raise ValueError("target_dimensions must be positive")
        if batch_size <= 0:
            raise ValueError("batch_size must be positive")
        self.source_db = Path(source_db)
        self.vector_db = Path(vector_db)
        self.target_dimensions = target_dimensions
        self.embed_batch = embed_batch
        self.batch_size = batch_size
        self.max_retries = max_retries
        self.sleep = sleep
        self.replace = replace
        self.rebuild_path = self.vector_db.with_suffix(self.vector_db.suffix + ".rebuild")
        self.checkpoint_path = self.vector_db.with_suffix(self.vector_db.suffix + ".migration.json")
        self.backup_path = self.vector_db.with_suffix(self.vector_db.suffix + ".pre-dimension-migration.bak")

    def _load_source_rows(self) -> dict[str, list[tuple[int, str]]]:
        conn = sqlite3.connect(self.source_db)
        try:
            return {
                table: [(int(row[0]), str(row[1])) for row in conn.execute(sql).fetchall()]
                for table, sql in TABLE_SOURCES.items()
            }
        finally:
            conn.close()

    def _load_checkpoint(self) -> dict:
        if not self.checkpoint_path.exists():
            return {"target_dimensions": self.target_dimensions, "completed": {table: 0 for table in TABLE_SOURCES}}
        data = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        if data.get("target_dimensions") != self.target_dimensions:
            raise RuntimeError("checkpoint target dimension mismatch")
        return data

    def _save_checkpoint(self, checkpoint: dict) -> None:
        from utils.atomic_write import atomic_json_write

        atomic_json_write(self.checkpoint_path, checkpoint)

    def _prepare_rebuild(self, checkpoint: dict) -> sqlite3.Connection:
        resuming = self.rebuild_path.exists() and any(checkpoint["completed"].values())
        if not resuming:
            self.rebuild_path.unlink(missing_ok=True)
        conn = _connect_vector_db(self.rebuild_path)
        if not resuming:
            for table in TABLE_SOURCES:
                conn.execute(
                    f"CREATE VIRTUAL TABLE {table} USING vec0(embedding float[{self.target_dimensions}])"
                )
            conn.commit()
        return conn

    async def _embed_with_retry(self, texts: list[str]) -> list[list[float]]:
        for attempt in range(self.max_retries + 1):
            try:
                vectors = await self.embed_batch(texts)
                if len(vectors) != len(texts):
                    raise RuntimeError("embedding response count mismatch")
                if any(len(vector) != self.target_dimensions for vector in vectors):
                    raise RuntimeError("embedding response dimension mismatch")
                return vectors
            except Exception:
                if attempt >= self.max_retries:
                    raise
                delay = float(2**attempt)
                pending = self.sleep(delay)
                if inspect.isawaitable(pending):
                    await pending
        raise RuntimeError("unreachable")

    def _validate(self, conn: sqlite3.Connection, rows: dict[str, list[tuple[int, str]]]) -> int:
        migrated = 0
        for table, source_rows in rows.items():
            stored = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if stored != len(source_rows):
                raise RuntimeError(f"{table} row count mismatch")
            dimensions = _table_dimensions(conn, table)
            if source_rows and dimensions != self.target_dimensions:
                raise RuntimeError(f"{table} dimension mismatch")
            if source_rows:
                row_id = source_rows[0][0]
                embedding = conn.execute(
                    f"SELECT embedding FROM {table} WHERE rowid=?", (row_id,)
                ).fetchone()[0]
                nearest = conn.execute(
                    f"SELECT rowid FROM {table} WHERE embedding MATCH ? AND k=1 ORDER BY distance",
                    (embedding,),
                ).fetchone()
                if nearest is None or nearest[0] != row_id:
                    raise RuntimeError(f"{table} recall validation failed")
            migrated += stored
        return migrated

    async def migrate(self) -> MigrationResult:
        if not self.source_db.exists():
            raise FileNotFoundError(self.source_db)
        if not self.vector_db.exists():
            raise FileNotFoundError(self.vector_db)

        dimensions = inspect_vector_dimensions(self.vector_db)
        known_dimensions = {value for value in dimensions.values() if value is not None}
        if len(known_dimensions) > 1:
            raise RuntimeError("source vector tables use inconsistent dimensions")
        source_dimensions = next(iter(known_dimensions), 0)
        rows = self._load_source_rows()
        total_rows = sum(len(items) for items in rows.values())
        checkpoint = self._load_checkpoint()

        if not self.backup_path.exists():
            shutil.copy2(self.vector_db, self.backup_path)

        conn = self._prepare_rebuild(checkpoint)
        try:
            for table, table_rows in rows.items():
                completed = int(checkpoint["completed"].get(table, 0))
                if completed > len(table_rows):
                    raise RuntimeError(f"{table} checkpoint exceeds source rows")
                for start in range(completed, len(table_rows), self.batch_size):
                    chunk = table_rows[start : start + self.batch_size]
                    vectors = await self._embed_with_retry([text for _, text in chunk])
                    conn.execute("BEGIN")
                    try:
                        for (row_id, _), vector in zip(chunk, vectors):
                            conn.execute(
                                f"INSERT INTO {table}(rowid, embedding) VALUES (?, vec_f32(?))",
                                (row_id, json.dumps(vector)),
                            )
                        conn.commit()
                    except Exception:
                        conn.rollback()
                        raise
                    checkpoint["completed"][table] = start + len(chunk)
                    self._save_checkpoint(checkpoint)
            migrated_rows = self._validate(conn, rows)
        finally:
            conn.close()

        self.replace(self.rebuild_path, self.vector_db)
        self.checkpoint_path.unlink(missing_ok=True)
        brute_dir = self.vector_db.parent / f"{self.vector_db.stem}_brute"
        if brute_dir.exists():
            shutil.rmtree(brute_dir)
        return MigrationResult(
            source_dimensions=source_dimensions,
            target_dimensions=self.target_dimensions,
            total_rows=total_rows,
            migrated_rows=migrated_rows,
            backup_path=self.backup_path,
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Migrate sqlite-vec tables to a remote embedding dimension")
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--vec-db", type=Path, required=True)
    parser.add_argument("--dimensions", type=int, required=True)
    parser.add_argument("--batch-size", type=int, default=32)
    return parser.parse_args()


async def _main() -> int:
    args = _parse_args()
    embedder = build_remote_embedder(
        api_key=os.getenv("EMBED_API_KEY", ""),
        model=os.getenv("EMBED_MODEL", "BAAI/bge-m3"),
    )
    result = await VectorDimensionMigrator(
        source_db=args.db,
        vector_db=args.vec_db,
        target_dimensions=args.dimensions,
        embed_batch=embedder,
        batch_size=args.batch_size,
    ).migrate()
    print(json.dumps({
        "source_dimensions": result.source_dimensions,
        "target_dimensions": result.target_dimensions,
        "total_rows": result.total_rows,
        "migrated_rows": result.migrated_rows,
        "backup_path": str(result.backup_path),
        "completed_at": int(time.time()),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
