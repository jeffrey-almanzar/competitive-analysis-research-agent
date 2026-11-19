# Offline tests for the Phase 1 pipeline: Exa and Claude are replaced with fakes.

from app.research import pipeline, search
from app.research.render import to_markdown
from app.research.schemas import (
    Claim,
    CompetitorCandidate,
    CompetitorExtraction,
    CompetitorSelection,
    PricePlan,
    SearchPlan,
)

IDEA = "AI meeting notes for law firms"

PAGES = {
    "https://acme.com": [
        search.Page("https://acme.com", "Acme", "Acme records and summarizes client calls for lawyers."),
        search.Page("https://acme.com/pricing", "Pricing", "Pro: $30/user/month. Enterprise: Contact sales."),
    ],
    "https://beta.io/": [],
}


def fake_structured(system, prompt, schema, effort="medium"):
    if schema is SearchPlan:
        return SearchPlan(queries=["AI note taker for lawyers"])
    if schema is CompetitorSelection:
        return CompetitorSelection(
            competitors=[
                CompetitorCandidate(name="Acme", homepage_url="https://www.acme.com", why_competitor="Same use case."),
                CompetitorCandidate(name="Beta", homepage_url="https://beta.io/", why_competitor="Adjacent."),
                CompetitorCandidate(name="Ghost", homepage_url="https://invented.example", why_competitor="Made up."),
            ]
        )
    if schema is CompetitorExtraction:
        return CompetitorExtraction(
            pricing=[
                PricePlan(plan_name="Pro", price="$30/user/month", source_url="https://acme.com/pricing", quote="Pro: $30/user/month."),
            ],
            claims=[
                Claim(category="product", text="Summarizes client calls.", source_url="https://acme.com",
                      quote="Acme records and summarizes client calls for lawyers."),
                Claim(category="feature", text="Has an API.", source_url="https://acme.com/api", quote="Our API"),
            ],
        )
    raise AssertionError(f"unexpected schema {schema}")


def fake_candidates(queries, per_query=10):
    return [
        search.Candidate("https://acme.com", "Acme", "Legal call notes"),
        search.Candidate("https://beta.io/", "Beta", "Meeting notes"),
    ]


def test_run_research_end_to_end(monkeypatch):
    monkeypatch.setattr(pipeline.llm, "structured", fake_structured)
    monkeypatch.setattr(search, "find_candidates", fake_candidates)
    monkeypatch.setattr(search, "fetch_site", lambda url, subpages=3: PAGES[url])

    report = pipeline.run_research(IDEA, max_competitors=5)

    # Invented URL is dropped; www. variant is normalized to the search-result URL.
    assert [c.name for c in report.competitors] == ["Acme", "Beta"]
    acme, beta = report.competitors
    assert acme.homepage_url == "https://acme.com"

    # Claim citing an unfetched page is discarded and counted.
    assert [c.text for c in acme.claims] == ["Summarizes client calls."]
    assert acme.dropped_items == 1
    assert acme.pricing[0].price == "$30/user/month"

    # A site with no fetched content yields an empty profile rather than an error.
    assert beta.claims == [] and beta.pricing == []

    md = to_markdown(report)
    assert "| Pro | $30/user/month | [1] |" in md
    assert "1. https://acme.com/pricing\n2. https://acme.com\n" in md
    assert '> "Acme records and summarizes client calls for lawyers."' in md
    assert "Pricing:** not found" in md


def test_domain_normalization():
    assert search.domain("https://www.Acme.com/pricing") == "acme.com"
    assert search.domain("acme.com") == "acme.com"
