# Celery task that runs the research graph for a queued run and stores the report.

import logging
import os
import uuid

from celery import Celery
from celery.exceptions import SoftTimeLimitExceeded

from app import repository
from app.db import session_scope
from app.research.pipeline import Progress, run_research

log = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)
celery_app.conf.update(
    task_acks_late=True,  # a run interrupted by a worker crash is redelivered
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # research runs are long; take one at a time per process
    task_soft_time_limit=int(os.getenv("RESEARCH_SOFT_TIME_LIMIT_S", 15 * 60)),
    task_time_limit=int(os.getenv("RESEARCH_TIME_LIMIT_S", 16 * 60)),
)


@celery_app.task(bind=True, name="research.run")
def run_research_task(self, run_id: str) -> dict:
    rid = uuid.UUID(run_id)
    with session_scope() as s:
        row = repository.get_run(s, rid)
        if row is None:
            log.error("Run %s not found", run_id)
            return {"status": "missing"}
        if row.status == "succeeded":
            # Idempotent: a redelivered task for a finished run does nothing.
            return {"status": "succeeded"}
        repository.mark_running(s, row, self.request.id)
        idea, max_competitors, model = row.idea, row.max_competitors, row.model

    def on_progress(p: Progress) -> None:
        with session_scope() as s:
            repository.set_progress(s, rid, {"step": p.step, "message": p.message,
                                             "completed": p.completed, "total": p.total})

    try:
        report = run_research(idea, max_competitors=max_competitors, on_progress=on_progress, model=model)
    except SoftTimeLimitExceeded:
        with session_scope() as s:
            repository.mark_failed(s, rid, "Research took too long and was stopped.")
        return {"status": "failed"}
    except Exception as exc:
        log.exception("Research run %s failed", run_id)
        with session_scope() as s:
            repository.mark_failed(s, rid, f"{type(exc).__name__}: {exc}")
        return {"status": "failed"}

    with session_scope() as s:
        repository.save_report(s, rid, report)
    return {"status": "succeeded"}
