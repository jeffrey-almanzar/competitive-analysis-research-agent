# Thin wrappers around the Exa API: find candidate companies and fetch their pages.

import logging
import os
import re
from dataclasses import dataclass
from typing import Literal
from functools import lru_cache
from urllib.parse import urlparse

from exa_py import Exa

from app.research import telemetry

log = logging.getLogger(__name__)

# Page text sent to Claude is capped per page to keep requests bounded.
MAX_PAGE_CHARS = 15_000
MAX_REVIEW_CHARS = 8_000
SUBPAGE_TARGETS = ["pricing", "plans", "features", "product"]
REVIEW_DOMAINS = [
    "g2.com",
    "capterra.com",
    "trustradius.com",
    "trustpilot.com",
    "producthunt.com",
    "reddit.com",
]


@dataclass
class Page:
    url: str
    title: str | None
    text: str
    kind: Literal["site", "review"] = "site"


@dataclass
class Candidate:
    url: str
    title: str | None
    snippet: str


@lru_cache(maxsize=1)
def _client() -> Exa:
    key = os.getenv("EXA_API_KEY")
    if not key:
        raise RuntimeError("EXA_API_KEY is not set. Add it to .env (see .env.example).")
    return Exa(api_key=key)


def domain(url: str) -> str:
    host = urlparse(url if "://" in url else f"https://{url}").netloc.lower()
    return host.removeprefix("www.")


def find_candidates(queries: list[str], per_query: int = 10) -> list[Candidate]:
    """Run each query as a company search and return results de-duplicated by domain."""
    seen: dict[str, Candidate] = {}
    for query in queries:
        for r in _company_search(query, num_results=per_query):
            d = domain(r.url)
            if d and d not in seen:
                seen[d] = r
    return list(seen.values())


@telemetry.tool("exa.search_companies")
def _company_search(query: str, num_results: int) -> list[Candidate]:
    response = _client().search(
        query,
        num_results=num_results,
        category="company",
        type="auto",
        contents={"text": {"max_characters": 500}},
    )
    return [Candidate(url=r.url, title=r.title, snippet=(r.text or "").strip()) for r in response.results]


@telemetry.tool("exa.fetch_site")
def fetch_site(homepage_url: str, subpages: int = 3) -> list[Page]:
    """Fetch a competitor's homepage plus likely pricing/feature subpages."""
    response = _client().get_contents(
        [homepage_url],
        text={"max_characters": MAX_PAGE_CHARS},
        subpages=subpages,
        subpage_target=SUBPAGE_TARGETS,
    )
    pages: list[Page] = []
    for r in response.results:
        if r.text:
            pages.append(Page(url=r.url, title=r.title, text=r.text))
        # Exa returns subpages as plain dicts rather than Result objects.
        for sub in r.subpages or []:
            get = sub.get if isinstance(sub, dict) else lambda k, o=sub: getattr(o, k, None)
            if get("text") and get("url"):
                pages.append(Page(url=get("url"), title=get("title"), text=get("text")))
    return pages


@telemetry.tool("exa.search_reviews")
def fetch_reviews(company: str, homepage_url: str, num_results: int = 4) -> list[Page]:
    """Find review and discussion pages about a company on review sites and Reddit."""
    # Exa's include_text accepts one phrase of up to 5 words.
    name_phrase = " ".join(company.split()[:5])
    response = _client().search(
        f"{company} ({domain(homepage_url)}) reviews, pros and cons, complaints",
        num_results=num_results,
        type="auto",
        include_domains=REVIEW_DOMAINS,
        include_text=[name_phrase],
        contents={"text": {"max_characters": MAX_REVIEW_CHARS}},
    )
    pages = []
    for r in response.results:
        if not r.text:
            continue
        if not mentions_company(company, f"{r.title or ''} {r.url}"):
            log.info("Skipping review page not about %s: %s", company, r.url)
            continue
        pages.append(Page(url=r.url, title=r.title, text=r.text, kind="review"))
    return pages


def _tokens(text: str) -> str:
    return " " + " ".join(re.findall(r"[a-z0-9]+", text.lower())) + " "


def mentions_company(company: str, text: str) -> bool:
    """True if the company name appears as whole words in text (title/URL of a review page).

    Review search often returns similarly named products (e.g. "Smartnotation" for
    "Smartnote"), so require a whole-word match, also accepting the name with spaces
    removed ("Smart Note" matches "smartnote").
    """
    name = _tokens(company).strip()
    if not name:
        return False
    haystack = _tokens(text)
    return f" {name} " in haystack or f" {name.replace(' ', '')} " in haystack
