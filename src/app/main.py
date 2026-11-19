# Main entry point for the FastAPI application, setting up routes and middleware.

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.routes import research


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize connections or any startup tasks here
    yield


app = FastAPI(title="Competitive Analysis Research Agent", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok"}


app.include_router(research.router)
