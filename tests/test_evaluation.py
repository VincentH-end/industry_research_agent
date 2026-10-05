from app.agents import _charts_from_sections, _demo_plan, _demo_sections
from app.evaluation import ReportEvaluator
from app.schemas import IndustryReport, ReportRequest


def test_demo_report_evaluates_without_fake_citations():
    request = ReportRequest(industry="工业机器人")
    sections = _demo_sections(request)
    report = IndustryReport(
        report_id="test",
        industry=request.industry,
        region=request.region,
        horizon=request.horizon,
        generated_at="2026-01-01T00:00:00+00:00",
        mode="demo",
        executive_summary="演示",
        lifecycle_stage="待证据判断",
        lifecycle_score=50,
        plan=_demo_plan(request),
        sections=sections,
        charts=_charts_from_sections(sections),
        sources=[],
        methodology=["test"],
        limitations=["demo"],
    )
    result = ReportEvaluator().evaluate(report)
    assert result.report_id == "test"
    assert 0 <= result.overall_score <= 1
    assert any("外部证据" in item for item in result.suggestions)

