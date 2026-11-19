# Pydantic models for the research report. Every fact in a report is a Claim or
# PricePlan carrying the URL it came from and a verbatim quote from that page.

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
    "other",
]


class Claim(BaseModel):
    category: ClaimCategory
    text: str = Field(description="The claim, in your own words, in one sentence.")
    source_url: str = Field(description="URL of the page the claim comes from, copied exactly.")
    quote: str = Field(
        description="A short excerpt copied character-for-character from that page "
        "that supports the claim."
    )


class PricePlan(BaseModel):
    plan_name: str
    price: str = Field(description='As written on the page, e.g. "$20/user/month" or "Contact sales".')
    source_url: str
    quote: str = Field(description="Excerpt copied character-for-character from the pricing page.")


class CompetitorExtraction(BaseModel):
    pricing: list[PricePlan] = Field(description="Empty if no pricing appears in the pages.")
    claims: list[Claim]


# --- Assembled report ------------------------------------------------------


class Source(BaseModel):
    url: str
    title: str | None = None


class CompetitorProfile(BaseModel):
    name: str
    homepage_url: str
    why_competitor: str
    pricing: list[PricePlan]
    claims: list[Claim]
    sources: list[Source]
    dropped_items: int = Field(
        0, description="Claims/plans discarded because they cited a URL that was not fetched."
    )


class Report(BaseModel):
    idea: str
    generated_at: datetime
    model: str
    search_queries: list[str]
    competitors: list[CompetitorProfile]
