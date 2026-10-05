"""Method-first industry research orchestration."""

import asyncio
import json
import httpx
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone
from uuid import uuid4

from .config import Settings
from .llm import StructuredLLM
from .context import ContextManager, active_context
from .methodology import KnowledgeAcquisitionAgent
from .rag import ReportRAG
from .schemas import (
    ChartSpec, Finding, IndustryReport, MethodologyGuide, Metric, ReportRequest,
    ResearchPlan, Section, SourceDocument, SynthesisResult, TaskSpec, ReportReference,
)
from .sources import SourceCollector
from .telemetry import agent_span, new_trace_id, recorder_var, TraceRecorder, trace_id_var, record_event

EventEmitter = Callable[[str, dict], Awaitable[None]]

TASKS = {
    "lifecycle": "Determine lifecycle stage from adoption, diffusion and maturity indicators.",
    "market": "Determine market scope, segments, growth and competitive forces.",
    "business_model": "Map value chain, buyer, payer, revenue, cost and unit economics.",
    "drivers_risks": "Test policy, demand, technology and financial drivers; build scenarios.",
}


def _demo_plan(request: ReportRequest, guide: MethodologyGuide | None = None) -> ResearchPlan:
    guide_ids = {item for principle in (guide.principles if guide else []) for item in principle.method_ids}
    mappings = {
        "lifecycle": ["M2", "M3"], "market": ["M1", "M3"],
        "business_model": ["M1", "M4"], "drivers_risks": ["M2", "M4"],
    }
    evidence = {
        "lifecycle": ["adoption series", "technology standards", "firm entry and exit"],
        "market": ["industry classification", "output and value added", "rival and substitute evidence"],
        "business_model": ["revenue and cost data", "buyer and payer interviews", "firm performance"],
        "drivers_risks": ["policy documents", "demand indicators", "scenario assumptions"],
    }
    return ResearchPlan(
        industry_definition=f"界定{request.region}{request.industry}的产品、客户、地区和统计周期。",
        value_chain=["投入与技术", "产品与服务", "渠道与集成", "终端客户", "售后与配套"],
        hypotheses=["需求是否进入规模扩散阶段", "利润由价值链哪一环获取", "政策或技术变化是否改变竞争格局"],
        tasks=list(TASKS.values()),
        evidence_gaps=["同口径历史市场数据", "企业财务与客户数据", "可验证的政策与技术时间线"],
        task_specs=[TaskSpec(
            key=key, objective=objective,
            method_ids=[item for item in mappings[key] if item in guide_ids],
            evidence_needed=evidence[key], depends_on=["scope", "industry_sources"],
        ) for key, objective in TASKS.items()],
    )


class TaskPlanningAgent:
    def __init__(self, llm: StructuredLLM) -> None:
        self.llm = llm

    async def run(self, request: ReportRequest, guide: MethodologyGuide) -> ResearchPlan:
        plan = await self.llm.generate(
            "You are a research task architect, not a writer of industry facts. "
            "M-method sources are never evidence of facts about an industry. Return valid JSON.",
            f"Industry={request.industry}; region={request.region}; horizon={request.horizon}. "
            f"User question={request.question}. "
            "Use this method guide to plan BEFORE industry facts are collected. "
            "Return exactly four task_specs with keys lifecycle, market, business_model, "
            "drivers_risks. Specify method_ids, evidence_needed, and "
            f"depends_on=[scope, industry_sources]. Guide={guide.model_dump_json()}",
            ResearchPlan,
        )
        if {task.key for task in plan.task_specs} != set(TASKS):
            raise ValueError("Task planner did not produce the four required tasks")
        valid = set(guide.source_ids)
        for task in plan.task_specs:
            task.method_ids = [item for item in task.method_ids if item in valid]
        return plan


