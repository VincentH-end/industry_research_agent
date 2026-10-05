from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ReportRequest(BaseModel):
    industry: str = Field(min_length=2, max_length=80, examples=["低空经济"])
    region: str = Field(default="中国", min_length=1, max_length=50)
    horizon: str = Field(default="未来3-5年", max_length=50)
    anchor_sites: list[str] = Field(default_factory=list, max_length=10)
    question: str = Field(default="", max_length=1000)
    session_id: str | None = Field(default=None, min_length=1, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    use_memory: bool = True
    use_rag: bool = True
    force_refresh: bool = False

    @field_validator("industry", "region", "horizon")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()


class SourceDocument(BaseModel):
    id: str
    title: str
    url: str
    domain: str
    excerpt: str
    published_at: str | None = None
    retrieved_at: str


class Metric(BaseModel):
    name: str
    value: float
    unit: str = ""
    period: str = ""
    source_ids: list[str] = Field(default_factory=list)
    is_estimate: bool = False


class Finding(BaseModel):
    title: str
    summary: str
    evidence: list[str] = Field(default_factory=list)
    confidence: Literal["high", "medium", "low"] = "medium"


class Section(BaseModel):
    key: str
    title: str
    executive_takeaway: str
    findings: list[Finding]
    metrics: list[Metric] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class ChartSpec(BaseModel):
    id: str
    section_key: str
    title: str
    note: str = ""
    option: dict


class ResearchPlan(BaseModel):
    industry_definition: str
    value_chain: list[str]
    hypotheses: list[str]
    tasks: list[str]
    evidence_gaps: list[str]
    task_specs: list["TaskSpec"] = Field(default_factory=list)


class TaskSpec(BaseModel):
    key: str
    objective: str
    method_ids: list[str] = Field(default_factory=list)
    evidence_needed: list[str] = Field(default_factory=list)
    depends_on: list[str] = Field(default_factory=list)


class KnowledgeSource(BaseModel):
    id: str
    title: str
    url: str
    source_type: Literal["book_or_article", "manual", "data_method", "survey_method"]
    usage: str
    acquisition: Literal["catalog", "retrieved"] = "catalog"
    excerpt: str = ""


class MethodPrinciple(BaseModel):
    name: str
    instruction: str
    method_ids: list[str] = Field(default_factory=list)


class MethodologyGuide(BaseModel):
    objective: str
    principles: list[MethodPrinciple]
    workflow: list[str]
    source_ids: list[str]
    limitations: list[str] = Field(default_factory=list)


class IndustryReport(BaseModel):
    report_id: str
    industry: str
    region: str
    horizon: str
    generated_at: str
    mode: Literal["live", "demo"]
    executive_summary: str
    lifecycle_stage: str
    lifecycle_score: float = Field(ge=0, le=100)
    plan: ResearchPlan
    methodology_guide: MethodologyGuide | None = None
    knowledge_sources: list[KnowledgeSource] = Field(default_factory=list)
    sections: list[Section]
    charts: list[ChartSpec]
    sources: list[SourceDocument]
    methodology: list[str]
    limitations: list[str]
    session_id: str | None = None
    trace_id: str | None = None
    reused: bool = False
    origin_trace_id: str | None = None
    related_reports: list["ReportReference"] = Field(default_factory=list)


class ReportReference(BaseModel):
    id: str
    report_id: str
    industry: str
    region: str
    generated_at: str
    section_key: str
    excerpt: str
    source_urls: list[str]
    score: float


class HealthResponse(BaseModel):
    status: str
    mode: str
    model: str


class SynthesisResult(BaseModel):
    executive_summary: str
    lifecycle_stage: str
    lifecycle_score: float = Field(ge=0, le=100)
    limitations: list[str]
