from datetime import datetime, timedelta, timezone

from app.agents import IndustryResearchOrchestrator, _demo_plan, _demo_sections, _validate_industry_citations
from app.config import Settings
from app.rag import ReportRAG
from app.schemas import IndustryReport, ReportRequest, SourceDocument


def seed_report(industry="芯片", mode="live"):
    request = ReportRequest(industry=industry, use_memory=False)
    sections = _demo_sections(request)
    sections[0].findings[0].summary = "合成测试：芯片产业链覆盖设计、制造、封装测试。"
    sections[0].findings[0].evidence = ["S-test"]
    return request, IndustryReport(
        report_id=f"test-{industry}-{mode}", industry=industry, region=request.region,
        horizon=request.horizon, generated_at=datetime.now(timezone.utc).isoformat(),
        mode=mode, executive_summary="合成测试报告", lifecycle_stage="测试阶段",
        lifecycle_score=50, plan=_demo_plan(request), sections=sections, charts=[],
        sources=[SourceDocument(id="S-test", title="合成测试来源", url="https://example.com/test",
            domain="example.com", excerpt="合成测试材料", retrieved_at=datetime.now(timezone.utc).isoformat())] if mode == "live" else [],
        methodology=[], limitations=["合成测试，不可用于真实决策。"], trace_id="original-trace",
    )


def test_exact_cache_scope_owner_freshness_and_restart(tmp_path):
    settings = Settings(rag_db=str(tmp_path / "reports.db"))
    archive = ReportRAG(settings)
    request, report = seed_report()
    archive.save("alice", request, report, [])
    assert ReportRAG(settings).cached("alice", request).report_id == report.report_id
    assert not archive.cached("bob", request)
    for update in ({"question":"另一个问题"}, {"region":"美国"}, {"horizon":"十年"}, {"anchor_sites":["example.com"]}):
        assert not archive.cached("alice", request.model_copy(update=update))
    report.generated_at = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    archive.save("alice", request, report, [])
    assert not archive.cached("alice", request)
    assert archive.get("alice", report.report_id)  # Archive remains readable, but not auto reused.


def test_related_chip_computer_search_and_demo_exclusion(tmp_path):
    archive = ReportRAG(Settings(rag_db=str(tmp_path / "reports.db")))
    request, report = seed_report()
    archive.save("alice", request, report, [])
    computer = ReportRequest(industry="计算机")
    hits = archive.search("alice", computer)
    assert hits and all(hit.industry == "芯片" for hit in hits)
    assert hits[0].source_urls == ["https://example.com/test"]
    assert not archive.search("bob", computer)
    assert not archive.search("alice", ReportRequest(industry="宠物医疗"))
    assert not archive.search("alice", ReportRequest(industry="计算机", region="美国"))
    demo_request, demo = seed_report("计算机", "demo")
    archive.save("alice", demo_request, demo, [])
    assert all(hit.report_id != demo.report_id for hit in archive.search("alice", computer))


async def test_cache_hit_skips_agents_and_force_refresh_regenerates(tmp_path):
    settings = Settings(llm_api_key="", tavily_api_key="", rag_db=str(tmp_path / "reports.db"))
    request, report = seed_report()
    ReportRAG(settings).save("alice", request, report, [])
    agent = IndustryResearchOrchestrator(settings)
    events = []
    async def emit(event, data):
        events.append(event)
    cached = await agent.run(request, emit, owner="alice")
    assert cached.reused and cached.report_id == report.report_id
    assert cached.generated_at == report.generated_at
    assert cached.origin_trace_id == "original-trace"
    assert "report.reused" in events and "knowledge.acquired" not in events
    fresh = await agent.run(request.model_copy(update={"force_refresh": True}), owner="alice")
    assert not fresh.reused and fresh.report_id != report.report_id
    assert fresh.related_reports


def test_historical_reference_is_not_numeric_evidence(tmp_path):
    archive = ReportRAG(Settings(rag_db=str(tmp_path / "reports.db")))
    request, report = seed_report()
    archive.save("alice", request, report, [])
    references = archive.search("alice", ReportRequest(industry="计算机"))
    sections = _demo_sections(ReportRequest(industry="计算机"))
    sections[0].findings[0].evidence = [references[0].id]
    metric = sections[0].metrics[0]
    metric.is_estimate = False
    metric.source_ids = [references[0].id]
    _validate_industry_citations(sections, [], references)
    assert sections[0].findings[0].evidence == [references[0].id]
    assert sections[0].findings[0].confidence == "low"
    assert metric not in sections[0].metrics


async def test_related_report_reaches_analysis_prompt_without_current_web_sources(tmp_path):
    import re
    from app.eval_fixtures import FixtureCollector, FixtureLLM
    from app.schemas import Section
    settings = Settings(llm_api_key="fixture", tavily_api_key="", rag_db=str(tmp_path / "reports.db"))
    request, previous = seed_report()
    ReportRAG(settings).save("alice", request, previous, [])
    computer = ReportRequest(industry="计算机", use_memory=False)
    prompts = []
    class EmptyCollector(FixtureCollector):
        async def collect(self, request):
            return []
    class HistoricalLLM(FixtureLLM):
        async def generate(self, system, prompt, schema):
            result = await super().generate(system, prompt, schema)
            if schema is Section:
                prompts.append(prompt)
                ref_id = re.search(r"\[(R-[^\]]+)\]", prompt).group(1)
                result.findings[0].evidence = [ref_id]
            return result
    agent = IndustryResearchOrchestrator(settings)
    agent.collector = EmptyCollector()
    agent.llm = HistoricalLLM(computer)
    report = await agent.run(computer, owner="alice")
    assert len(prompts) == 4 and all("芯片" in prompt for prompt in prompts)
    assert report.related_reports and not report.sources
    assert all(section.findings[0].confidence == "low" for section in report.sections)
    assert all(not section.metrics for section in report.sections)
    assert any("未获取新的网页证据" in limitation for limitation in report.limitations)