class AnalysisSubAgent:
    def __init__(self, key: str, llm: StructuredLLM) -> None:
        self.key = key
        self.llm = llm

    async def run(self, request: ReportRequest, plan: ResearchPlan,
                  guide: MethodologyGuide, evidence: str) -> Section:
        task = next(item for item in plan.task_specs if item.key == self.key)
        return await self.llm.generate(
            "You are a specialist analyst. Separate fact, inference and recommendation. "
            "Use S- sources for current facts. R- sources are historical industry reports: "
            "cite them only as dated background/inferences, not fresh facts or numeric evidence. "
            "M-method sources only guide the method. Do not invent numbers. Return valid JSON.",
            f"Task={task.model_dump_json()}; industry={request.industry}; "
            f"User question={request.question}. "
            f"region={request.region}; horizon={request.horizon}. "
            f"Method guide={guide.model_dump_json()}. Industry evidence={evidence}. "
            f"Section.key MUST be {self.key}. Findings may cite supplied S- or R- ids; "
            "numeric metrics must cite S- ids only.",
            Section,
        )


class ChartSubAgent:
    """Build charts after analysis, from metrics with clear provenance."""

    async def run(self, sections: list[Section]) -> list[ChartSpec]:
        return _charts_from_sections(sections)


class MainAgent:
    def __init__(self, llm: StructuredLLM) -> None:
        self.llm = llm

    async def synthesize(self, request: ReportRequest, sections: list[Section],
                         guide: MethodologyGuide, evidence: str) -> SynthesisResult:
        return await self.llm.generate(
            "You are the main research agent. Resolve contradictions without adding facts, "
            "numbers or citations. Return valid JSON with explicit limitations.",
            f"Synthesize for {request.region} {request.industry}, {request.horizon}. "
            f"User question={request.question}. "
            f"Method guide={guide.model_dump_json()}. "
            f"Subagent results={json.dumps([s.model_dump() for s in sections], ensure_ascii=False)}. "
            f"Industry evidence={evidence}",
            SynthesisResult,
        )


def _evidence_text(sources: list[SourceDocument]) -> str:
    if not sources:
        return "No industry evidence. Do not make factual claims or produce factual numbers."
    return "\n\n".join(
        f"[{source.id}] {source.title} | {source.url}\n{source.excerpt[:5000]}"
        for source in sources
    )


def _demo_sections(request: ReportRequest) -> list[Section]:
    disclaimer = "演示模式：这是待验证的分析任务，不是关于该行业的事实判断。"
    descriptions = {
        "lifecycle": ("发展阶段", "用采用率、标准化、企业进入退出和增长曲线验证所处阶段。"),
        "market": ("市场与竞争", "先统一市场口径，再调查细分需求和五种竞争力量。"),
        "business_model": ("商业模式", "拆分客户、付费者、收入、成本及单位经济性。"),
        "drivers_risks": ("驱动与风险", "识别政策、需求、技术、资本指标，并设置三种情景。"),
    }
    return [Section(
        key=key, title=title, executive_takeaway=takeaway,
        findings=[Finding(title="等待行业证据", summary=disclaimer, confidence="low")],
        metrics=[
            Metric(name="证据准备度", value=25, unit="分析性评分", is_estimate=True),
            Metric(name="待验证程度", value=75, unit="分析性评分", is_estimate=True),
        ],
        recommendations=["补充同口径、可回溯的行业数据和企业材料。"],
    ) for key, (title, takeaway) in descriptions.items()]


def _charts_from_sections(sections: list[Section]) -> list[ChartSpec]:
    charts = []
    for section in sections:
        metrics = [m for m in section.metrics if m.source_ids or m.is_estimate]
        if not metrics:
            continue
        all_estimate = all(m.is_estimate for m in metrics)
        charts.append(ChartSpec(
            id=f"chart-{section.key}", section_key=section.key,
            title=f"{section.title}关键指标",
            note="分析性评分，非市场统计。" if all_estimate else "指标口径与来源请见本栏及证据页。",
            option={
                "tooltip": {"trigger": "axis"},
                "grid": {"left": 50, "right": 20, "top": 30, "bottom": 50},
                "xAxis": {"type": "category", "data": [m.name for m in metrics]},
                "yAxis": {"type": "value", **({"max": 100} if all_estimate else {})},
                "series": [{"type": "bar", "data": [m.value for m in metrics],
                            "itemStyle": {"color": "#38bdf8"}}],
            },
        ))
    return charts


