from fastapi.testclient import TestClient

from app.config import Settings, get_settings
from app.main import app
from app.security import Principal, current_principal


def test_api_owner_isolation_and_memory_deletion(tmp_path):
    scopes = frozenset({"reports:read", "reports:write", "evals:read", "evals:write", "memory:read", "memory:write"})
    settings = Settings(llm_api_key="", tavily_api_key="", memory_db=str(tmp_path / "memory.db"), rag_db=str(tmp_path / "rag.db"), eval_artifact_dir=str(tmp_path / "evals"))
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[current_principal] = lambda: Principal("alice", "analyst", scopes)
    try:
        with TestClient(app) as client:
            report = client.post("/api/reports", json={"industry": "机器人", "session_id": "session1"}).json()
            memories = client.get("/api/memory").json()
            assert memories and all(item["kind"] == "procedural" for item in memories)
            assert client.get("/api/context/session1").json()["short_term"]
            app.dependency_overrides[current_principal] = lambda: Principal("bob", "analyst", scopes)
            assert client.get("/api/memory").json() == []
            assert client.get("/api/context/session1").json()["short_term"] == []
            assert client.delete(f"/api/memory/{memories[0]['id']}").status_code == 404
            for suffix in ("", "/trace", "/evaluation"):
                assert client.get(f"/api/reports/{report['report_id']}{suffix}").status_code == 404
            app.dependency_overrides[current_principal] = lambda: Principal("alice", "analyst", scopes)
            assert client.delete(f"/api/memory/{memories[0]['id']}").status_code == 200
            assert client.delete("/api/context/session1").json()["deleted"]
            cases = client.get("/api/evaluations/cases")
            assert cases.status_code == 200 and len(cases.json()) == 5
            evaluated = client.post("/api/evaluations/run", json={"mode": "fixture", "case_ids": ["industrial_robot"]})
            assert evaluated.status_code == 200 and evaluated.json()["pass_rate"] == 1
    finally:
        app.dependency_overrides.clear()
