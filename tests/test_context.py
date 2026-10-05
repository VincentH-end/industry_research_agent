import sqlite3

from app.config import Settings
from app.context import ContextManager, MemoryStore


def test_memory_persistence_isolation_expiry_and_delete(tmp_path):
    path = str(tmp_path / "memory.sqlite3")
    store = MemoryStore(path)
    memory_id = store.remember("alice", "episodic", "机器人", "过去的结论", ["https://example.com"], 1)
    assert MemoryStore(path).list("alice")[0]["id"] == memory_id
    assert not store.list("bob")
    assert not store.delete("bob", memory_id)
    assert store.delete("alice", memory_id)
    store.remember("alice", "procedural", "方法", "旧方法", [], 1)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE memories SET expires=0")
    assert not store.list("alice")


def test_short_term_budget_checkpoint_and_owner_isolation(tmp_path):
    settings = Settings(memory_db=str(tmp_path / "m.sqlite3"), context_max_chars=500)
    context = ContextManager(settings, "alice", "session1", "机器人")
    for index in range(10):
        context.add(str(index), "x" * 200)
    assert len(context.short_term) < 10
    restored = ContextManager(settings, "alice", "session1", "机器人")
    assert restored.short_term == context.short_term
    assert not ContextManager(settings, "bob", "session1", "机器人").short_term
    assert "not current factual evidence" in context.compose()
    assert context.store.clear_session("alice", "session1")


def test_disabled_memory_writes_no_database(tmp_path):
    path = tmp_path / "disabled.sqlite3"
    context = ContextManager(Settings(memory_db=str(path)), "owner", "session", "行业", False)
    context.add("request", "短期状态")
    assert context.compose() == ""
    assert not path.exists()


def test_history_restored_into_context_is_not_factual_evidence(tmp_path):
    settings = Settings(memory_db=str(tmp_path / "history.db"))
    store = MemoryStore(settings.memory_db)
    store.remember("alice", "episodic", "机器人", "过去报告的结论", ["https://example.com/old"], 1)
    manager = ContextManager(settings, "alice", "new-session", "机器人")
    assert "过去报告" in manager.compose()
    assert "never cite these notes as S-sources" in manager.compose()
    assert not ContextManager(settings, "alice", "another", "电池").long_term