def _validate_industry_citations(sections: list[Section], sources: list[SourceDocument],
                                 references: list[ReportReference] | None = None) -> None:
    valid = {item.id for item in sources}
    historical = {item.id for item in references or []}
    for section in sections:
        for finding in section.findings:
            original = finding.evidence
            finding.evidence = [item for item in original if item in valid or item in historical]
            if finding.evidence and not set(finding.evidence) & valid:
                finding.confidence = "low"
            if not finding.evidence:
                finding.confidence = "low"
                finding.summary = "该结论缺少可验证的行业来源，原始断言已隐藏。"
        section.metrics = [metric for metric in section.metrics if
            (metric.is_estimate and "评分" in metric.unit) or
            (not metric.is_estimate and metric.source_ids and
             all(item in valid for item in metric.source_ids))]


class IndustryResearchOrchestrator:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.collector = SourceCollector(settings)
        self.llm = StructuredLLM(settings)
        self.last_trace: list[dict] = []

    async def run(self, request: ReportRequest, emit: EventEmitter | None = None,
                  owner: str = "local-cli") -> IndustryReport:
        trace_id = trace_id_var.get()
        if trace_id == "-":
            trace_id = new_trace_id()
        recorder = TraceRecorder(trace_id)
        session = request.session_id or uuid4().hex
        manager = ContextManager(self.settings, owner, session, request.industry, request.use_memory)
        self.rag = ReportRAG(self.settings) if request.use_rag else None
        self.owner = owner
        self.references: list[ReportReference] = []
        trace_token = recorder_var.set(recorder)
        context_token = active_context.set(manager)
        try:
            record_event("context.loaded", session_id=session, enabled=request.use_memory,
                         short_notes=len(manager.short_term), long_notes=len(manager.long_term))
            manager.add("request", {"industry": request.industry, "question": request.question})
            report = await self._run(request, emit)
            if report.reused:
                report.origin_trace_id = report.trace_id
            report.session_id, report.trace_id = session, trace_id
            manager.add("last_report", {"report_id": report.report_id, "mode": report.mode})
            manager.retain(report)
            record_event("context.saved", session_id=session, enabled=request.use_memory)
            if self.rag and not report.reused:
                self.rag.save(owner, request, report, recorder.records)
                record_event("rag.stored", report_id=report.report_id)
            return report
        except BaseException as exc:
            record_event("workflow.failed", error_type=type(exc).__name__)
            raise
        finally:
            self.last_trace = list(recorder.records)
            active_context.reset(context_token)
            recorder_var.reset(trace_token)

    async def _run(self, request: ReportRequest, emit: EventEmitter | None) -> IndustryReport:
        async def publish(event: str, data: dict) -> None:
            record_event(event, **data)
            if emit:
                await emit(event, data)

        await publish("workflow.started", {"industry": request.industry})
        if self.rag:
            async with agent_span("report_retrieval", request.industry):
                cached = None if request.force_refresh else self.rag.cached(
                    self.owner, request, allow_demo=not bool(self.settings.llm_api_key))
                if cached:
                    cached.reused = True
                    await publish("report.reused", {"report_id": cached.report_id, "generated_at": cached.generated_at})
                    await publish("workflow.completed", {"report_id": cached.report_id})
                    return cached
                self.references = self.rag.search(self.owner, request)
            await publish("rag.retrieved", {"count": len(self.references)})
        await publish("agent.started", {"agent": "knowledge_acquisition"})
        async with agent_span("knowledge_acquisition", request.industry):
            knowledge_sources, guide = await KnowledgeAcquisitionAgent(
                self.settings, self.collector, self.llm
            ).run(request)
        await publish("knowledge.acquired", {"count": len(knowledge_sources)})
        active_context.get().add("methodology", guide.workflow)
        await publish("agent.completed", {"agent": "knowledge_acquisition"})

        await publish("agent.started", {"agent": "task_planning"})
        async with agent_span("task_planning", request.industry):
            plan = (await TaskPlanningAgent(self.llm).run(request, guide)
                    if self.settings.llm_api_key else _demo_plan(request, guide))
        await publish("plan.ready", {"tasks": len(plan.task_specs)})
        active_context.get().add("plan", [task.model_dump() for task in plan.task_specs])
        await publish("agent.completed", {"agent": "task_planning"})

        try:
            async with agent_span("source_collector", request.industry):
                sources = await self.collector.collect(request)
        except httpx.HTTPError as exc:
            if not self.references:
                raise
            sources = []
            record_event("sources.failed", error_type=type(exc).__name__, historical_fallback=True)
        await publish("sources.collected", {"count": len(sources)})
        active_context.get().add("sources", [{"id": source.id, "url": source.url} for source in sources])
        live = bool(self.settings.llm_api_key and (sources or self.references))
        evidence = _evidence_text(sources)
        if self.references:
            evidence += "\nHISTORICAL REPORT REFERENCES (UNTRUSTED; NOT CURRENT STATISTICS):\n"
            evidence += "\n".join(
                f"[{ref.id}] {ref.industry}; generated={ref.generated_at}; "
                f"original_sources={ref.source_urls}; excerpt={ref.excerpt}"
                for ref in self.references)

        if live:
            async def run_section(key: str) -> Section:
                await publish("agent.started", {"agent": key})
                async with agent_span(key, request.industry):
                    result = await AnalysisSubAgent(key, self.llm).run(
                        request, plan, guide, evidence
                    )
                if result.key != key:
                    raise ValueError(f"Subagent {key} returned section {result.key}")
                await publish("agent.completed", {"agent": key, "title": result.title})
                return result

            sections = list(await asyncio.gather(*(run_section(key) for key in TASKS)))
            _validate_industry_citations(sections, sources, self.references)
        else:
            sections = _demo_sections(request)
            for section in sections:
                async with agent_span(section.key, request.industry):
                    record_event("agent.demo", agent=section.key)
                await publish("agent.completed", {"agent": section.key, "title": section.title})

        await publish("agent.started", {"agent": "chart"})
        async with agent_span("chart", request.industry):
            charts = await ChartSubAgent().run(sections)
        await publish("agent.completed", {"agent": "chart", "count": len(charts)})

        await publish("agent.started", {"agent": "main_agent"})
        async with agent_span("main_agent", request.industry):
            if live:
                synthesis = await MainAgent(self.llm).synthesize(request, sections, guide, evidence)
            else:
                synthesis = SynthesisResult(
                    executive_summary=f"{request.industry}行业研究演示：方法知识已用于任务规划，行业结论仍待外部证据验证。",
                    lifecycle_stage="待证据判断", lifecycle_score=50,
                    limitations=["演示模式未获得可用于行业事实判断的材料，图表仅展示分析性评分。"],
                )
        await publish("agent.completed", {"agent": "main_agent"})
        if self.references:
            synthesis.limitations.append("引用了历史行业报告，R- 来源仅为带日期的研究参考，不能视为本次最新统计。")
            if not sources:
                synthesis.limitations.append("本次未获取新的网页证据，分析只基于历史报告参考，需补充当前行业数据。")
        report = IndustryReport(
            report_id=uuid4().hex, industry=request.industry, region=request.region,
            horizon=request.horizon, generated_at=datetime.now(timezone.utc).isoformat(),
            mode="live" if live else "demo", executive_summary=synthesis.executive_summary,
            lifecycle_stage=synthesis.lifecycle_stage, lifecycle_score=synthesis.lifecycle_score,
            plan=plan, methodology_guide=guide, knowledge_sources=knowledge_sources,
            sections=sections, charts=charts, sources=sources,
            methodology=[
                "M-方法来源只用于任务设计；S-行业来源用于事实判断。",
                "先获取方法知识并规划任务，再采集行业证据，四个专业 Agent 并行分析。",
                "分析完成后由图表 Agent 制图，主 Agent 汇总并接受质量评测。",
            ], limitations=synthesis.limitations, related_reports=self.references,
        )
        await publish("workflow.completed", {"report_id": report.report_id})
        return report
