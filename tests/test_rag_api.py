from fastapi.testclient import TestClient

import app.main as main
from app.config import Settings, get_settings
from app.store import ReportStore


def test_rest_sse_reuse_and_archive_read_after_process_cache_reset(tmp_path, monkeypatch):
    settings = Settings(llm_api_key="", tavily_api_key="", rag_db=str(tmp_path / "rag.db"), memory_db=str(tmp_path / "memory.db"))
    main.app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(main, "store", ReportStore())
    try:
        with TestClient(main.app) as client:
            request = {"industry": "芯片", "use_memory": False}
            first = client.post("/api/reports", json=request).json()
            second = client.post("/api/reports", json=request).json()
            assert second["reused"] and second["report_id"] == first["report_id"]
            stream = client.post("/api/reports/stream", json=request)
            assert "event: report.reused" in stream.text and "event: report\n" in stream.text
            assert "event: knowledge.acquired" not in stream.text
            monkeypatch.setattr(main, "store", ReportStore())
            archived = client.get(f"/api/reports/{first['report_id']}")
            assert archived.status_code == 200
            assert archived.json()["report_id"] == first["report_id"]
            assert client.get(f"/api/reports/{first['report_id']}/trace").json()["trace"]
            assert client.get("/api/rag/reports").json()
            # Demo storage is reusable as demo, never as related factual material.
            assert client.post("/api/rag/search", json={"industry":"计算机"}).json() == []
    finally:
        main.app.dependency_overrides.clear()
