# Read/write research runs. Converts between the pipeline's Pydantic Report and the
# relational tables in app.models.

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import (
    ClaimRow,
    CompetitorRow,
    MarketGapRow,
    PricePlanRow,
    ReportRow,
    SourceRow,
)
from app.research.schemas import (
    Claim,
    CompetitorProfile,
    MarketGap,
    PricePlan,
    Report,
    ReportStats,
    RunUsage,
    Source,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_run(session: Session, idea: str, max_competitors: int) -> ReportRow:
    row = ReportRow(
        idea=idea,
        max_competitors=max_competitors,
        status="queued",
        progress={"step": "queued", "message": "Waiting for a worker", "completed": 0, "total": 0},
    )
    session.add(row)
    session.flush()
    return row


def get_run(session: Session, run_id: uuid.UUID) -> ReportRow | None:
    return session.get(ReportRow, run_id)


def list_runs(session: Session, limit: int = 20) -> list[ReportRow]:
    return list(session.scalars(select(ReportRow).order_by(ReportRow.created_at.desc()).limit(limit)))


def mark_running(session: Session, row: ReportRow, task_id: str | None) -> None:
    row.status = "running"
    row.task_id = task_id
    row.started_at = _now()
    row.error = None


def set_progress(session: Session, run_id: uuid.UUID, progress: dict) -> None:
    row = session.get(ReportRow, run_id)
    if row is not None:
        row.progress = progress


def mark_failed(session: Session, run_id: uuid.UUID, error: str) -> None:
    row = session.get(ReportRow, run_id)
    if row is not None:
        row.status = "failed"
        row.error = error
        row.finished_at = _now()
        row.progress = {**(row.progress or {}), "step": "failed", "message": "Research failed"}


def save_report(session: Session, run_id: uuid.UUID, report: Report) -> ReportRow:
    """Store a finished report on its run row, replacing any previous results."""
    row = session.get(ReportRow, run_id)
    if row is None:
        raise LookupError(f"Run {run_id} not found")

    row.competitors.clear()
    row.gaps.clear()
    session.flush()

    row.generated_at = report.generated_at
    row.model = report.model
    row.search_queries = report.search_queries
    row.stats = report.stats.model_dump()
    row.usage = report.usage.model_dump() if report.usage else None
    row.research_errors = report.errors

    for comp in report.competitors:
        comp_row = CompetitorRow(
            rank=comp.rank, name=comp.name, homepage_url=comp.homepage_url, why_competitor=comp.why_competitor
        )
        sources = {}
        for src in comp.sources:
            if src.url not in sources:  # a page can come back twice (e.g. site + review search)
                sources[src.url] = SourceRow(url=src.url, title=src.title, kind=src.kind)
        comp_row.sources = list(sources.values())
        comp_row.claims = [
            ClaimRow(
                claim_key=c.id, category=c.category, text=c.text, source_url=c.source_url, quote=c.quote,
                verified=c.verified, verification_note=c.note,
            )
            for c in comp.claims
        ]
        comp_row.price_plans = [
            PricePlanRow(
                plan_key=p.id, plan_name=p.plan_name, price=p.price, source_url=p.source_url, quote=p.quote,
                verified=p.verified, verification_note=p.note,
            )
            for p in comp.pricing
        ]
        row.competitors.append(comp_row)
        session.flush()  # assigns source ids
        by_url = {s.url: s.id for s in comp_row.sources}
        for item in [*comp_row.claims, *comp_row.price_plans]:
            item.source_id = by_url.get(item.source_url)

    row.gaps = [
        MarketGapRow(
            position=i, title=g.title, description=g.description, how_to_stand_out=g.how_to_stand_out,
            supported=g.supported, evidence_ids=g.evidence_ids,
        )
        for i, g in enumerate(report.gaps)
    ]
    row.status = "succeeded"
    row.finished_at = _now()
    row.error = None
    session.flush()
    return row


def load_report(session: Session, run_id: uuid.UUID) -> Report | None:
    """Rebuild the Pydantic Report for a succeeded run."""
    row = session.scalars(
        select(ReportRow)
        .where(ReportRow.id == run_id)
        .options(
            selectinload(ReportRow.competitors).selectinload(CompetitorRow.sources),
            selectinload(ReportRow.competitors).selectinload(CompetitorRow.claims),
            selectinload(ReportRow.competitors).selectinload(CompetitorRow.price_plans),
            selectinload(ReportRow.gaps),
        )
    ).one_or_none()
    if row is None or row.status != "succeeded":
        return None
    return Report(
        idea=row.idea,
        generated_at=row.generated_at,
        model=row.model,
        search_queries=row.search_queries or [],
        competitors=[
            CompetitorProfile(
                rank=c.rank,
                name=c.name,
                homepage_url=c.homepage_url,
                why_competitor=c.why_competitor,
                sources=[Source(url=s.url, title=s.title, kind=s.kind) for s in c.sources],
                claims=[
                    Claim(id=cl.claim_key, category=cl.category, text=cl.text, source_url=cl.source_url,
                          quote=cl.quote, verified=cl.verified, note=cl.verification_note)
                    for cl in c.claims
                ],
                pricing=[
                    PricePlan(id=p.plan_key, plan_name=p.plan_name, price=p.price, source_url=p.source_url,
                              quote=p.quote, verified=p.verified, note=p.verification_note)
                    for p in c.price_plans
                ],
            )
            for c in row.competitors
        ],
        gaps=[
            MarketGap(title=g.title, description=g.description, how_to_stand_out=g.how_to_stand_out,
                      evidence_ids=g.evidence_ids, supported=g.supported)
            for g in row.gaps
        ],
        stats=ReportStats(**row.stats),
        usage=RunUsage(**row.usage) if row.usage else None,
        errors=row.research_errors or [],
    )
