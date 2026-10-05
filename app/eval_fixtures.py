"""Synthetic offline adapters. These test orchestration, NOT real model capability."""

import asyncio
from datetime import datetime, timezone

from .agents import _demo_plan
from .methodology import CATALOG, catalog_guide
from .schemas import Finding, Metric, Section, SourceDocument, SynthesisResult, ResearchPlan, MethodologyGuide
from .telemetry import record_event

TEXT = {
    "lifecycle": "行业处于试点向商业化验证阶段，采用程度和技术成熟度仍需进一步验证。",
    "market": "竞争分析必须统一行业分类与口径；来源存在冲突时不得合并不可比市场数据。",
    "business_model": "产业链包括零部件、设备与系统集成；区分客户与付费者。企业SaaS收入依赖订阅、续费与获客成本。",
    "drivers_risks": "监管风险包括适航和许可，技术替代和融资也可能影响商业化。",
}


class FixtureCollector:
    async def fetch_urls(self, urls):
        return []

    async def collect(self, request):
        if request.industry == "未知新兴产业":
            return []
        now = datetime.now(timezone.utc).isoformat()
        sources = [SourceDocument(
            id="S-fixture", title="SYNTHETIC TEST DOCUMENT — NOT REAL INDUSTRY DATA",
            url="https://example.com/fixture", domain="example.com",
            excerpt="\n".join(TEXT.values()) + "\n合成指标：测试指标=12 测试单位。", retrieved_at=now,
        )]
        if request.industry == "动力电池":
            sources[0].excerpt += "\n合成口径 A：只计电芯出厂价值，不能与下游系统交付价值混算。"
            sources.append(SourceDocument(
                id="S-fixture-alt", title="SYNTHETIC CONFLICTING MEASUREMENT",
                url="https://example.com/fixture-alt", domain="example.com",
                excerpt="合成口径 B：包含电芯及系统集成服务，不能直接对比口径 A。",
                retrieved_at=now,
            ))
        return sources


class FixtureLLM:
    def __init__(self, request):
        self.request = request

    async def generate(self, system, prompt, schema):
        record_event("llm.started", schema=schema.__name__, fixture=True)
        await asyncio.sleep(0.005)  # Yield so actual overlap can be measured in spans.
        guide = catalog_guide(self.request, CATALOG)
        if schema is MethodologyGuide:
            result = guide
        elif schema is ResearchPlan:
            result = _demo_plan(self.request, guide)
        elif schema is Section:
            key = next(key for key in TEXT if f"Section.key MUST be {key}" in prompt)
            result = Section(
                key=key, title=key, executive_takeaway=TEXT[key],
                findings=[Finding(title="合成测试结论", summary=TEXT[key], evidence=["S-fixture"])],
                metrics=[Metric(name="测试指标", value=12, unit="测试单位", source_ids=["S-fixture"])],
                recommendations=["复核原始来源并补充证据。"],
            )
        elif schema is SynthesisResult:
            result = SynthesisResult(
                executive_summary="合成回归报告，仅用于测试编排，不是真实行业分析。",
                lifecycle_stage="验证阶段", lifecycle_score=40,
                limitations=["合成测试来源，不可用于实际决策；数据口径冲突需要核查。"],
            )
        else:
            raise ValueError(f"Unsupported fixture schema {schema}")
        record_event("llm.completed", schema=schema.__name__, fixture=True)
        return result
