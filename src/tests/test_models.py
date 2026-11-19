# Model selection: registry, per-run model through the graph, API, worker, MCP and cost.

import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app import repository, tasks
from app.db import session_scope
from app.research import llm, models, pipeline, telemetry
from evals import grading
from tests.test_pipeline import IDEA, _patch, fake_structured


def test_registry_is_cheapest_first_and_default_is_cheapest():
    costs = [m.est_cost_per_competitor for m in models.MODELS]
    assert costs == sorted(costs)
    assert models.DEFAULT_MODEL == "claude-haiku-5-5"
    assert [m.id for m in models.MODELS] == ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5"]
    with pytest.raises(ValueError):
        models.get("claude-nonexistent")


def test_run_model_reaches_every_claude_call_in_the_graph(monkeypatch):
    _patch(monkeypatch)
    seen = []

    def recording_fake(system, prompt, schema, **kw):
        seen.append(llm.current_model())  # read inside LangGraph worker threads
        return fake_structured(system, prompt, schema, **kw)

    monkeypatch.setattr(pipeline.llm, "structured", recording_fake)
    report = pipeline.run_research(IDEA, model="claude-sonnet-5-5")
    assert report.model == "claude-sonnet-5-5"
    assert len(seen) >= 4 and set(seen) == {"claude-sonnet-5-5"}
    assert llm.current_model() == llm.MODEL  # reset after the run

    with pytest.raises(ValueError):
        pipeline.run_research(IDEA, model="gpt-4")


class _FakeMessages:
    def __init__(self):
        self.kwargs = None

    def parse(self, **kwargs):
        self.kwargs = kwargs
        usage = type("U", (), {"input_tokens": 10, "output_tokens": 5,
                               "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0})()
        return type("R", (), {"usage": usage, "model": kwargs["model"], "stop_reason": "end_turn",
                              "stop_details": None, "_request_id": "req_test",
                              "parsed_output": kwargs["output_format"](queries=["q"])})()


@pytest.mark.parametrize("model,expect_fallback", [
    ("claude-haiku-5-5", False),
    ("claude-sonnet-5-5", True),
    ("claude-opus-5-5", True),
])
def test_fallback_parameter_only_sent_where_supported(monkeypatch, model, expect_fallback):
    fake = _FakeMessages()
    client = type("C", (), {"beta": type("B", (), {"messages": fake})()})()
    monkeypatch.setattr(llm, "_client", lambda: client)
    with llm.use_model(model):
        llm.structured("sys", "prompt", pipeline.SearchPlan)
    assert fake.kwargs["model"] == model
    assert ("fallbacks" in fake.kwargs) is expect_fallback
    assert ("betas" in fake.kwargs) is expect_fallback


def test_api_model_default_validation_and_listing(monkeypatch, sqlite_db):
    from app.main import app
    from app.routes import research as routes

    monkeypatch.setattr(routes.run_research_task, "delay", lambda run_id: type("R", (), {"id": "t"})())
    client = TestClient(app)

    listing = client.get("/models").json()
    assert listing["default"] == "claude-haiku-5-5"
    assert [m["id"] for m in listing["models"]] == list(models.MODEL_IDS)
    assert all(m["capability"] and m["est_cost_per_competitor"] > 0 for m in listing["models"])
    assert [m["cost_measured"] for m in listing["models"]] == [False, False, True]

    default = client.post("/research", json={"idea": "AI meeting notes for small law firms"}).json()
    assert default["model"] == "claude-haiku-5-5"
    chosen = client.post("/research", json={"idea": "AI meeting notes for small law firms",
                                            "model": "claude-opus-5-5"}).json()
    assert chosen["model"] == "claude-opus-5-5"
    assert client.post("/research", json={"idea": "AI meeting notes for small law firms",
                                          "model": "gpt-4"}).status_code == 422
    assert {r["model"] for r in client.get("/research").json()} == {"claude-haiku-5-5", "claude-opus-5-5"}


def test_worker_runs_the_stored_model(monkeypatch, sqlite_db):
    seen = {}
    monkeypatch.setattr(tasks, "run_research", lambda idea, **kw: seen.update(kw) or (_ for _ in ()).throw(RuntimeError("stop")))
    with session_scope() as s:
        run_id = repository.create_run(s, IDEA, 4, "claude-sonnet-5-5").id
    tasks.run_research_task(str(run_id))
    assert seen["model"] == "claude-sonnet-5-5" and seen["max_competitors"] == 4


def test_haiku_long_prompts_bill_at_the_higher_rate():
    short = telemetry.LLMCall("x", "claude-haiku-5-5", "", "", None, 100_000, 1_000_000, 0, 0, 0, None)
    long = telemetry.LLMCall("x", "claude-haiku-5-5", "", "", None, 100_001, 1_000_000, 0, 0, 0, None)
    assert grading.cost_usd([short]) == round(0.1 * 0.1 + 0.5, 4)        # $0.10 / $0.50 per MTok
    assert grading.cost_usd([long]) == round(0.100001 * 0.5 + 2.5, 4)    # $0.50 / $2.50 per MTok


def test_mcp_start_research_sends_model(monkeypatch, sqlite_db):
    import httpx
    from app import mcp_server
    from app.main import app
    from app.routes import research as routes

    monkeypatch.setattr(routes.run_research_task, "delay", lambda run_id: type("R", (), {"id": "t"})())
    monkeypatch.setattr(mcp_server, "_client", lambda: httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://api"))
    result = asyncio.run(mcp_server.server.call_tool(
        "start_research", {"idea": "AI meeting notes for small law firms", "model": "claude-sonnet-5-5"}))
    data = result.structured_content or json.loads(result.content[0].text)
    assert data.get("result", data)["model"] == "claude-sonnet-5-5"
    tool = {t.name: t for t in asyncio.run(mcp_server.server.list_tools())}["start_research"]
    assert tool.input_schema["properties"]["model"]["enum"] == list(models.MODEL_IDS)
