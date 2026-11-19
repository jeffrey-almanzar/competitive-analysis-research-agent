# Phase 2 research agent as a LangGraph graph:
#
#   plan -> find_competitors -> research_competitor (one per competitor, in parallel)
#        -> verify -> analyze_gaps -> END
#
# Claude plans, selects, extracts and analyzes; code checks every quote against the
# fetched page text, and the gap analysis may only cite claims that passed that check.

import logging
import operator
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Annotated, Callable, TypedDict
from xml.sax.saxutils import escape, quoteattr

from langgraph.graph import END, START, StateGraph
from langgraph.types import Send

from app.research import llm, search, telemetry, verify
from app.research.schemas import (
    Claim,
    CompetitorCandidate,
    CompetitorExtraction,
    CompetitorProfile,
    CompetitorSelection,
    GapAnalysis,
    MarketGap,
    PricePlan,
    Report,
    ReportStats,
    RunUsage,
    SearchPlan,
    Source,
)

log = logging.getLogger(__name__)

PLAN_SYSTEM = """You help founders research their competition. Given a business idea, \
write web search queries that will surface the companies and products a customer would \
consider instead. Phrase each query as a description of such a company (e.g. "AI tool that \
transcribes and summarizes legal client meetings"), not as a question. Cover direct \
competitors and the closest substitutes."""

SELECT_SYSTEM = """You pick the real competitors of a business idea from a list of \
search results. Keep only companies whose product a target customer could choose instead \
of the idea. Skip directories, blogs, news articles, review sites, and unrelated companies. \
Use the homepage URL exactly as it appears in the candidate list; never invent a URL."""

EXTRACT_SYSTEM = """You extract facts about one company from the web pages provided. \
Pages with kind="site" are the company's own website; pages with kind="review" are \
third-party reviews and discussions written by customers.
Rules:
- Use only information stated in the pages. Do not use prior knowledge.
- Every claim and price plan must cite the URL of the page it came from, copied exactly \
from that page's url attribute.
- The quote must be copied character-for-character from that page's text: a short excerpt \
(one sentence or phrase, at least a few words) that directly supports the claim. Do not \
paraphrase, fix typos, or merge text from different places. Quotes are checked \
automatically against the page, and any quote that doesn't match is flagged.
- If the pages don't show pricing, return an empty pricing list. Don't guess prices.
- Prefer specific, decision-useful facts (who it's for, what it does, notable features, \
limits, pricing model) over marketing slogans.
- From review pages, record what customers praise (customer_praise) and complain about \
(customer_complaint). Only include reviews that are clearly about this company.
- Record weaknesses from the company's own pages only when they are stated there \
(e.g. missing features, limits on cheaper plans)."""

GAPS_SYSTEM = """You find gaps in a market for a founder. You receive verified facts about \
competitors, each with an ID. Identify where competitors are weak, missing something, \
overpriced, or underserving a customer group, and how the founder's idea could stand out.
Rules:
- Base every gap only on the facts provided, and list the IDs of the facts that support it.
- Prefer gaps backed by several facts or by customer complaints.
- Don't repeat the same gap in different words. Return 3-6 gaps, strongest first.
- If the facts don't support a gap, don't include it."""


# --- Graph state -----------------------------------------------------------


def _merge(a: dict, b: dict) -> dict:
    return {**a, **b}


class ResearchState(TypedDict, total=False):
    idea: str
    max_competitors: int
    queries: list[str]
    competitors: list[CompetitorCandidate]
    # Written by parallel research_competitor branches, merged by these reducers.
    profiles: Annotated[list[CompetitorProfile], operator.add]
    pages: Annotated[dict[str, str], _merge]
    errors: Annotated[list[str], operator.add]
    # Profiles after quote checking, sorted by rank (replaces, not appended).
    verified_profiles: list[CompetitorProfile]
    gaps: list[MarketGap]


class CompetitorTask(TypedDict):
    idea: str
    rank: int
    competitor: CompetitorCandidate


# --- Nodes -----------------------------------------------------------------


@telemetry.traced_node
def plan(state: ResearchState) -> dict:
    result = llm.structured(PLAN_SYSTEM, f"Business idea:\n{state['idea']}", SearchPlan)
    log.info("Queries: %s", result.queries)
    return {"queries": result.queries}


@telemetry.traced_node
def find_competitors(state: ResearchState) -> dict:
    candidates = search.find_candidates(state["queries"])
    log.info("Found %d candidate companies", len(candidates))
    listing = "\n\n".join(
        f"- url: {c.url}\n  title: {c.title or ''}\n  snippet: {c.snippet[:400]}"
        for c in candidates
    )
    limit = state.get("max_competitors", 6)
    prompt = (
        f"Business idea:\n{state['idea']}\n\nCandidates:\n{listing}\n\n"
        f"Return up to {limit} competitors, most direct first."
    )
    selection = llm.structured(SELECT_SYSTEM, prompt, CompetitorSelection)

    # Keep only URLs that were actually in the search results.
    known = {search.domain(c.url): c.url for c in candidates}
    picked, seen = [], set()
    for comp in selection.competitors:
        d = search.domain(comp.homepage_url)
        if d in known and d not in seen:
            seen.add(d)
            picked.append(comp.model_copy(update={"homepage_url": known[d]}))
        else:
            log.warning("Dropping competitor %s: URL not in search results", comp.name)
    picked = picked[:limit]
    log.info("Selected: %s", ", ".join(c.name for c in picked))
    return {"competitors": picked}


