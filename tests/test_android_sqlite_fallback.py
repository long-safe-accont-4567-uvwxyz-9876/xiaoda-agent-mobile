from pathlib import Path

import pytest

from db.database import CURRENT_SCHEMA_VERSION, DatabaseManager


@pytest.mark.asyncio
async def test_android_sqlite_without_fts5_keeps_memory_search_working(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("XIAODA_FORCE_NO_FTS5", "1")
    manager = DatabaseManager(tmp_path / "android.db")
    await manager.init()
    try:
        version = await manager.fetch_one("SELECT MAX(version) AS version FROM schema_version")
        assert version["version"] == CURRENT_SCHEMA_VERSION
        assert manager._fts5_available is False

        memory_id = await manager.memory.insert_episodic_memory("用户喜欢本地运行的小搭")
        matches = await manager.memory.search_memories_fts("本地运行")
        assert [row["id"] for row in matches] == [memory_id]

        child_id = await manager.memory.insert_child_chunk(memory_id, "安卓手机本地记忆检索")
        child_matches = await manager.memory.search_child_fts("本地记忆")
        assert [row["id"] for row in child_matches] == [child_id]
    finally:
        await manager.close()
