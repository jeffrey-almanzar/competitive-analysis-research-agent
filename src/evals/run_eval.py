# Eval runner for the research agent.
#
#   docker compose run --rm api python -m evals.run_eval [--cases id,id] [--reps N] ...
#
# Runs the real entry point (app.research.pipeline.run_research) on each case in
# evals/cases.toml, grades the report (see evals/grading.py), and writes, per variant:
#   results.jsonl       one row per (case, rep) that produced a gradable report
#   errors.jsonl        one row per failed attempt (timeout, API error, model mismatch...)
#   traces/<id>_rep<k>.json   the run as a conversation (Claude calls, Exa calls, report)
#   reports/<id>_rep<k>.json  the full Report
# Resumable: (case, rep) pairs already in results.jsonl are skipped.

import argparse
import hashlib
import json
import logging
import math
import os
import sys
import threading
import time
import tomllib
import traceback
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from pathlib import Path

import anthropic

from app.research import llm, pipeline, telemetry
from app.research.render import to_markdown
from evals import grading

HERE = Path(__file__).resolve().parent
APP_ROOT = HERE.parent  # /app inside the container (= src/)
DEFAULT_OUT = Path(os.getenv("EVAL_OUT", "/hillclimb/research-report"))

# Files whose contents define the harness. If they change, the runner refuses to
# run until re-approved with --approve-harness, so a score can't silently mix versions.
HARNESS_PATHS = ["evals/run_eval.py", "evals/grading.py"]

METRICS = [
    {"id": "citation_support", "label": "Cites support", "kind": "float", "scale": 1},
    {"id": "verified_rate", "label": "Quote found", "kind": "float", "scale": 1},
    {"id": "competitor_recall", "label": "Recall", "kind": "float", "scale": 1},
    {"id": "gap_grounding", "label": "Gaps grounded", "kind": "float", "scale": 1},
]
PERF_FIELDS = [
    {"id": "cost_usd", "label": "Agent cost", "unit": "$"},
    {"id": "judge_cost_usd", "label": "Judge cost", "unit": "$"},
    {"id": "latency_s", "label": "Latency", "unit": "s"},
    {"id": "in_tokens", "label": "In tokens"},
    {"id": "out_tokens", "label": "Out tokens"},
    {"id": "exa_requests", "label": "Exa requests"},
    {"id": "competitors", "label": "Competitors"},
]

log = logging.getLogger("eval")
_write_lock = threading.Lock()


# --- Setup -----------------------------------------------------------------


def load_cases(path: Path, only: set[str] | None) -> list[dict]:
    cases = tomllib.loads(path.read_text())["case"]
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        raise SystemExit("Duplicate case ids in cases.toml")
    if only:
        unknown = only - set(ids)
        if unknown:
            raise SystemExit(f"Unknown case ids: {sorted(unknown)}")
        cases = [c for c in cases if c["id"] in only]
    return cases


def harness_sha() -> str:
    h = hashlib.sha256()
    for rel in HARNESS_PATHS:
        h.update(rel.encode())
        h.update((APP_ROOT / rel).read_bytes())
    return h.hexdigest()


def check_harness(flow_dir: Path, approve: bool) -> None:
    state_path = flow_dir / "_state.json"
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    sha = harness_sha()
    if state.get("harness_sha") != sha:
        if not approve:
            print(
                "The eval harness (" + ", ".join(HARNESS_PATHS) + ") is new or has changed since it was "
                "last approved.\nReview it, then re-run with --approve-harness.",
                file=sys.stderr,
            )
            raise SystemExit(2)
        state["harness_sha"] = sha
    state.update({"metrics": METRICS, "perf_fields": PERF_FIELDS, "harness_paths": HARNESS_PATHS})
    flow_dir.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, indent=2))


def done_keys(results_path: Path) -> set[tuple[str, int]]:
    if not results_path.exists():
        return set()
    keys = set()
    for line in results_path.read_text().splitlines():
        if line.strip():
            row = json.loads(line)
            keys.add((row["prompt_id"], row["rep"]))
    return keys


def append_jsonl(path: Path, row: dict) -> None:
    with _write_lock, path.open("a") as f:
        f.write(json.dumps(row) + "\n")


# --- One case ----------------------------------------------------------------


class ModelMismatch(RuntimeError):
    pass


