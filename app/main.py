import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .agents import IndustryResearchOrchestrator
from .benchmarks import BenchmarkRequest, load_cases, run_benchmark
from .context import MemoryInput, MemoryStore
from .rag import ReportRAG
from .config import Settings, get_settings
from .evaluation import EvaluationResult, ReportEvaluator
from .schemas import HealthResponse, IndustryReport, ReportRequest
from .security import Principal, require_scope
from .store import ReportStore
from .telemetry import configure_logging, new_trace_id

BASE_DIR = Path(__file__).resolve().parent.parent
WEB_DIR = BASE_DIR / "web"
settings = get_settings()
store = ReportStore()
evaluator = ReportEvaluator()


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging(settings)
    logging.getLogger("industry_agent").info("application.started")
    yield


app = FastAPI(
    title="行业洞察 Multi-Agent API",
    version="0.1.0",
    description="锚定来源、多 Agent 并行分析、可追踪且可评测的行业研究服务",
    lifespan=lifespan,
)
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")


@app.middleware("http")
async def trace_middleware(request: Request, call_next):
    trace_id = new_trace_id(request.headers.get("X-Trace-ID"))
    response = await call_next(request)
    response.headers["X-Trace-ID"] = trace_id
    return response


@app.get("/", include_in_schema=False)
async def index():
    return FileResponse(WEB_DIR / "index.html")


REPORT_PAGES = {
    "overview", "methodology", "lifecycle", "market", "business_model",
    "drivers_risks", "sources", "evaluation",
}


@app.get("/reports/{report_id}/{page}", include_in_schema=False)
async def report_page(report_id: str, page: str):
    if page not in REPORT_PAGES or not report_id.isalnum():
        raise HTTPException(404, "报告子页不存在")
    return FileResponse(WEB_DIR / "report.html")


@app.get("/api/health", response_model=HealthResponse)
async def health(config: Settings = Depends(get_settings)) -> HealthResponse:
    return HealthResponse(status="ok", mode="demo" if config.demo_mode else "configured", model=config.llm_model)


@app.post("/api/reports", response_model=IndustryReport)
async def create_report(
    payload: ReportRequest,
    principal: Principal = Depends(require_scope("reports:write")),
    config: Settings = Depends(get_settings),
) -> IndustryReport:
    logging.getLogger("industry_agent").info(
        "report.requested", extra={"subject": principal.subject, "industry": payload.industry}
    )
    agent = IndustryResearchOrchestrator(config)
    report = await agent.run(payload, owner=principal.subject)
    store.put(report, principal.subject, agent.last_trace)
    return report


@app.post("/api/reports/stream")
async def stream_report(
    payload: ReportRequest,
    principal: Principal = Depends(require_scope("reports:write")),
    config: Settings = Depends(get_settings),
) -> StreamingResponse:
    async def stream():
        queue: asyncio.Queue[tuple[str, dict]] = asyncio.Queue()

        async def emit(event: str, data: dict) -> None:
            await queue.put((event, data))

        async def produce() -> None:
            try:
                agent = IndustryResearchOrchestrator(config)
                report = await agent.run(payload, emit, owner=principal.subject)
                store.put(report, principal.subject, agent.last_trace)
                await queue.put(("report", report.model_dump(mode="json")))
            except Exception as exc:
                logging.getLogger("industry_agent").exception("report.failed")
                await queue.put(("error", {"message": str(exc)}))
            finally:
                await queue.put(("done", {}))

        task = asyncio.create_task(produce())
        try:
            while True:
                event, data = await queue.get()
                yield f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
                if event == "done":
                    break
        finally:
            if not task.done():
                task.cancel()

    logging.getLogger("industry_agent").info(
        "report.stream_requested", extra={"subject": principal.subject, "industry": payload.industry}
    )
    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/reports/{report_id}", response_model=IndustryReport)
async def get_report(
    report_id: str, principal: Principal = Depends(require_scope("reports:read")),
    config: Settings = Depends(get_settings),
) -> IndustryReport:
    return load_owned_report(report_id, principal.subject, config)


def load_owned_report(report_id: str, owner: str, config: Settings) -> IndustryReport:
    if store.owned(report_id, owner):
        return store.get(report_id)
    archived = ReportRAG(config).get(owner, report_id)
    if not archived:
        raise HTTPException(404, "报告不存在")
    report, trace = archived
    store.put(report, owner, trace)
    return report


@app.get("/api/reports/{report_id}/evaluation", response_model=EvaluationResult)
async def evaluate_report(
    report_id: str, principal: Principal = Depends(require_scope("evals:read")),
    config: Settings = Depends(get_settings),
) -> EvaluationResult:
    report = load_owned_report(report_id, principal.subject, config)
    return evaluator.evaluate(report)


@app.get("/api/reports/{report_id}/trace")
async def report_trace(report_id: str, principal: Principal = Depends(require_scope("evals:read")),
                       config: Settings = Depends(get_settings)):
    load_owned_report(report_id, principal.subject, config)
    return {"report_id": report_id, "trace": store.trace(report_id)}


@app.get("/api/rag/reports")
async def rag_reports(principal: Principal = Depends(require_scope("reports:read")),
                      config: Settings = Depends(get_settings)):
    return ReportRAG(config).list(principal.subject)


@app.post("/api/rag/search")
async def rag_search(payload: ReportRequest,
    principal: Principal = Depends(require_scope("reports:read")),
    config: Settings = Depends(get_settings)):
    return [ref.model_dump() for ref in ReportRAG(config).search(principal.subject, payload)]


@app.get("/api/evaluations/cases")
async def evaluation_cases(_: Principal = Depends(require_scope("evals:read"))):
    return [case.model_dump(mode="json") for case in load_cases()]


@app.post("/api/evaluations/run")
async def execute_evaluation(payload: BenchmarkRequest,
    _: Principal = Depends(require_scope("evals:write")),
    config: Settings = Depends(get_settings)):
    try:
        return await run_benchmark(config, payload)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/memory")
async def list_memory(principal: Principal = Depends(require_scope("memory:read")),
                      config: Settings = Depends(get_settings)):
    return MemoryStore(config.memory_db).list(principal.subject)


@app.post("/api/memory")
async def write_memory(payload: MemoryInput,
    principal: Principal = Depends(require_scope("memory:write")),
    config: Settings = Depends(get_settings)):
    memory_id = MemoryStore(config.memory_db).remember(
        principal.subject, payload.kind, payload.topic, payload.content, payload.provenance, payload.ttl_days)
    return {"memory_id": memory_id, "note": "历史笔记不是本次行业事实来源"}


@app.delete("/api/memory/{memory_id}")
async def delete_memory(memory_id: str,
    principal: Principal = Depends(require_scope("memory:write")),
    config: Settings = Depends(get_settings)):
    if not MemoryStore(config.memory_db).delete(principal.subject, memory_id):
        raise HTTPException(404, "记忆不存在")
    return {"deleted": memory_id}


@app.get("/api/context/{session_id}")
async def get_context(session_id: str,
    principal: Principal = Depends(require_scope("memory:read")),
    config: Settings = Depends(get_settings)):
    return {"session_id": session_id, "short_term": MemoryStore(config.memory_db).restore(principal.subject, session_id)}


@app.delete("/api/context/{session_id}")
async def clear_context(session_id: str,
    principal: Principal = Depends(require_scope("memory:write")),
    config: Settings = Depends(get_settings)):
    return {"deleted": MemoryStore(config.memory_db).clear_session(principal.subject, session_id)}
