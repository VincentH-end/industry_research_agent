import contextvars
import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import AsyncIterator

from .config import Settings

trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("trace_id", default="-")
recorder_var: contextvars.ContextVar["TraceRecorder | None"] = contextvars.ContextVar("trace_recorder", default=None)


class TraceRecorder:
    """The same span data feeds JSON logs and reproducible trajectory evaluation."""

    def __init__(self, trace_id: str) -> None:
        self.trace_id = trace_id
        self.started = time.perf_counter()
        self.records: list[dict] = []

    def add(self, event: str, **data) -> None:
        record = {
            "trace_id": self.trace_id, "event": event,
            "elapsed_ms": round((time.perf_counter() - self.started) * 1000, 3), **data,
        }
        self.records.append(record)


def record_event(event: str, **data) -> None:
    recorder = recorder_var.get()
    if recorder:
        recorder.add(event, **data)


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "trace_id": trace_id_var.get(),
            "message": record.getMessage(),
        }
        for key in ("agent", "duration_ms", "status", "subject", "industry", "span_id"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(settings: Settings) -> None:
    logger = logging.getLogger("industry_agent")
    if logger.handlers:
        return
    logger.setLevel(settings.log_level.upper())
    formatter = JsonFormatter()
    stream = logging.StreamHandler()
    stream.setFormatter(formatter)
    logger.addHandler(stream)
    if settings.log_file:
        path = Path(settings.log_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
        handler.setFormatter(formatter)
        logger.addHandler(handler)


def new_trace_id(value: str | None = None) -> str:
    trace_id = value or uuid.uuid4().hex
    trace_id_var.set(trace_id)
    return trace_id


@asynccontextmanager
async def agent_span(name: str, industry: str) -> AsyncIterator[None]:
    logger = logging.getLogger("industry_agent")
    started = time.perf_counter()
    span_id = uuid.uuid4().hex
    record_event("span.started", agent=name, span_id=span_id)
    status_value = "ok"
    try:
        yield
    except BaseException:
        status_value = "error"
        raise
    finally:
        duration = round((time.perf_counter() - started) * 1000, 2)
        record_event("span.completed", agent=name, span_id=span_id, duration_ms=duration, status=status_value)
        logger.info(
            "agent.completed",
            extra={
                "agent": name,
                "duration_ms": duration,
                "span_id": span_id,
                "status": status_value,
                "industry": industry,
            },
        )
