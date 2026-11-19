# Celery tasks for conducting research asynchronously.

import os

from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)


@celery_app.task
def start_research(query: str):
    # TODO: Conduct research using Claude API and Exa Web Search
    # TODO: Save results to PostgreSQL
    return {"status": "completed", "query": query}