def _trace(idea: str, rec: telemetry.RunRecorder, report_md: str) -> list[dict]:
    turns = [
        {"role": "system", "content": "Competitive research agent (LangGraph: plan -> find_competitors -> "
                                      "research_competitor x N -> verify -> analyze_gaps)."},
        {"role": "user", "content": idea},
    ]
    for ev in rec.events:
        if isinstance(ev, telemetry.LLMCall):
            turns.append({"role": "tool_call", "name": f"claude:{ev.name}",
                          "content": f"[model {ev.model}, {ev.input_tokens} in / {ev.output_tokens} out, "
                                     f"{ev.latency_s:.1f}s]\n\nSYSTEM:\n{ev.system}\n\nUSER:\n{ev.prompt}"})
            turns.append({"role": "tool_result", "content": json.dumps(ev.output, indent=2)})
        else:
            turns.append({"role": "tool_call", "name": ev.name, "content": json.dumps(ev.args, indent=2, default=str)})
            turns.append({"role": "tool_result", "content": json.dumps(ev.result, indent=2, default=str)})
    turns.append({"role": "assistant", "content": report_md})
    return turns


def run_case(case: dict, rep: int, args, var_dir: Path) -> dict:
    """Run and grade one (case, rep). Raises on failure; the caller records the error."""
    with telemetry.recording() as rec:
        report = pipeline.run_research(case["idea"], max_competitors=args.max_competitors)

    served = {c.model for c in rec.llm_calls}
    if served - {args.model}:
        raise ModelMismatch(f"requested {args.model}, served {sorted(served)}")

    with telemetry.recording() as judge_rec:
        cite = grading.grade_citations(report, model=args.judge_model)
    recall, found, missed = grading.competitor_recall(report, case["expected"])

    key = f"{case['id']}_rep{rep}"
    (var_dir / "traces" / f"{key}.json").write_text(
        json.dumps(_trace(case["idea"], rec, to_markdown(report)), indent=1)
    )
    (var_dir / "reports" / f"{key}.json").write_text(report.model_dump_json(indent=2))

    usage = {
        "input_tokens": sum(c.input_tokens for c in rec.llm_calls),
        "output_tokens": sum(c.output_tokens for c in rec.llm_calls),
        "cache_read_input_tokens": sum(c.cache_read_input_tokens for c in rec.llm_calls),
        "cache_creation_input_tokens": sum(c.cache_creation_input_tokens for c in rec.llm_calls),
    }
    judge_usage = {
        "input_tokens": sum(c.input_tokens for c in judge_rec.llm_calls),
        "output_tokens": sum(c.output_tokens for c in judge_rec.llm_calls),
    }
    return {
        "prompt_id": case["id"],
        "prompt": case["idea"],
        "tags": case.get("tags", []),
        "rep": rep,
        "status": "ok",
        "stop_reason": "end_turn",
        "grade": {
            "citation_support": round(cite.score, 4),
            "verified_rate": round(grading.verified_rate(report), 4),
            "competitor_recall": round(recall, 4),
            "gap_grounding": round(grading.gap_grounding(report), 4),
        },
        "explanation": {
            "citation_support": (
                f"{cite.supported}/{cite.judged} supported, {cite.partial} partial, "
                f"{cite.unsupported} unsupported, {cite.missing} not judged."
                + "".join(f"\n- [{p['verdict']}] {p['company']}: {p['claim']} — \"{p['quote']}\" ({p['reason']})"
                          for p in cite.problems[:15])
            ),
            "competitor_recall": f"found {found}; missed {missed}; selected "
                                 f"{[c.name for c in report.competitors]}",
        },
        "model": sorted(served)[0] if served else args.model,
        "usage": usage,
        "judge_model": args.judge_model,
        "judge_usage": judge_usage,
        "cost_usd": grading.cost_usd(rec.llm_calls),
        "judge_cost_usd": grading.cost_usd(judge_rec.llm_calls),
        "in_tokens": usage["input_tokens"],
        "out_tokens": usage["output_tokens"],
        "latency_s": report.usage.latency_s,
        "exa_requests": report.usage.exa_requests,
        "competitors": len(report.competitors),
        "meta": {"trace_url": report.usage.trace_url, "errors": report.errors,
                 "reviewed_case": case.get("reviewed", False)},
    }


def _failure_class(exc: BaseException) -> str:
    if isinstance(exc, FutureTimeout):
        return "timeout"
    if isinstance(exc, ModelMismatch):
        return "model_mismatch"
    if isinstance(exc, llm.LLMError) and "declined" in str(exc):
        return "refusal"
    if isinstance(exc, (anthropic.APIError, ConnectionError, TimeoutError)):
        return "api_error"
    return "harness_error"


