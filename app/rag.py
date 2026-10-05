"""Persistent report archive + relation-aware lexical chunk retrieval (no embedding API)."""

import hashlib
import json
import re
import sqlite3
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from .config import Settings
from .schemas import IndustryReport, ReportReference, ReportRequest

# Explicit, auditable relation hints, not a claim of learned semantic embeddings.
RELATIONS = {
    "计算机": {"芯片", "半导体", "人工智能", "云计算", "软件"},
    "芯片": {"计算机", "半导体", "人工智能", "智能手机", "汽车电子"},
    "动力电池": {"新能源汽车", "储能", "锂矿"},
    "工业机器人": {"制造业", "工业自动化", "机械", "人工智能"},
    "企业saas": {"软件", "云计算", "计算机"},
}


def normalize(text: str) -> str:
    return re.sub(r"[\s\W_]+", "", unicodedata.normalize("NFKC", text).casefold())


def industry_key(text: str) -> str:
    return re.sub(r"(行业|产业)$", "", normalize(text))


def tokens(text: str) -> set[str]:
    words = set(re.findall(r"[a-z0-9]{2,}", text.casefold()))
    chinese = re.findall(r"[\u4e00-\u9fff]+", text)
    for word in chinese:
        words.update(word[i:i + 2] for i in range(max(1, len(word) - 1)))
    return words


class ReportRAG:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.path = settings.rag_db
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS reports (
                id TEXT PRIMARY KEY, owner TEXT NOT NULL, fingerprint TEXT NOT NULL,
                industry TEXT NOT NULL, region TEXT NOT NULL, generated REAL NOT NULL,
                mode TEXT NOT NULL, report TEXT NOT NULL, trace TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS report_lookup ON reports(owner,fingerprint,generated)")
            db.execute("""CREATE TABLE IF NOT EXISTS chunks (
                id TEXT PRIMARY KEY, report_id TEXT NOT NULL, owner TEXT NOT NULL,
                section_key TEXT NOT NULL, content TEXT NOT NULL)""")
            db.execute("CREATE INDEX IF NOT EXISTS chunk_owner ON chunks(owner,report_id)")

    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    def fingerprint(self, request: ReportRequest) -> str:
        anchors = request.anchor_sites or self.settings.anchor_domain_list
        # Different questions/anchors must not silently reuse an unrelated answer.
        scope = [industry_key(request.industry), normalize(request.region),
                 normalize(request.horizon), normalize(request.question), sorted(set(anchors))]
        return hashlib.sha256(json.dumps(scope, ensure_ascii=False).encode()).hexdigest()

    def save(self, owner: str, request: ReportRequest, report: IndustryReport, trace: list[dict]) -> None:
        if any(item.get("fixture") for item in trace):
            return
        stamp = datetime.fromisoformat(report.generated_at).timestamp()
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO reports VALUES (?,?,?,?,?,?,?,?,?)", (
                report.report_id, owner, self.fingerprint(request), industry_key(report.industry),
                normalize(report.region), stamp, report.mode,
                report.model_dump_json(), json.dumps(trace, ensure_ascii=False),
            ))
            db.execute("DELETE FROM chunks WHERE report_id=? AND owner=?", (report.report_id, owner))
            # Store demo reports for inspection/cache, but never use them as RAG evidence.
            if report.mode == "live" and (report.sources or report.related_reports) and not any(item.get("fixture") for item in trace):
                valid = {source.id for source in report.sources} | {ref.id for ref in report.related_reports}
                for section in report.sections:
                    supported = [finding for finding in section.findings
                                 if finding.evidence and set(finding.evidence).issubset(valid)]
                    if not supported:
                        continue
                    text = section.title + "\n" + "\n".join(finding.summary for finding in supported)
                    for offset in range(0, min(len(text), 12000), 1800):
                        chunk_id = f"R-{report.report_id}-{section.key}-{offset // 1800}"
                        db.execute("INSERT INTO chunks VALUES (?,?,?,?,?)", (
                            chunk_id, report.report_id, owner, section.key, text[offset:offset + 1800]))

    def cached(self, owner: str, request: ReportRequest, allow_demo: bool = False) -> IndustryReport | None:
        with self.connect() as db:
            row = db.execute("""SELECT report FROM reports WHERE owner=? AND fingerprint=?
                AND generated>? AND (mode='live' OR ?)
                ORDER BY (mode='live') DESC, generated DESC LIMIT 1""", (
                owner, self.fingerprint(request), time.time() - self.settings.rag_max_age_days * 86400,
                int(allow_demo),
            )).fetchone()
        if not row:
            return None
        report = IndustryReport.model_validate_json(row["report"])
        cutoff = time.time() - self.settings.rag_max_age_days * 86400
        if any(datetime.fromisoformat(ref.generated_at).timestamp() < cutoff for ref in report.related_reports):
            return None
        return report

    def get(self, owner: str, report_id: str) -> tuple[IndustryReport, list[dict]] | None:
        with self.connect() as db:
            row = db.execute("SELECT report,trace FROM reports WHERE owner=? AND id=?", (owner, report_id)).fetchone()
        return (IndustryReport.model_validate_json(row["report"]), json.loads(row["trace"])) if row else None

    def list(self, owner: str) -> list[dict]:
        with self.connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,industry,region,generated,mode FROM reports WHERE owner=? ORDER BY generated DESC LIMIT 100", (owner,))]

    def search(self, owner: str, request: ReportRequest) -> list[ReportReference]:
        query = industry_key(request.industry)
        query_tokens = tokens(request.industry + " " + request.question)
        industry_tokens = tokens(query)
        with self.connect() as db:
            rows = db.execute("""SELECT c.*,r.industry,r.region,r.generated,r.report FROM chunks c
                JOIN reports r ON c.report_id=r.id AND c.owner=r.owner
                WHERE c.owner=? AND r.mode='live' AND r.generated>? AND r.region=?
                ORDER BY r.generated DESC LIMIT 1000""", (
                owner, time.time() - self.settings.rag_max_age_days * 86400, normalize(request.region),
            )).fetchall()
        ranked = []
        for row in rows:
            industry = row["industry"]
            related = industry in RELATIONS.get(query, set()) or query in RELATIONS.get(industry, set())
            content_tokens = tokens(row["content"])
            if industry != query and not related and not (industry_tokens & content_tokens):
                continue
            lex = len(query_tokens & content_tokens) / max(1, len(query_tokens))
            score = (0.7 if industry == query else 0.5 if related else 0) + 0.3 * lex
            if score < 0.18:
                continue
            report = IndustryReport.model_validate_json(row["report"])
            if any(datetime.fromisoformat(ref.generated_at).timestamp() < time.time() - self.settings.rag_max_age_days * 86400 for ref in report.related_reports):
                continue
            provenance = list(dict.fromkeys(
                [source.url for source in report.sources] +
                [url for ref in report.related_reports for url in ref.source_urls]))
            ranked.append(ReportReference(
                id=row["id"], report_id=report.report_id, industry=report.industry,
                region=report.region, generated_at=report.generated_at, section_key=row["section_key"],
                excerpt=row["content"], source_urls=provenance,
                score=round(score, 4),
            ))
        ranked.sort(key=lambda item: item.score, reverse=True)
        # Diversify: avoid letting a single report consume the whole context budget.
        selected, counts = [], {}
        for item in ranked:
            if counts.get(item.report_id, 0) >= 2:
                continue
            selected.append(item)
            counts[item.report_id] = counts.get(item.report_id, 0) + 1
            if len(selected) == self.settings.rag_top_k:
                break
        return selected
