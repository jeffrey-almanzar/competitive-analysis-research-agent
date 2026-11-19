# Pydantic models for the research report. Every fact in a report is a Claim or
# PricePlan carrying the URL it came from and a verbatim quote from that page.
# Quotes are checked against the fetched page text in code (see verify.py).

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# --- Models Claude fills in (structured outputs) ---------------------------


class SearchPlan(BaseModel):
    queries: list[str] = Field(
        description="3-5 web search queries, each phrased as a description of a "
        "company or product that would compete with the idea."
    )


class CompetitorCandidate(BaseModel):
    name: str
    homepage_url: str = Field(description="Must be copied exactly from the candidate list.")
    why_competitor: str = Field(description="One sentence on why this competes with the idea.")


class CompetitorSelection(BaseModel):
    competitors: list[CompetitorCandidate]


ClaimCategory = Literal[
    "product",
    "target_customer",
    "positioning",
    "feature",
    "strength",
    "weakness",
    "customer_praise",
    "customer_complaint",
    "other",
]


class ExtractedClaim(BaseModel):
    category: ClaimCategory
    text: str = Field(description="The claim, in your own words, in one sentence.")
    source_url: str = Field(description="URL of the page the claim comes from, copied exactly.")
    quote: str = Field(
        description="A short excerpt copied character-for-character from that page "
        "that supports the claim."
    )


class ExtractedPrice(BaseModel):
    plan_name: str
    price: str = Field(description='As written on the page, e.g. "$20/user/month" or "Contact sales".')
    source_url: str
    quote: str = Field(description="Excerpt copied character-for-character from the pricing page.")


class CompetitorExtraction(BaseModel):
    pricing: list[ExtractedPrice] = Field(description="Empty if no pricing appears in the pages.")
    claims: list[ExtractedClaim]


class GapDraft(BaseModel):
    title: str = Field(description="Short name for the gap.")
    description: str = Field(description="What competitors miss or do poorly, in 1-2 sentences.")
    how_to_stand_out: str = Field(description="How the idea could exploit this gap, in 1-2 sentences.")
    evidence_ids: list[str] = Field(description="IDs of the claims that support this gap.")


class GapAnalysis(BaseModel):
    gaps: list[GapDraft]


# --- Assembled report ------------------------------------------------------


class Verification(BaseModel):
    verified: bool = False
    note: str = "not checked"


class Claim(ExtractedClaim, Verification):
    id: str


class PricePlan(ExtractedPrice, Verification):
    id: str


class Source(BaseModel):
    url: str
    title: str | None = None
    kind: Literal["site", "review"] = "site"


class CompetitorProfile(BaseModel):
    rank: int
    name: str
    homepage_url: str
    why_competitor: str
    pricing: list[PricePlan]
    claims: list[Claim]
    sources: list[Source]


class MarketGap(BaseModel):
    title: str
    description: str
    how_to_stand_out: str
    evidence_ids: list[str] = Field(description="Verified claim IDs backing this gap.")
    supported: bool = Field(description="False when none of the cited evidence is a verified claim.")


class ReportStats(BaseModel):
    claims_total: int
    claims_verified: int
    prices_total: int
    prices_verified: int
    gaps_supported: int
    gaps_unsupported: int


class Report(BaseModel):
    idea: str
    generated_at: datetime
    model: str
    search_queries: list[str]
    competitors: list[CompetitorProfile]
    gaps: list[MarketGap]
    stats: ReportStats
    errors: list[str] = []
