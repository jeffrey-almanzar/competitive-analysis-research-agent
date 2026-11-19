# Phase 1 research loop: idea -> search queries -> competitors -> fetched pages -> sourced claims.

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from xml.sax.saxutils import escape, quoteattr

from app.research import llm, search
from app.research.schemas import (
    CompetitorExtraction,
    CompetitorProfile,
    CompetitorSelection,
    Report,
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
Rules:
- Use only information stated in the pages. Do not use prior knowledge.
- Every claim and price plan must cite the URL of the page it came from, copied exactly \
from that page's url attribute.
- The quote must be copied character-for-character from that page's text: a short excerpt \
(one sentence or phrase) that directly supports the claim. Do not paraphrase or fix typos \
in quotes.
- If the pages don't show pricing, return an empty pricing list. Don't guess prices.
- Prefer specific, decision-useful facts (who it's for, what it does, notable features, \
limits, pricing model) over marketing slogans.
- Record weaknesses only when the pages state them (e.g. missing features, limits on \
cheaper plans)."""


def plan_queries(idea: str) -> list[str]:
    plan = llm.structured(PLAN_SYSTEM, f"Business idea:\n{idea}", SearchPlan)
    return plan.queries


def select_competitors(idea: str, candidates: list[search.Candidate], limit: int):
    listing = "\n\n".join(
        f"- url: {c.url}\n  title: {c.title or ''}\n  snippet: {c.snippet[:400]}"
        for c in candidates
    )
    prompt = (
        f"Business idea:\n{idea}\n\nCandidates:\n{listing}\n\n"
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
    return picked[:limit]


def _format_pages(pages: list[search.Page]) -> str:
    return "\n\n".join(
        f"<page url={quoteattr(p.url)} title={quoteattr(p.title or '')}>\n{escape(p.text)}\n</page>"
        for p in pages
    )


def research_competitor(idea: str, comp) -> CompetitorProfile:
    pages = search.fetch_site(comp.homepage_url)
    sources = [Source(url=p.url, title=p.title) for p in pages]
    if not pages:
        log.warning("No page content fetched for %s", comp.name)
        return CompetitorProfile(**comp.model_dump(), pricing=[], claims=[], sources=[])

    prompt = (
        f"The user is researching competitors for this idea:\n{idea}\n\n"
        f"Company: {comp.name}\n\nPages:\n{_format_pages(pages)}"
    )
    extraction = llm.structured(EXTRACT_SYSTEM, prompt, CompetitorExtraction)

    # Discard anything citing a URL we didn't fetch.
    fetched = {p.url for p in pages}
    claims = [c for c in extraction.claims if c.source_url in fetched]
    pricing = [p for p in extraction.pricing if p.source_url in fetched]
    dropped = len(extraction.claims) - len(claims) + len(extraction.pricing) - len(pricing)

    return CompetitorProfile(
        **comp.model_dump(),
        pricing=pricing,
        claims=claims,
        sources=sources,
        dropped_items=dropped,
    )


def run_research(idea: str, max_competitors: int = 6, workers: int = 4) -> Report:
    log.info("Planning search queries")
    queries = plan_queries(idea)
    log.info("Queries: %s", queries)

    candidates = search.find_candidates(queries)
    log.info("Found %d candidate companies", len(candidates))

    competitors = select_competitors(idea, candidates, max_competitors)
    log.info("Selected: %s", ", ".join(c.name for c in competitors))

    def _safe(comp):
        try:
            return research_competitor(idea, comp)
        except Exception:
            log.exception("Research failed for %s", comp.name)
            return None

    with ThreadPoolExecutor(max_workers=workers) as pool:
        profiles = [p for p in pool.map(_safe, competitors) if p is not None]

    return Report(
        idea=idea,
        generated_at=datetime.now(timezone.utc),
        model=llm.MODEL,
        search_queries=queries,
        competitors=profiles,
    )
