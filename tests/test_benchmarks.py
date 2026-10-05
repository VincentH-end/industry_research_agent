import json

from app.benchmarks import BenchmarkRequest, load_cases, run_benchmark, score_candidate
from app.config import Settings
from app.schemas import IndustryReport


async def test_fixture_suite_executes_agent_and_captures_parallel_trace(tmp_path):
    settings = Settings(eval_artifact_dir=str(tmp_path / "evals"))
    result = await run_benchmark(settings, BenchmarkRequest(mode="fixture"))
    assert len(result["results"]) == 5
    assert result["pass_rate"] == 1
    artifact = json.loads(open(result["artifact"], encoding="utf-8").read())
    assert artifact["mode"] == "fixture"
    assert all(item["trace"] for item in artifact["results"])
    assert all(item["trajectory"]["parallel_overlap"] == 1 for item in artifact["results"] if item["parallel_required"])
    assert artifact["results"][-1]["trajectory"]["parallel_overlap"] == 0

    # Negative mutation: fluent output with fake citations must fail the hard gate.
    candidate = IndustryReport.model_validate(result["results"][0]["actual_report"])
    candidate.sections[0].findings[0].evidence = ["S-invented"]
    score = score_candidate(load_cases()[0], candidate, result["results"][0]["trace"])
    assert not score["passed"]
    assert "citation_integrity" in score["failures"]
    candidate = IndustryReport.model_validate(result["results"][0]["actual_report"])
    candidate.sections[0].metrics[0].source_ids = ["S-invented"]
    assert not score_candidate(load_cases()[0], candidate, result["results"][0]["trace"])["passed"]


async def test_demo_abstention_and_trace_order_mutation(tmp_path):
    result = await run_benchmark(Settings(eval_artifact_dir=str(tmp_path)),
        BenchmarkRequest(mode="demo", case_ids=["missing_evidence"]))
    item = result["results"][0]
    assert item["passed"]
    report = IndustryReport.model_validate(item["actual_report"])
    trace = [dict(record) for record in item["trace"]]
    for record in trace:
        if record["event"] == "span.completed" and record["agent"] == "knowledge_acquisition":
            record["elapsed_ms"] = 1e9
    assert not score_candidate(load_cases()[-1], report, trace)["passed"]


async def test_live_requires_model_key(tmp_path):
    import pytest
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        await run_benchmark(Settings(llm_api_key="", eval_artifact_dir=str(tmp_path)), BenchmarkRequest(mode="live"))
