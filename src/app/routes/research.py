# Defines API endpoints related to competitive research.

from fastapi import APIRouter
from pydantic import BaseModel

from app.tasks import celery_app, start_research

router = APIRouter()


class ResearchRequest(BaseModel):
    query: str


@router.post("/research")
async def initiate_research(request: ResearchRequest):
    task = start_research.delay(request.query)
    return {"task_id": task.id}


@router.get("/research/{task_id}")
async def get_research(task_id: str):
    result = celery_app.AsyncResult(task_id)
    return {
        "task_id": task_id,
        "status": result.status,
        "result": result.result if result.ready() else None,
    }
