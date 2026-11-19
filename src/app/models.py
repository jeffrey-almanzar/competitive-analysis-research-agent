# Database tables. A report owns its competitors and market gaps; each competitor owns
# its sources (fetched pages), claims and price plans. Claims and prices keep the cited
# URL, the verbatim quote and the verification result, so every fact stays checkable.

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base

# JSONB on PostgreSQL, plain JSON elsewhere (SQLite in unit tests).
JSONType = JSON().with_variant(JSONB(), "postgresql")

STATUSES = ("queued", "running", "succeeded", "failed")


class ReportRow(Base):
    __tablename__ = "reports"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    idea: Mapped[str] = mapped_column(Text)
    max_competitors: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    # Latest progress event: {"step", "message", "completed", "total"}.
    progress: Mapped[dict | None] = mapped_column(JSONType)
    error: Mapped[str | None] = mapped_column(Text)
    task_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Filled in when the research succeeds.
    generated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    model: Mapped[str | None] = mapped_column(String(64))
    search_queries: Mapped[list | None] = mapped_column(JSONType)
    stats: Mapped[dict | None] = mapped_column(JSONType)
    usage: Mapped[dict | None] = mapped_column(JSONType)
    research_errors: Mapped[list | None] = mapped_column(JSONType)

    competitors: Mapped[list["CompetitorRow"]] = relationship(
        back_populates="report", cascade="all, delete-orphan", order_by="CompetitorRow.rank"
    )
    gaps: Mapped[list["MarketGapRow"]] = relationship(
        back_populates="report", cascade="all, delete-orphan", order_by="MarketGapRow.position"
    )


class CompetitorRow(Base):
    __tablename__ = "competitors"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    rank: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(Text)
    homepage_url: Mapped[str] = mapped_column(Text)
    why_competitor: Mapped[str] = mapped_column(Text)

    report: Mapped[ReportRow] = relationship(back_populates="competitors")
    sources: Mapped[list["SourceRow"]] = relationship(
        back_populates="competitor", cascade="all, delete-orphan", order_by="SourceRow.id"
    )
    claims: Mapped[list["ClaimRow"]] = relationship(
        back_populates="competitor", cascade="all, delete-orphan", order_by="ClaimRow.id"
    )
    price_plans: Mapped[list["PricePlanRow"]] = relationship(
        back_populates="competitor", cascade="all, delete-orphan", order_by="PricePlanRow.id"
    )


class SourceRow(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("competitor_id", "url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id", ondelete="CASCADE"), index=True)
    url: Mapped[str] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(16))  # site | review

    competitor: Mapped[CompetitorRow] = relationship(back_populates="sources")


class _CitedMixin:
    source_url: Mapped[str] = mapped_column(Text)
    quote: Mapped[str] = mapped_column(Text)
    verified: Mapped[bool] = mapped_column(Boolean)
    verification_note: Mapped[str] = mapped_column(Text)


class ClaimRow(_CitedMixin, Base):
    __tablename__ = "claims"

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id", ondelete="CASCADE"), index=True)
    # Null when the claim cites a page that wasn't fetched (such claims are never verified).
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    claim_key: Mapped[str] = mapped_column(String(32))  # e.g. "c2-5", referenced by gap evidence
    category: Mapped[str] = mapped_column(String(32))
    text: Mapped[str] = mapped_column(Text)

    competitor: Mapped[CompetitorRow] = relationship(back_populates="claims")


class PricePlanRow(_CitedMixin, Base):
    __tablename__ = "price_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    competitor_id: Mapped[int] = mapped_column(ForeignKey("competitors.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int | None] = mapped_column(ForeignKey("sources.id", ondelete="SET NULL"))
    plan_key: Mapped[str] = mapped_column(String(32))
    plan_name: Mapped[str] = mapped_column(Text)
    price: Mapped[str] = mapped_column(Text)

    competitor: Mapped[CompetitorRow] = relationship(back_populates="price_plans")


class MarketGapRow(Base):
    __tablename__ = "market_gaps"

    id: Mapped[int] = mapped_column(primary_key=True)
    report_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("reports.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text)
    how_to_stand_out: Mapped[str] = mapped_column(Text)
    supported: Mapped[bool] = mapped_column(Boolean)
    evidence_ids: Mapped[list] = mapped_column(JSONType)  # claim/plan keys

    report: Mapped[ReportRow] = relationship(back_populates="gaps")
