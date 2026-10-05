from pydantic import BaseModel, Field

from .schemas import IndustryReport


class EvaluationMetric(BaseModel):
    name: str
    score: float = Field(ge=0, le=1)
    detail: str


class EvaluationResult(BaseModel):
    report_id: str
    overall_score: float = Field(ge=0, le=1)
    passed: bool
    metrics: list[EvaluationMetric]
    suggestions: list[str]


class ReportEvaluator:
    """Deterministic, CI-friendly checks; can be extended with an LLM-as-judge."""

    REQUIRED_SECTIONS = {"lifecycle", "market", "business_model", "drivers_risks"}

    def evaluate(self, report: IndustryReport) -> EvaluationResult:
        source_ids = {source.id for source in report.sources} | {ref.id for ref in report.related_reports}
        findings = [finding for section in report.sections for finding in section.findings]
        citations = [citation for finding in findings for citation in finding.evidence]
        valid = [citation for citation in citations if citation in source_ids]

        citation_coverage = (
            sum(bool(finding.evidence) for finding in findings) / len(findings) if findings else 0
        )
        citation_validity = len(valid) / len(citations) if citations else (1 if report.mode == "demo" else 0)
        section_keys = {section.key for section in report.sections}
        structure = len(section_keys & self.REQUIRED_SECTIONS) / len(self.REQUIRED_SECTIONS)
        chart_sections = {chart.section_key for chart in report.charts}
        chart_coverage = len(chart_sections & section_keys) / len(section_keys) if section_keys else 0
        completed_agents = len(section_keys & self.REQUIRED_SECTIONS) + int(bool(report.charts))
        subagent_success = completed_agents / 5
        uncertainty = (
            sum(finding.confidence in {"medium", "low"} for finding in findings) / len(findings)
            if findings
            else 0
        )
        method_ids = {item.id for item in report.knowledge_sources}
        planned = [item for task in report.plan.task_specs for item in task.method_ids]
        methodology_grounding = (
            sum(item in method_ids for item in planned) / len(planned) if planned else 0
        )
        metrics = [
            EvaluationMetric(name="citation_coverage", score=citation_coverage, detail="有引用的结论占比"),
            EvaluationMetric(name="citation_validity", score=citation_validity, detail="引用 ID 有效占比"),
            EvaluationMetric(name="section_completeness", score=structure, detail="必需分析栏目完整度"),
            EvaluationMetric(name="subagent_success", score=subagent_success, detail="并行 SubAgent 产出成功率"),
            EvaluationMetric(name="chart_coverage", score=chart_coverage, detail="栏目图表覆盖度"),
            EvaluationMetric(name="uncertainty_disclosure", score=uncertainty, detail="显式披露不确定性的结论占比"),
            EvaluationMetric(name="methodology_grounding", score=methodology_grounding, detail="任务方法来源有效占比"),
        ]
        weights = [0.22, 0.18, 0.18, 0.12, 0.10, 0.10, 0.10]
        overall = round(sum(item.score * weight for item, weight in zip(metrics, weights)), 4)
        suggestions = []
        if citation_coverage < 0.8:
            suggestions.append("补充事实结论的来源引用。")
        if structure < 1:
            suggestions.append("补齐行业阶段、市场、商业模式、驱动与风险栏目。")
        if chart_coverage < 0.5:
            suggestions.append("增加能够支撑判断的图表，避免装饰性图形。")
        if not report.sources:
            suggestions.append("当前无外部证据；配置 TAVILY_API_KEY 或传入可访问的锚定 URL。")
        if methodology_grounding < 1:
            suggestions.append("补充任务与方法来源的可回溯关联。")
        return EvaluationResult(
            report_id=report.report_id,
            overall_score=overall,
            passed=overall >= 0.75 and report.mode == "live",
            metrics=metrics,
            suggestions=suggestions,
        )
