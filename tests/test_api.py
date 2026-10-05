from fastapi.testclient import TestClient

from app.main import app


def test_rest_sse_and_evaluation_flow():
    with TestClient(app) as client:
        health = client.get("/api/health")
        assert health.status_code == 200

        response = client.post("/api/reports", json={"industry": "工业机器人", "use_rag": False})
        assert response.status_code == 200
        report = response.json()
        assert report["mode"] == "demo"
        assert len(report["sections"]) == 4
        assert len(report["charts"]) == 4
        assert len(report["knowledge_sources"]) >= 4
        assert report["methodology_guide"]["source_ids"]
        assert len(report["plan"]["task_specs"]) == 4
        assert all(task["method_ids"] for task in report["plan"]["task_specs"])
        assert response.headers["X-Trace-ID"]
        assert report["session_id"]
        trace = client.get(f"/api/reports/{report['report_id']}/trace")
        assert trace.status_code == 200 and trace.json()["trace"]

        for page in ("overview", "methodology", "lifecycle", "market", "business_model", "drivers_risks", "sources", "evaluation"):
            child = client.get(f"/reports/{report['report_id']}/{page}")
            assert child.status_code == 200
            assert "report-nav" in child.text
        assert client.get(f"/reports/{report['report_id']}/unknown").status_code == 404

        evaluation = client.get(f"/api/reports/{report['report_id']}/evaluation")
        assert evaluation.status_code == 200
        assert any(item["name"] == "subagent_success" for item in evaluation.json()["metrics"])

        stream = client.post("/api/reports/stream", json={"industry": "低空经济", "use_rag": False})
        assert stream.status_code == 200
        assert stream.headers["content-type"].startswith("text/event-stream")
        assert "event: report" in stream.text
        assert "event: done" in stream.text
        assert stream.text.index("event: knowledge.acquired") < stream.text.index("event: plan.ready")
        assert stream.text.index("event: plan.ready") < stream.text.index("event: sources.collected")
        assert stream.text.index('"agent": "chart"') < stream.text.index('"agent": "main_agent"')
