"""Methodology knowledge is separate from industry-specific factual evidence."""

import httpx

from .config import Settings
from .llm import StructuredLLM
from .schemas import KnowledgeSource, MethodologyGuide, MethodPrinciple, ReportRequest
from .sources import SourceCollector

# Editorial summaries of publicly identified primary sources. No book text is copied.
CATALOG = [
    KnowledgeSource(
        id="M1",
        title="The Five Competitive Forces That Shape Strategy — Michael E. Porter (2008)",
        url="https://hbr.org/2008/01/the-five-competitive-forces-that-shape-strategy",
        source_type="book_or_article",
        usage="Use five-forces questions to map rivalry, entrants, substitutes, buyers and suppliers.",
    ),
    KnowledgeSource(
        id="M2",
        title="Oslo Manual 2018 — OECD/Eurostat",
        url="https://www.oecd.org/en/publications/oslo-manual-2018_9789264304604-en.html",
        source_type="manual",
        usage="Define innovation and adoption indicators before judging technology maturity.",
    ),
    KnowledgeSource(
        id="M3",
        title="Structural Analysis Database (STAN) — OECD",
        url="https://www.oecd.org/en/data/datasets/structural-analysis-database.html",
        source_type="data_method",
        usage="Harmonise industry classification, output, value added, labour and productivity comparisons.",
    ),
    KnowledgeSource(
        id="M4",
        title="Enterprise Surveys — World Bank",
        url="https://microdata.worldbank.org/collections/enterprise_surveys",
        source_type="survey_method",
        usage="Use firm-level evidence for competition, finance, infrastructure and performance questions.",
    ),
]


def catalog_guide(request: ReportRequest, sources: list[KnowledgeSource]) -> MethodologyGuide:
    available = {item.id for item in sources}
    principles = [
        MethodPrinciple(
            name="先界定行业口径",
            instruction="定义产品、客户、地区、分类代码和统计周期，再比较市场数据。",
            method_ids=["M3"] if "M3" in available else [],
        ),
        MethodPrinciple(
            name="竞争结构不等于竞品名单",
            instruction="分别调查现有竞争、潜在进入、替代品、买方和供应方议价能力。",
            method_ids=["M1"] if "M1" in available else [],
        ),
        MethodPrinciple(
            name="技术成熟度须有观测指标",
            instruction="区分发明、实际应用和扩散；寻找采用率、标准化和企业创新证据。",
            method_ids=["M2"] if "M2" in available else [],
        ),
        MethodPrinciple(
            name="商业模式须回到企业层面",
            instruction="核查客户、付费者、成本、利润、融资约束及企业经营表现。",
            method_ids=["M4"] if "M4" in available else [],
        ),
    ]
    return MethodologyGuide(
        objective=f"为{request.region}{request.industry}研究设计可复核的任务与证据标准",
        principles=principles,
        workflow=[
            "方法知识获取与适用性筛选",
            "界定行业边界、指标口径和待验证假设",
            "采集具体行业事实并登记来源",
            "并行分析生命周期、市场竞争、商业模式、驱动与风险",
            "根据已验证指标制图、主 Agent 汇总并质量评测",
        ],
        source_ids=[item.id for item in sources],
        limitations=["目录摘要仅用于方法规划；具体行业事实必须另找 S- 来源。"],
    )


class KnowledgeAcquisitionAgent:
    """Acquire method sources before any industry research or task planning."""

    def __init__(self, settings: Settings, collector: SourceCollector, llm: StructuredLLM) -> None:
        self.settings = settings
        self.collector = collector
        self.llm = llm

    async def run(self, request: ReportRequest) -> tuple[list[KnowledgeSource], MethodologyGuide]:
        sources = [item.model_copy(deep=True) for item in CATALOG]
        if self.settings.llm_api_key:
            urls = [item.url for item in sources] + self.settings.methodology_url_list
            fetched = {item.url: item for item in await self.collector.fetch_urls(urls)}
            if self.settings.tavily_api_key:
                allowed = ["oecd.org", "worldbank.org", "hbr.org"]
                try:
                    async with httpx.AsyncClient(timeout=self.settings.request_timeout_seconds) as client:
                        response = await client.post("https://api.tavily.com/search", json={
                            "api_key": self.settings.tavily_api_key,
                            "query": f"{request.industry} industry analysis methodology market definition value chain competitive structure report methods",
                            "include_domains": allowed, "max_results": 3,
                        })
                        response.raise_for_status()
                        discovered = [item.get("url", "") for item in response.json().get("results", [])]
                    extras = await self.collector.fetch_urls(discovered)
                    fetched.update({item.url: item for item in extras})
                    urls += discovered
                except httpx.HTTPError:
                    pass  # The audited catalog remains available when discovery fails.
            for item in sources:
                if item.url in fetched:
                    item.acquisition = "retrieved"
                    item.excerpt = fetched[item.url].excerpt[:4000]
            known = {item.url for item in sources}
            for url in dict.fromkeys(urls):
                if url in fetched and url not in known:
                    doc = fetched[url]
                    sources.append(
                        KnowledgeSource(
                            id=f"M{len(sources)+1}", title=doc.title, url=url,
                            source_type="book_or_article", usage="Additional user-configured research method",
                            acquisition="retrieved", excerpt=doc.excerpt[:4000],
                        )
                    )
        if not self.settings.llm_api_key:
            return sources, catalog_guide(request, sources)

        evidence = "\n".join(
            f"[{item.id}] {item.title}; purpose={item.usage}; status={item.acquisition}; "
            f"excerpt={item.excerpt[:2500]}" for item in sources
        )
        guide = await self.llm.generate(
            "You design industry research workflows. Use only the method sources provided. "
            "Method sources guide tasks; they are not evidence of facts about the named industry. "
            "Return JSON matching the schema and cite only existing M ids.",
            f"Design a research methodology for {request.region} / {request.industry} / {request.horizon}. "
            f"Cover scope, lifecycle, competition, business model, risk, evidence standards and dependencies.\n{evidence}",
            MethodologyGuide,
        )
        valid = {item.id for item in sources}
        for principle in guide.principles:
            principle.method_ids = [item for item in principle.method_ids if item in valid]
        guide.principles = [item for item in guide.principles if item.method_ids]
        if not guide.principles:
            return sources, catalog_guide(request, sources)
        guide.source_ids = list(dict.fromkeys(
            method_id for principle in guide.principles for method_id in principle.method_ids
        ))
        return sources, guide
