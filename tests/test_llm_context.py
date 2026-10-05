from types import SimpleNamespace

import pytest
from pydantic import BaseModel

from app.config import Settings
from app.context import ContextManager, active_context
from app.llm import StructuredLLM


class TinyResult(BaseModel):
    value: str


async def test_context_is_injected_without_changing_system_or_schema(tmp_path, monkeypatch):
    settings = Settings(memory_db=str(tmp_path / "notes.db"))
    llm = StructuredLLM(settings)
    captured = {}
    async def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='{"value":"ok"}'))], usage=None)
    monkeypatch.setattr(llm.client.chat.completions, "create", create)
    context = ContextManager(settings, "alice", "session", "行业")
    context.add("plan", "按价值链研究")
    token = active_context.set(context)
    try:
        result = await llm.generate("trusted system", "current evidence", TinyResult)
    finally:
        active_context.reset(token)
    assert result.value == "ok"
    assert captured["messages"][0]["content"] == "trusted system"
    text = captured["messages"][1]["content"]
    assert "按价值链研究" in text and "JSON Schema" in text
    assert "never cite these notes as S-sources" in text


async def test_oversized_prompt_fails_instead_of_losing_evidence():
    llm = StructuredLLM(Settings(prompt_max_chars=5000))
    with pytest.raises(ValueError, match="PROMPT_MAX_CHARS"):
        await llm.generate("system", "x" * 5001, TinyResult)
