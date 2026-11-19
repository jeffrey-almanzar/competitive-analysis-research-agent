# Offline tests for the research graph: Exa and Claude are replaced with fakes.

from app.research import pipeline, search
from app.research.render import to_markdown
from app.research.schemas import (
    CompetitorCandidate,
    CompetitorExtraction,
    CompetitorSelection,
    ExtractedClaim,
    ExtractedPrice,
    GapAnalysis,
    GapDraft,
    SearchPlan,
)

IDEA = "AI meeting notes for law firms"

SITE = {
    "https://acme.com": [
        search.Page("https://acme.com", "Acme", "Acme **records and summarizes** client calls for lawyers."),
        search.Page("https://acme.com/pricing", "Pricing", "Pro: $30/user/month. Enterprise: Contact sales."),
    ],
    "https://beta.io/": [],
}
REVIEWS = {
    "Acme": [
        search.Page("https://g2.com/acme", "Acme reviews",
                    "Setup took weeks and the mobile app keeps crashing during hearings.", kind="review"),
    ],
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
        assert "Acme" in prompt and 'kind="review"' in prompt
        return CompetitorExtraction(
            pricing=[
                ExtractedPrice(plan_name="Pro", price="$30/user/month",
                               source_url="https://acme.com/pricing", quote="Pro: $30/user/month."),
                ExtractedPrice(plan_name="Team", price="$50/user/month",
                               source_url="https://acme.com/pricing", quote="Pro: $30/user/month."),
            ],
            claims=[
                ExtractedClaim(category="product", text="Summarizes client calls.", source_url="https://acme.com",
                               quote="Acme records and summarizes client calls for lawyers."),
                ExtractedClaim(category="customer_complaint", text="Mobile app is unstable.",
                               source_url="https://g2.com/acme", quote="the mobile app keeps crashing"),
                ExtractedClaim(category="feature", text="Has an API.", source_url="https://acme.com/api",
                               quote="Use our REST API to export notes"),
                ExtractedClaim(category="strength", text="Bar-approved.", source_url="https://acme.com",
                               quote="Approved by every state bar association"),
            ],
        )
    if schema is GapAnalysis:
        # Only verified facts may be offered to the gap analysis.
        assert "[c1-1]" in prompt and "[c1-2]" in prompt and "[c1-p1]" in prompt
        assert "c1-3" not in prompt and "c1-4" not in prompt and "c1-p2" not in prompt
        return GapAnalysis(
            gaps=[
                GapDraft(title="Reliable mobile capture", description="Mobile app crashes.",
                         how_to_stand_out="Ship a stable offline-first app.", evidence_ids=["c1-2", "c1-4"]),
                GapDraft(title="Invented gap", description="No basis.",
                         how_to_stand_out="n/a", evidence_ids=["c9-9"]),
            ]
        )
    raise AssertionError(f"unexpected schema {schema}")


def _patch(monkeypatch):
    monkeypatch.setattr(pipeline.llm, "structured", fake_structured)
    monkeypatch.setattr(search, "find_candidates", lambda queries, per_query=10: [
        search.Candidate("https://acme.com", "Acme", "Legal call notes"),
        search.Candidate("https://beta.io/", "Beta", "Meeting notes"),
    ])
    monkeypatch.setattr(search, "fetch_site", lambda url, subpages=3: list(SITE[url]))
    monkeypatch.setattr(search, "fetch_reviews", lambda name, url, num_results=4: list(REVIEWS.get(name, [])))


def test_graph_end_to_end(monkeypatch):
    _patch(monkeypatch)
    report = pipeline.run_research(IDEA, max_competitors=5)

    # Invented URL is dropped; www. variant is normalized to the search-result URL.
    assert [c.name for c in report.competitors] == ["Acme", "Beta"]
    acme, beta = report.competitors
    assert acme.homepage_url == "https://acme.com"
    assert {s.kind for s in acme.sources} == {"site", "review"}

    status = {c.id: (c.verified, c.note) for c in acme.claims}
    assert status["c1-1"] == (True, "quote found on cited page")      # markdown bold ignored
    assert status["c1-2"] == (True, "quote found on cited page")      # review page
    assert status["c1-3"] == (False, "cited page was not fetched")
    assert status["c1-4"] == (False, "quote not found on cited page")

    prices = {p.plan_name: (p.verified, p.note) for p in acme.pricing}
    assert prices["Pro"][0] is True
    assert prices["Team"] == (False, "price not in quote")

    # Gap evidence is limited to verified IDs; a gap with none is flagged unsupported.
    real, invented = report.gaps
    assert real.evidence_ids == ["c1-2"] and real.supported
    assert invented.evidence_ids == [] and not invented.supported

    assert report.stats.claims_total == 4 and report.stats.claims_verified == 2
    assert report.stats.prices_verified == 1
    assert beta.claims == [] and "Beta: no pages could be fetched" in report.errors

    md = to_markdown(report)
    assert "## Market gaps and how to stand out" in md
    assert "### 1. Reliable mobile capture" in md
    assert "**Flagged gaps**" in md and "Invented gap" in md
    assert "Has an API." in md and "_cited page was not fetched_" in md
    assert "| Team |" not in md  # unverified price kept out of the pricing table


def test_one_competitor_failing_does_not_sink_the_report(monkeypatch):
    _patch(monkeypatch)

    def boom(url, subpages=3):
        if "beta" in url:
            raise TimeoutError("exa timed out")
        return list(SITE[url])

    monkeypatch.setattr(search, "fetch_site", boom)
    report = pipeline.run_research(IDEA)
    assert [c.name for c in report.competitors] == ["Acme"]
    assert any("Beta: research failed (TimeoutError" in e for e in report.errors)


def test_domain_normalization():
    assert search.domain("https://www.Acme.com/pricing") == "acme.com"
    assert search.domain("acme.com") == "acme.com"


def test_review_pages_must_name_the_company():
    assert search.mentions_company("VXT", "Vxt Reviews 2026 https://www.capterra.com/p/211214/Vxt/reviews/")
    assert search.mentions_company("Smart Note", "https://www.g2.com/products/smartnote/reviews")
    assert not search.mentions_company("Smartnote", "Smartnotation https://www.capterra.com/p/179097/Smartnotation/")
    assert not search.mentions_company("Smartnote", "Smart Noter reviews https://www.producthunt.com/products/smart-noter")