# --- Main ------------------------------------------------------------------


def summarize(results_path: Path) -> None:
    rows = [json.loads(l) for l in results_path.read_text().splitlines() if l.strip()] if results_path.exists() else []
    if not rows:
        print("No results.")
        return
    print(f"\n{len(rows)} graded runs")
    for m in METRICS:
        vals = [r["grade"][m["id"]] for r in rows]
        mean = sum(vals) / len(vals)
        sd = math.sqrt(sum((v - mean) ** 2 for v in vals) / (len(vals) - 1)) if len(vals) > 1 else 0.0
        half = 1.96 * sd / math.sqrt(len(vals))
        print(f"  {m['label']:<14} {mean:.3f} ± {half:.3f}  (95% CI, n={len(vals)})")
    for f in ("cost_usd", "judge_cost_usd", "latency_s"):
        vals = sorted(r[f] for r in rows)
        print(f"  {f:<14} median {vals[len(vals) // 2]:.2f}  min {vals[0]:.2f}  max {vals[-1]:.2f}  total {sum(vals):.2f}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the research-report eval.")
    parser.add_argument("--variant", default="baseline", help='"baseline" or v1, v2, ...')
    parser.add_argument("--cases", help="Comma-separated case ids (default: all)")
    parser.add_argument("--reps", type=int, default=1)
    parser.add_argument("--concurrency", type=int, default=3, help="Cases run at once")
    parser.add_argument("--timeout-s", type=float, default=900, help="Wall-clock ceiling per case")
    parser.add_argument("--max-competitors", type=int, default=6)
    parser.add_argument("--model", default=llm.MODEL, help="Model the agent must be served by")
    parser.add_argument("--judge-model", default=grading.JUDGE_MODEL)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--approve-harness", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()

    if args.variant != "baseline" and not (args.variant[:1] == "v" and args.variant[1:].isdigit()):
        raise SystemExit('--variant must be "baseline" or v<N>')
    if args.model != llm.MODEL:
        raise SystemExit(f"--model {args.model} differs from the agent's CLAUDE_MODEL ({llm.MODEL}); set CLAUDE_MODEL")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s", datefmt="%H:%M:%S")
    for noisy in ("httpx", "httpx2", "anthropic", "app.research"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    var_dir = args.out / args.variant
    results_path, errors_path = var_dir / "results.jsonl", var_dir / "errors.jsonl"
    if args.summary_only:
        summarize(results_path)
        return 0

    check_harness(args.out, args.approve_harness)
    (var_dir / "traces").mkdir(parents=True, exist_ok=True)
    (var_dir / "reports").mkdir(parents=True, exist_ok=True)

    only = set(args.cases.split(",")) if args.cases else None
    cases = load_cases(HERE / "cases.toml", only)
    done = done_keys(results_path)
    todo = [(c, r) for c in cases for r in range(args.reps) if (c["id"], r) not in done]
    log.info("%d cases x %d reps: %d to run, %d already done", len(cases), args.reps, len(todo), len(done))

    def attempt(item):
        case, rep = item
        start = time.monotonic()
        # A separate thread enforces the wall-clock ceiling; a timed-out run may keep going
        # in the background but its slot and result are released.
        single = ThreadPoolExecutor(max_workers=1)
        future = single.submit(run_case, case, rep, args, var_dir)
        try:
            row = future.result(timeout=args.timeout_s)
            append_jsonl(results_path, row)
            g = row["grade"]
            log.info("%s rep%d: support %.2f, found %.2f, recall %.2f, gaps %.2f, $%.2f + judge $%.2f, %.0fs",
                     case["id"], rep, g["citation_support"], g["verified_rate"], g["competitor_recall"],
                     g["gap_grounding"], row["cost_usd"], row["judge_cost_usd"], row["latency_s"])
        except BaseException as exc:
            cls = _failure_class(exc)
            log.error("%s rep%d failed (%s): %s", case["id"], rep, cls, exc)
            append_jsonl(errors_path, {
                "prompt_id": case["id"], "rep": rep, "class": cls, "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=5), "elapsed_s": round(time.monotonic() - start, 1),
            })
        finally:
            single.shutdown(wait=False)

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        list(pool.map(attempt, todo))

    summarize(results_path)
    if errors_path.exists():
        n = sum(1 for l in errors_path.read_text().splitlines() if l.strip())
        print(f"  {n} failed attempt(s) recorded in {errors_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
