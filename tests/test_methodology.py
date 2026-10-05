from app.agents import _demo_plan, _demo_sections, _validate_industry_citations
from app.methodology import KnowledgeAcquisitionAgent
from app.config import Settings
from app.llm import StructuredLLM
from app.schemas import ReportRequest
from app.sources import SourceCollector


async def test_methodology_catalog_guides_demo_tasks():
    settings = Settings(llm_api_key="")
    request = ReportRequest(industry="工业机器人")
    sources, guide = await KnowledgeAcquisitionAgent(
        settings, SourceCollector(settings), StructuredLLM(settings)
    ).run(request)
    assert all(item.id.startswith("M") for item in sources)
    assert all(item.acquisition == "catalog" for item in sources)
    plan = _demo_plan(request, guide)
    assert {task.key for task in plan.task_specs} == {
        "lifecycle", "market", "business_model", "drivers_risks"
    }
    assert all(task.method_ids for task in plan.task_specs)


def test_method_source_cannot_validate_industry_claim():
    sections = _demo_sections(ReportRequest(industry="工业机器人"))
    sections[0].findings[0].evidence = ["M1"]
    sections[0].findings[0].summary = "unsupported claim"
    _validate_industry_citations(sections, [])
    assert sections[0].findings[0].evidence == []
    assert "隐藏" in sections[0].findings[0].summary