def fan_out(state: ResearchState) -> list[Send]:
    return [
        Send("research_competitor", {"idea": state["idea"], "rank": i, "competitor": comp})
        for i, comp in enumerate(state["competitors"], start=1)
    ]


def _format_pages(pages: list[search.Page]) -> str:
    return "\n\n".join(
        f"<page url={quoteattr(p.url)} kind={quoteattr(p.kind)} title={quoteattr(p.title or '')}>\n"
        f"{escape(p.text)}\n</page>"
        for p in pages
    )


@telemetry.traced_node
def research_competitor(task: CompetitorTask) -> dict:
    comp, rank = task["competitor"], task["rank"]
    try:
        pages = search.fetch_site(comp.homepage_url)
        try:
            pages += search.fetch_reviews(comp.name, comp.homepage_url)
        except Exception as exc:  # Reviews are optional; keep the site research.
            log.warning("Review search failed for %s: %s", comp.name, exc)

        profile = CompetitorProfile(
            rank=rank,
            **comp.model_dump(),
            pricing=[],
            claims=[],
            sources=[Source(url=p.url, title=p.title, kind=p.kind) for p in pages],
        )
        if not pages:
            log.warning("No page content fetched for %s", comp.name)
            return {"profiles": [profile], "errors": [f"{comp.name}: no pages could be fetched"]}

        prompt = (
            f"The user is researching competitors for this idea:\n{task['idea']}\n\n"
            f"Company: {comp.name} ({comp.homepage_url})\n\nPages:\n{_format_pages(pages)}"
        )
        extraction = llm.structured(EXTRACT_SYSTEM, prompt, CompetitorExtraction)

        profile.claims = [
            Claim(id=f"c{rank}-{n}", **c.model_dump()) for n, c in enumerate(extraction.claims, 1)
        ]
        profile.pricing = [
            PricePlan(id=f"c{rank}-p{n}", **p.model_dump()) for n, p in enumerate(extraction.pricing, 1)
        ]
        log.info("%s: %d claims, %d price plans from %d pages",
                 comp.name, len(profile.claims), len(profile.pricing), len(pages))
        return {"profiles": [profile], "pages": {p.url: p.text for p in pages}}
    except Exception as exc:
        log.exception("Research failed for %s", comp.name)
        return {"errors": [f"{comp.name}: research failed ({type(exc).__name__}: {exc})"]}


@telemetry.traced_node
def verify_sources(state: ResearchState) -> dict:
    pages = state.get("pages", {})
    profiles = []
    for prof in sorted(state.get("profiles", []), key=lambda p: p.rank):
        profiles.append(
            prof.model_copy(
                update={
                    "claims": [verify.verify_claim(c, pages) for c in prof.claims],
                    "pricing": [verify.verify_price(p, pages) for p in prof.pricing],
                }
            )
        )
    return {"verified_profiles": profiles}


@telemetry.traced_node
def analyze_gaps(state: ResearchState) -> dict:
    profiles: list[CompetitorProfile] = state["verified_profiles"]
    verified = {c.id: c for p in profiles for c in p.claims if c.verified}
    if not verified:
        log.warning("No verified claims; skipping gap analysis")
        return {"gaps": []}

    facts = []
    for p in profiles:
        rows = [f'  [{c.id}] ({c.category}) {c.text} — "{c.quote}"' for c in p.claims if c.verified]
        rows += [f"  [{pp.id}] (pricing) {pp.plan_name}: {pp.price}" for pp in p.pricing if pp.verified]
        if rows:
            facts.append(f"{p.name} ({p.homepage_url}):\n" + "\n".join(rows))
    prompt = f"Founder's idea:\n{state['idea']}\n\nVerified facts:\n\n" + "\n\n".join(facts)
    analysis = llm.structured(GAPS_SYSTEM, prompt, GapAnalysis, effort="high")

    verified_prices = {pp.id for p in profiles for pp in p.pricing if pp.verified}
    gaps = []
    for g in analysis.gaps:
        evidence = [i for i in g.evidence_ids if i in verified or i in verified_prices]
        dropped = set(g.evidence_ids) - set(evidence)
        if dropped:
            log.warning("Gap %r cited unknown/unverified IDs: %s", g.title, sorted(dropped))
        gaps.append(
            MarketGap(
                title=g.title,
                description=g.description,
                how_to_stand_out=g.how_to_stand_out,
                evidence_ids=evidence,
                supported=bool(evidence),
            )
        )
    return {"gaps": gaps}


