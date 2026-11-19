# Phase 4: persistence, progress, the Celery task, the API and the page cache.
# Runs on SQLite with Exa and Claude faked; no external services needed.

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from app import repository, tasks
from app.db import session_scope
from app.research import cache, pipeline, search
from tests.test_pipeline import IDEA, _patch


def _report(monkeypatch, **kw):
    _patch(monkeypatch)
    return pipeline.run_research(IDEA, **kw)


def test_progress_events_follow_the_graph(monkeypatch):
    events = []
    _report(monkeypatch, on_progress=events.append)
    steps = [(e.step, e.completed, e.total) for e in events]
    assert steps == [
        ("planning", 0, 0),
        ("finding_competitors", 0, 0),
        ("researching", 0, 2),
        ("researching", 1, 2),
        ("verifying", 2, 2),
        ("analyzing_gaps", 2, 2),
        ("done", 2, 2),
    ]


def test_report_round_trips_through_the_database(monkeypatch, sqlite_db):
    report = _report(monkeypatch)
    with session_scope() as s:
        run_id = repository.create_run(s, IDEA, 6, "claude-opus-5-5").id
    with session_scope() as s:
        repository.save_report(s, run_id, report)
    with session_scope() as s:
        loaded = repository.load_report(s, run_id)
        row = repository.get_run(s, run_id)
        assert row.status == "succeeded" and row.finished_at is not None
        # Verified claims are linked to their stored source page; the unfetched one isn't.
        claims = {c.claim_key: c for c in row.competitors[0].claims}
        assert claims["c1-1"].source_id is not None
        assert claims["c1-3"].source_id is None
    a = json.loads(report.model_dump_json(exclude={"generated_at"}))
    b = json.loads(loaded.model_dump_json(exclude={"generated_at"}))
    assert a == b


def test_task_runs_research_and_records_progress(monkeypatch, sqlite_db):
    _patch(monkeypatch)
    seen = []
    real = repository.set_progress
    monkeypatch.setattr(repository, "set_progress", lambda s, rid, p: (seen.append(p["step"]), real(s, rid, p)))
    with session_scope() as s:
        run_id = repository.create_run(s, IDEA, 6, "claude-opus-5-5").id

    assert tasks.run_research_task(str(run_id)) == {"status": "succeeded"}
    assert seen[0] == "planning" and seen[-1] == "done"
    with session_scope() as s:
        row = repository.get_run(s, run_id)
        assert (row.status, row.progress["step"]) == ("succeeded", "done")
        assert len(row.competitors) == 2

    # Redelivery of a finished run does nothing.
    monkeypatch.setattr(tasks, "run_research", lambda *a, **k: pytest.fail("should not re-run"))
    assert tasks.run_research_task(str(run_id)) == {"status": "succeeded"}


def test_task_failure_is_recorded(monkeypatch, sqlite_db):
    def boom(*a, **k):
        raise RuntimeError("Exa is down")

    monkeypatch.setattr(tasks, "run_research", boom)
    with session_scope() as s:
        run_id = repository.create_run(s, IDEA, 6, "claude-opus-5-5").id
    assert tasks.run_research_task(str(run_id)) == {"status": "failed"}
    with session_scope() as s:
        row = repository.get_run(s, run_id)
        assert row.status == "failed" and "Exa is down" in row.error


def test_api_queue_poll_and_fetch(monkeypatch, sqlite_db):
    from app.main import app
    from app.routes import research as routes

    queued = []
    monkeypatch.setattr(routes.run_research_task, "delay",
                        lambda run_id: queued.append(run_id) or type("R", (), {"id": "task-1"})())
    client = TestClient(app)

    r = client.post("/research", json={"idea": "AI meeting notes for small law firms", "max_competitors": 3})
    assert r.status_code == 202
    run = r.json()
    assert run["status"] == "queued" and queued == [run["id"]]
    assert client.get(f"/research/{run['id']}/report.md").status_code == 409

    # Simulate the worker.
    _patch(monkeypatch)
    tasks.run_research_task(run["id"])

    detail = client.get(run["links"]["self"]).json()
    assert detail["status"] == "succeeded" and detail["progress"]["step"] == "done"
    assert [c["name"] for c in detail["report"]["competitors"]] == ["Acme", "Beta"]
    md = client.get(detail["links"]["markdown"])
    assert md.status_code == 200 and md.text.startswith("# Competitive analysis")

    assert [x["id"] for x in client.get("/research").json()] == [run["id"]]
    assert client.get(f"/research/{uuid.uuid4()}").status_code == 404
    assert client.post("/research", json={"idea": "short"}).status_code == 422
    assert client.post("/research", json={"idea": "a long enough idea", "max_competitors": 50}).status_code == 422


class FakeRedis:
    def __init__(self):
        self.data, self.ttl = {}, {}

    def get(self, k):
        return self.data.get(k)

    def set(self, k, v, ex=None):
        self.data[k], self.ttl[k] = v, ex


def test_page_cache_skips_repeat_fetches(monkeypatch):
    fake = FakeRedis()
    monkeypatch.delenv("PAGE_CACHE_TTL_S")  # use the default lifetime
    monkeypatch.setattr(cache, "_client", lambda: fake)
    calls = []

    @cache.cached_pages("site", search.Page)
    def fetch(url, subpages=3):
        calls.append(url)
        return [search.Page(url, "T", "text", kind="site")] if "empty" not in url else []

    first = fetch("https://acme.com")
    second = fetch("https://acme.com")
    assert calls == ["https://acme.com"] and first == second
    assert list(fake.ttl.values()) == [cache.DEFAULT_TTL_S]

    fetch("https://empty.com"); fetch("https://empty.com")
    assert calls.count("https://empty.com") == 2  # empty results aren't cached
