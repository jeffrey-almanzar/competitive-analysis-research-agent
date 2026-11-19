# MCP server exposing the research agent as tools for Claude Desktop, Claude Code, or
# any MCP client. It talks to the research HTTP API, so the API and worker must be running.
#
#   HTTP (compose service "mcp"):  http://localhost:8001/mcp
#   stdio (for clients that launch the server):
#     docker compose run --rm -T -e RESEARCH_API_URL=http://api:8000 mcp python -m app.mcp_server --stdio

import argparse
import asyncio
import functools
import os
import time
from typing import Annotated, Literal

import httpx
from pydantic import Field

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

API_URL = os.getenv("RESEARCH_API_URL", "http://localhost:8000").rstrip("/")
MAX_WAIT_S = 120

server = MCPServer(
    name="competitive-research",
    title="Competitive Research Agent",
    instructions=(
        "Researches the competitors of a business idea and returns a report in which every claim "
        "cites its source page and a verbatim quote. Start with start_research, then poll "
        "get_research (pass wait_seconds to wait for completion), then read get_report. "
        "A run takes 1-2 minutes. Each start_research call spends real API credits (~$1 per "
        "6-competitor report), so confirm with the user before starting a new run, and reuse "
        "existing runs from list_research when the idea has already been researched."
    ),
)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=API_URL, timeout=30)


def _api_errors(fn):
    """Turn HTTP/transport failures into ToolErrors whose message reaches the client."""

    @functools.wraps(fn)
    async def wrapper(*args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except ToolError:
            raise
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:300]
            raise ToolError(f"Research API returned {exc.response.status_code}: {detail}") from exc
        except httpx.TransportError as exc:
            raise ToolError(f"Research API at {API_URL} is unreachable ({type(exc).__name__}). "
                            "Is the stack running (docker compose up -d)?") from exc

    return wrapper


async def _get_run(client: httpx.AsyncClient, run_id: str) -> dict:
    r = await client.get(f"/research/{run_id}")
    if r.status_code == 404:
        raise ToolError(f"No research run with id {run_id}")
    r.raise_for_status()
    return r.json()


def _summarize(run: dict) -> dict:
    """Compact view of a run: status, progress, and (when done) the headline results."""
    out = {k: run.get(k) for k in ("id", "idea", "status", "progress", "error", "created_at", "finished_at")}
    report = run.get("report")
    if report:
        s = report["stats"]
        out["result"] = {
            "competitors": [{"rank": c["rank"], "name": c["name"], "homepage": c["homepage_url"]}
                            for c in report["competitors"]],
            "market_gaps": [g["title"] for g in report["gaps"] if g["supported"]],
            "source_check": f"{s['claims_verified']}/{s['claims_total']} claims and "
                            f"{s['prices_verified']}/{s['prices_total']} prices verified against their sources",
            "next_step": "Call get_report for the full report with citations.",
        }
    return out


@server.tool(
    title="Start competitor research",
    annotations=ToolAnnotations(readOnlyHint=False, idempotentHint=False, openWorldHint=True),
)
@_api_errors
async def start_research(
    idea: Annotated[str, Field(min_length=10, max_length=2000, description="What the user wants to build, in a sentence or two.")],
    max_competitors: Annotated[int, Field(ge=1, le=10, description="How many competitors to research.")] = 6,
) -> dict:
    """Queue a new competitor research run for a business idea. Returns a run id right away;
    the run takes 1-2 minutes. Costs real API credits, so confirm with the user first."""
    async with _client() as client:
        r = await client.post("/research", json={"idea": idea, "max_competitors": max_competitors})
        r.raise_for_status()
        return _summarize(r.json())


@server.tool(title="Get research status", annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
@_api_errors
async def get_research(
    run_id: Annotated[str, Field(description="Id returned by start_research or list_research.")],
    wait_seconds: Annotated[int, Field(ge=0, le=MAX_WAIT_S, description="Wait up to this long for the run to finish.")] = 0,
) -> dict:
    """Get a run's status and progress. When it has succeeded, also returns the competitors
    found and the evidence-backed market gaps."""
    deadline = time.monotonic() + wait_seconds
    async with _client() as client:
        while True:
            run = await _get_run(client, run_id)
            if run["status"] in ("succeeded", "failed") or time.monotonic() >= deadline:
                return _summarize(run)
            await asyncio.sleep(3)


@server.tool(title="Get research report", annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
@_api_errors
async def get_report(
    run_id: Annotated[str, Field(description="Id of a succeeded run.")],
    format: Annotated[Literal["markdown", "json"], Field(description="markdown for reading, json for the full data.")] = "markdown",
) -> str | dict:
    """Return a finished report. Every claim cites its source URL and a verbatim quote, and
    claims that couldn't be verified are listed separately as flagged."""
    async with _client() as client:
        if format == "json":
            run = await _get_run(client, run_id)
            if run["status"] != "succeeded":
                raise ToolError(f"Report not ready (status: {run['status']})")
            return run["report"]
        r = await client.get(f"/research/{run_id}/report.md")
        if r.status_code == 404:
            raise ToolError(f"No research run with id {run_id}")
        if r.status_code == 409:
            raise ToolError(r.json().get("detail", "Report not ready"))
        r.raise_for_status()
        return r.text


@server.tool(title="List research runs", annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
@_api_errors
async def list_research(
    limit: Annotated[int, Field(ge=1, le=100)] = 20,
) -> list[dict]:
    """List recent research runs (newest first) with their ids, ideas and status."""
    async with _client() as client:
        r = await client.get("/research", params={"limit": limit})
        r.raise_for_status()
        return [{k: run[k] for k in ("id", "idea", "status", "created_at")} for run in r.json()]


@server.tool(title="List competitors", annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False))
@_api_errors
async def list_competitors(
    run_id: Annotated[str, Field(description="Id of a succeeded run.")],
) -> list[dict]:
    """List the competitors in a finished report with their verified pricing and the number of
    verified and flagged claims for each."""
    async with _client() as client:
        run = await _get_run(client, run_id)
    if run["status"] != "succeeded":
        raise ToolError(f"Report not ready (status: {run['status']})")
    return [
        {
            "rank": c["rank"],
            "name": c["name"],
            "homepage": c["homepage_url"],
            "why_competitor": c["why_competitor"],
            "pricing": [{"plan": p["plan_name"], "price": p["price"], "source": p["source_url"]}
                        for p in c["pricing"] if p["verified"]],
            "verified_claims": sum(cl["verified"] for cl in c["claims"]),
            "flagged_claims": sum(not cl["verified"] for cl in c["claims"]),
        }
        for c in run["report"]["competitors"]
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Competitive research MCP server")
    parser.add_argument("--stdio", action="store_true", help="Serve over stdio instead of HTTP")
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", "8001")))
    args = parser.parse_args()
    if args.stdio:
        server.run("stdio")
    else:
        server.run("streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()
