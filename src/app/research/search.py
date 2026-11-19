# Thin wrappers around the Exa API: find candidate companies and fetch their pages.

import os
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlparse

from exa_py import Exa

# Page text sent to Claude is capped per page to keep requests bounded.
MAX_PAGE_CHARS = 15_000
SUBPAGE_TARGETS = ["pricing", "plans", "features", "product"]


@dataclass
class Page:
    url: str
    title: str | None
    text: str


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
        response = _client().search(
            query,
            num_results=per_query,
            category="company",
            type="auto",
            contents={"text": {"max_characters": 500}},
        )
        for r in response.results:
            d = domain(r.url)
            if d and d not in seen:
                seen[d] = Candidate(url=r.url, title=r.title, snippet=(r.text or "").strip())
    return list(seen.values())


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
        for sub in r.subpages or []:
            if sub.text:
                pages.append(Page(url=sub.url, title=sub.title, text=sub.text))
    return pages
