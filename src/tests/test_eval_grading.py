# Offline checks of the eval grader (no API calls): known-good and known-bad inputs.

import json
from types import SimpleNamespace

import pytest

from app.research import telemetry
from evals import grading, run_eval
from tests.test_pipeline import _patch, IDEA, fake_structured
from app.research import pipeline


def _report(monkeypatch):
    _patch(monkeypatch)
    return pipeline.run_research(IDEA)


def test_recall_matches_by_domain_subdomain_or_name(monkeypatch):
    report = _report(monkeypatch)  # selects Acme (acme.com) and Beta (beta.io)
    expected = [
        {"name": "Acme Inc", "domains": ["acme.com"]},
        {"name": "Beta", "domains": ["beta-official.com"]},       # name match
        {"name": "Gamma", "domains": ["gamma.com"]},              # missed
    ]
    recall, found, missed = grading.competitor_recall(report, expected)
    assert (round(recall, 3), found, missed) == (0.667, ["Acme Inc", "Beta"], ["Gamma"])
    assert grading.competitor_recall(report, [{"name": "X", "domains": ["x.com"]}])[0] == 0.0  # null


def test_citation_grade_counts_and_only_judges_verified_items(monkeypatch):
    report = _report(monkeypatch)
    seen = {}

    def fake_structured(system, prompt, schema, **kw):
        ids = [line.split('"')[1] for line in prompt.splitlines() if line.startswith("<item id=")]
        seen["ids"] = ids
        verdicts = {"c1-1": "supported", "c1-2": "partial", "c1-p1": "supported"}
        return grading.JudgeResult(verdicts=[
            grading.Verdict(id=i, verdict=verdicts[i], reason="r") for i in ids
        ])

    monkeypatch.setattr(grading.llm, "structured", fake_structured)
    g = grading.grade_citations(report)
    assert sorted(seen["ids"]) == ["c1-1", "c1-2", "c1-p1"]  # unverified c1-3, c1-4, c1-p2 excluded
    assert (g.judged, g.supported, g.partial, round(g.score, 3)) == (3, 2, 1, 0.667)
    assert g.problems[0]["id"] == "c1-2"


def test_missing_verdicts_are_counted_not_scored(monkeypatch):
    report = _report(monkeypatch)
    monkeypatch.setattr(grading.llm, "structured", lambda *a, **k: grading.JudgeResult(verdicts=[]))
    g = grading.grade_citations(report)
    assert (g.judged, g.missing, g.score) == (0, 3, 0.0)


def test_cost_uses_served_model_and_cache_multipliers():
    call = telemetry.LLMCall("x", "claude-opus-5-5", "", "", None, 1_000_000, 100_000, 1_000_000, 1_000_000, 0, None)
    # 4 (input) + 2 (output) + 0.4 (cache read 0.1x) + 5 (cache write 1.25x)
    assert grading.cost_usd([call]) == 11.4
    with pytest.raises(KeyError):
        grading.cost_usd([call.__class__(**{**call.__dict__, "model": "unknown-model"})])


def test_runner_rejects_unapproved_harness(tmp_path):
    with pytest.raises(SystemExit) as e:
        run_eval.check_harness(tmp_path, approve=False)
    assert e.value.code == 2
    run_eval.check_harness(tmp_path, approve=True)
    run_eval.check_harness(tmp_path, approve=False)  # now approved
    state = json.loads((tmp_path / "_state.json").read_text())
    assert state["metrics"][0]["id"] == "citation_support"


def test_cases_file_is_well_formed():
    cases = run_eval.load_cases(run_eval.HERE / "cases.toml", None)
    assert len(cases) >= 15
    for c in cases:
        assert c["idea"] and c["tags"] and c["expected"], c["id"]
        assert all(e["name"] and e["domains"] for e in c["expected"]), c["id"]


def test_runner_end_to_end_with_failures_and_resume(monkeypatch, tmp_path):
    _patch(monkeypatch)
    real = pipeline.run_research

    def flaky(idea, max_competitors=6):
        if "veterinary" in idea:
            raise ConnectionError("simulated network failure")
        return real(IDEA, max_competitors=max_competitors)

    monkeypatch.setattr(run_eval.pipeline, "run_research", flaky)
    def structured(system, prompt, schema, **kw):
        if schema is not grading.JudgeResult:
            return fake_structured(system, prompt, schema, **kw)
        return grading.JudgeResult(verdicts=[
            grading.Verdict(id=line.split('"')[1], verdict="supported", reason="ok")
            for line in prompt.splitlines() if line.startswith("<item id=")
        ])

    monkeypatch.setattr(grading.llm, "structured", structured)
    # The fakes don't record LLM calls, so pretend the agent was served the right model.
    monkeypatch.setattr(run_eval.telemetry.RunRecorder, "llm_calls", property(lambda self: []))

    argv = ["run_eval", "--out", str(tmp_path), "--cases", "meal-kits,vet-practice-software", "--approve-harness"]
    monkeypatch.setattr("sys.argv", argv)
    assert run_eval.main() == 0

    var = tmp_path / "baseline"
    rows = [json.loads(l) for l in (var / "results.jsonl").read_text().splitlines()]
    errors = [json.loads(l) for l in (var / "errors.jsonl").read_text().splitlines()]
    assert [r["prompt_id"] for r in rows] == ["meal-kits"]
    assert rows[0]["grade"]["citation_support"] == 1.0
    assert set(rows[0]["grade"]) == {m["id"] for m in run_eval.METRICS}
    assert [(e["prompt_id"], e["class"]) for e in errors] == [("vet-practice-software", "api_error")]
    assert (var / "traces" / "meal-kits_rep0.json").exists()

    # Resume: the finished case is skipped, the failed one is retried.
    calls = []
    monkeypatch.setattr(run_eval.pipeline, "run_research", lambda idea, **k: calls.append(idea) or flaky(idea, **k))
    run_eval.main()
    assert len(calls) == 1 and "veterinary" in calls[0]
