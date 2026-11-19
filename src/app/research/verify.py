# Code-based source checking: a claim is verified only if its quote actually appears
# in the text of the page it cites. The model never grades its own output.

import html
import re
import unicodedata

from app.research.schemas import Claim, PricePlan

MIN_QUOTE_CHARS = 12

_CHAR_MAP = str.maketrans(
    {
        "‘": "'", "’": "'", "‚": "'", "‛": "'",
        "“": '"', "”": '"', "„": '"', "‟": '"',
        "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "−": "-",
        " ": " ", " ": " ", " ": " ",
        "*": " ", "#": " ", "`": " ", "|": " ",
    }
)
_MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_ELLIPSIS = re.compile(r"\.\.\.|…|\[\.\.\.\]")
_EDGE_PUNCT = " \"'.,;:!?()[]-"


def normalize(text: str) -> str:
    """Lowercase and strip formatting differences that don't change the words."""
    # Page text is HTML-escaped in the prompt, so quotes may contain &amp; etc.
    text = unicodedata.normalize("NFKC", html.unescape(text))
    text = _MD_LINK.sub(r"\1", text)
    text = text.translate(_CHAR_MAP).lower()
    return re.sub(r"\s+", " ", text).strip()


def find_quote(quote: str, page_text: str) -> tuple[bool, str]:
    """Return (found, note). Quotes may skip text with '...'; fragments must appear in order."""
    fragments = [f.strip(_EDGE_PUNCT) for f in _ELLIPSIS.split(normalize(quote))]
    fragments = [f for f in fragments if f]
    if sum(len(f) for f in fragments) < MIN_QUOTE_CHARS:
        return False, "quote too short to verify"

    page = normalize(page_text)
    pos = 0
    for fragment in fragments:
        i = page.find(fragment, pos)
        if i < 0:
            return False, "quote not found on cited page"
        pos = i + len(fragment)
    return True, "quote found on cited page"


def verify_claim(claim: Claim, pages: dict[str, str]) -> Claim:
    if claim.source_url not in pages:
        return claim.model_copy(update={"verified": False, "note": "cited page was not fetched"})
    found, note = find_quote(claim.quote, pages[claim.source_url])
    return claim.model_copy(update={"verified": found, "note": note})


def verify_price(plan: PricePlan, pages: dict[str, str]) -> PricePlan:
    if plan.source_url not in pages:
        return plan.model_copy(update={"verified": False, "note": "cited page was not fetched"})
    found, note = find_quote(plan.quote, pages[plan.source_url])
    if found:
        # The numbers in the stated price must appear in the supporting quote.
        numbers = re.findall(r"\d+(?:[.,]\d+)?", plan.price)
        quote = normalize(plan.quote)
        if any(n not in quote for n in numbers):
            return plan.model_copy(update={"verified": False, "note": "price not in quote"})
    return plan.model_copy(update={"verified": found, "note": note})
