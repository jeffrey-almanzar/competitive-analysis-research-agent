# Research API: queue a run, poll its progress, fetch the finished report.

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app import repository
from app.db import get_session
from app.models import ReportRow
from app.research import models
from app.research.render import to_markdown
from app.research.schemas import Report
from app.tasks import run_research_task

router = APIRouter(prefix="/research", tags=["research"])
models_router = APIRouter(tags=["research"])

ModelId = Literal[models.MODEL_IDS]  # type: ignore[valid-type]


class ResearchRequest(BaseModel):
    idea: str = Field(min_length=10, max_length=2000, description="What you want to build, in a sentence or two.")
    max_competitors: int = Field(6, ge=1, le=10)
    model: ModelId = Field(models.DEFAULT_MODEL, description="Claude model to run the research with.")


class ModelOut(BaseModel):
    id: str
    label: str
    capability: str
    input_per_mtok: float
    output_per_mtok: float
    est_cost_per_competitor: float
    cost_measured: bool


class ModelsOut(BaseModel):
    default: str
    models: list[ModelOut]


@models_router.get("/models", response_model=ModelsOut)
def list_models():
    """Models a research run can use, cheapest first, with capability and cost hints."""
    return {
        "default": models.DEFAULT_MODEL,
        "models": [
            {k: getattr(m, k) for k in ModelOut.model_fields}
            for m in models.MODELS
        ],
    }


class ProgressOut(BaseModel):
    step: str
    message: str
    completed: int = 0
    total: int = 0


class RunSummary(BaseModel):
    id: uuid.UUID
    idea: str
    model: str | None
    max_competitors: int
    status: Literal["queued", "running", "succeeded", "failed"]
    progress: ProgressOut | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    links: dict[str, str]


class RunDetail(RunSummary):
    report: Report | None = None


def _summary(row: ReportRow, request: Request) -> dict:
    links = {"self": str(request.url_for("get_research", run_id=row.id))}
    if row.status == "succeeded":
        links["markdown"] = str(request.url_for("get_research_markdown", run_id=row.id))
    return {
        "id": row.id, "idea": row.idea, "model": row.model, "max_competitors": row.max_competitors,
        "status": row.status, "progress": row.progress, "error": row.error,
        "created_at": row.created_at, "started_at": row.started_at, "finished_at": row.finished_at,
        "links": links,
    }


@router.post("", status_code=202, response_model=RunSummary)
def create_research(body: ResearchRequest, request: Request, session: Session = Depends(get_session)):
    row = repository.create_run(session, body.idea.strip(), body.max_competitors, body.model)
    session.commit()  # the worker must be able to see the row
    result = run_research_task.delay(str(row.id))
    row.task_id = result.id
    return _summary(row, request)


@router.get("", response_model=list[RunSummary])
def list_research(request: Request, limit: int = Query(20, ge=1, le=100), session: Session = Depends(get_session)):
    return [_summary(r, request) for r in repository.list_runs(session, limit)]


@router.get("/{run_id}", response_model=RunDetail, name="get_research")
def get_research(run_id: uuid.UUID, request: Request, session: Session = Depends(get_session)):
    row = repository.get_run(session, run_id)
    if row is None:
        raise HTTPException(404, "Research run not found")
    detail = _summary(row, request)
    if row.status == "succeeded":
        detail["report"] = repository.load_report(session, run_id)
    return detail


@router.get("/{run_id}/report.md", response_class=PlainTextResponse, name="get_research_markdown")
def get_research_markdown(run_id: uuid.UUID, session: Session = Depends(get_session)):
    row = repository.get_run(session, run_id)
    if row is None:
        raise HTTPException(404, "Research run not found")
    if row.status != "succeeded":
        raise HTTPException(409, f"Report not ready (status: {row.status})")
    report = repository.load_report(session, run_id)
    return PlainTextResponse(to_markdown(report), media_type="text/markdown; charset=utf-8")
