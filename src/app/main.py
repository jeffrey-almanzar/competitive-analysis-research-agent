# Main entry point for the FastAPI application.

import redis
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import engine
from app.routes import research
from app.tasks import REDIS_URL

app = FastAPI(title="Competitive Analysis Research Agent")


@app.get("/health")
def health():
    checks = {}
    try:
        with engine().connect() as conn:
            conn.execute(text("select 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {type(exc).__name__}"
    try:
        redis.Redis.from_url(REDIS_URL, socket_timeout=2).ping()
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {type(exc).__name__}"
    healthy = all(v == "ok" for v in checks.values())
    return JSONResponse({"status": "ok" if healthy else "degraded", **checks}, status_code=200 if healthy else 503)


app.include_router(research.router)