# --- Graph -----------------------------------------------------------------


def build_graph():
    g = StateGraph(ResearchState)
    g.add_node("plan", plan)
    g.add_node("find_competitors", find_competitors)
    g.add_node("research_competitor", research_competitor)
    g.add_node("verify", verify_sources)
    g.add_node("analyze_gaps", analyze_gaps)

    g.add_edge(START, "plan")
    g.add_edge("plan", "find_competitors")
    g.add_conditional_edges("find_competitors", fan_out, ["research_competitor"])
    g.add_edge("research_competitor", "verify")
    g.add_edge("verify", "analyze_gaps")
    g.add_edge("analyze_gaps", END)
    return g.compile()


def _stats(profiles: list[CompetitorProfile], gaps: list[MarketGap]) -> ReportStats:
    claims = [c for p in profiles for c in p.claims]
    prices = [pp for p in profiles for pp in p.pricing]
    return ReportStats(
        claims_total=len(claims),
        claims_verified=sum(c.verified for c in claims),
        prices_total=len(prices),
        prices_verified=sum(pp.verified for pp in prices),
        gaps_supported=sum(g.supported for g in gaps),
        gaps_unsupported=sum(not g.supported for g in gaps),
    )


def _usage(rec: telemetry.RunRecorder, trace_url: str | None) -> RunUsage:
    calls = rec.llm_calls
    return RunUsage(
        models=sorted({c.model for c in calls}),
        llm_calls=len(calls),
        input_tokens=sum(c.input_tokens for c in calls),
        output_tokens=sum(c.output_tokens for c in calls),
        cache_read_input_tokens=sum(c.cache_read_input_tokens for c in calls),
        cache_creation_input_tokens=sum(c.cache_creation_input_tokens for c in calls),
        exa_requests=len(rec.tool_calls),
        latency_s=round(time.monotonic() - rec.started, 2),
        trace_url=trace_url,
    )


@dataclass
class Progress:
    step: str  # planning | finding_competitors | researching | verifying | analyzing_gaps | done
    message: str
    completed: int = 0  # competitors researched so far (during "researching")
    total: int = 0


ProgressCallback = Callable[[Progress], None]


def _progress_after(node: str, update: dict, state: dict) -> Progress | None:
    """Translate a finished graph node into the next user-visible step."""
    if node == "plan":
        return Progress("finding_competitors", "Searching for competitors")
    if node == "find_competitors":
        n = len(update.get("competitors", []))
        state["total"], state["completed"] = n, 0
        if n == 0:
            return Progress("done", "No competitors found")
        return Progress("researching", f"Researching {n} competitors", 0, n)
    if node == "research_competitor":
        state["completed"] += 1
        done, total = state["completed"], state["total"]
        if done < total:
            return Progress("researching", f"Researched {done} of {total} competitors", done, total)
        return Progress("verifying", "Checking quotes against sources", done, total)
    if node == "verify":
        return Progress("analyzing_gaps", "Analyzing market gaps", state["total"], state["total"])
    if node == "analyze_gaps":
        return Progress("done", "Report ready", state["total"], state["total"])
    return None


def run_research(
    idea: str,
    max_competitors: int = 6,
    max_parallel: int = 4,
    on_progress: ProgressCallback | None = None,
    model: str | None = None,
) -> Report:
    """Research competitors for `idea`. `model` picks the Claude model (default: llm.MODEL)."""
    graph = build_graph()
    notify = on_progress or (lambda p: None)
    with llm.use_model(model) as run_model, telemetry.recording(reuse=True) as rec, telemetry.observe(
        "research", as_type="agent", input={"idea": idea, "max_competitors": max_competitors, "model": run_model}
    ) as root:
        notify(Progress("planning", "Planning search queries"))
        state: dict = {}
        tracker = {"completed": 0, "total": 0}
        for mode, chunk in graph.stream(
            {"idea": idea, "max_competitors": max_competitors},
            config={"max_concurrency": max_parallel},
            stream_mode=["updates", "values"],
        ):
            if mode == "values":
                state = chunk
                continue
            for node, update in chunk.items():
                progress = _progress_after(node, update or {}, tracker)
                if progress is not None:
                    notify(progress)
        profiles = state.get("verified_profiles", [])
        gaps = state.get("gaps", [])
        report = Report(
            idea=idea,
            generated_at=datetime.now(timezone.utc),
            model=run_model,
            search_queries=state.get("queries", []),
            competitors=profiles,
            gaps=gaps,
            stats=_stats(profiles, gaps),
            errors=state.get("errors", []),
        )
        if root is not None:
            root.update(output=report.stats.model_dump())
        report.usage = _usage(rec, telemetry.trace_url())
    telemetry.flush()
    return report
