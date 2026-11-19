# MCP tools tested end to end against the real FastAPI app (in-process, SQLite), with the
# Celery queue faked so start_research never starts a paid research run.

import asyncio
import json

import httpx
import pytest

from mcp.server.mcpserver.exceptions import ToolError

from app import mcp_server, tasks
from tests.test_pipeline import _patch


@pytest.fixture
def api(monkeypatch, sqlite_db):
    from app.main import app
    from app.routes import research as routes

    queued = []
    monkeypatch.setattr(routes.run_research_task, "delay",
                        lambda run_id: queued.append(run_id) or type("R", (), {"id": "t"})())
    monkeypatch.setattr(mcp_server, "_client", lambda: httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://api"))
    return queued


def call(name, args):
    # In-process call_tool raises ToolError; over the protocol it becomes an isError result.
    try:
        result = asyncio.run(mcp_server.server.call_tool(name, args))
    except ToolError as exc:
        return {"error": str(exc)}
    if result.is_error:
        return {"error": result.content[0].text}
    if result.structured_content is not None:
        data = result.structured_content
        return data.get("result", data)
    text = result.content[0].text
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def test_tools_are_listed_with_correct_hints():
    tools = {t.name: t for t in asyncio.run(mcp_server.server.list_tools())}
    assert set(tools) == {"start_research", "get_research", "get_report", "list_research", "list_competitors"}
    assert tools["start_research"].annotations.read_only_hint is False
    assert all(tools[n].annotations.read_only_hint for n in tools if n != "start_research")
    assert "Costs real API credits" in tools["start_research"].description


def test_full_flow_through_mcp(api, monkeypatch):
    started = call("start_research", {"idea": "AI meeting notes for small law firms", "max_competitors": 3})
    assert started["status"] == "queued" and api == [started["id"]]
    rid = started["id"]

    assert "not ready" in call("get_report", {"run_id": rid})["error"]
    assert "not ready" in call("list_competitors", {"run_id": rid})["error"]

    _patch(monkeypatch)  # simulate the worker with faked Claude/Exa
    tasks.run_research_task(rid)

    status = call("get_research", {"run_id": rid})
    assert status["status"] == "succeeded"
    assert [c["name"] for c in status["result"]["competitors"]] == ["Acme", "Beta"]
    assert status["result"]["market_gaps"] == ["Reliable mobile capture"]

    comps = call("list_competitors", {"run_id": rid})
    assert comps[0]["pricing"] == [{"plan": "Pro", "price": "$30/user/month", "source": "https://acme.com/pricing"}]
    assert (comps[0]["verified_claims"], comps[0]["flagged_claims"]) == (2, 2)

    md = call("get_report", {"run_id": rid})
    assert md.startswith("# Competitive analysis")
    assert call("get_report", {"run_id": rid, "format": "json"})["idea"].startswith("AI meeting notes")
    assert [r["id"] for r in call("list_research", {})] == [rid]


def test_errors_reach_the_client(api, monkeypatch):
    missing = call("get_research", {"run_id": "00000000-0000-0000-0000-000000000000"})
    assert "No research run with id" in missing["error"]
    assert "error" in call("start_research", {"idea": "short"})  # validation

    monkeypatch.setattr(mcp_server, "_client", lambda: httpx.AsyncClient(base_url="http://127.0.0.1:9"))
    assert "unreachable" in call("list_research", {})["error"]
