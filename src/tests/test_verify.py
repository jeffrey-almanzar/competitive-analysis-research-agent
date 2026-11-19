from app.research.verify import find_quote

PAGE = """# Pricing

**Pro** — $30/user/month, billed annually.
Teams get “unlimited” recordings and [SSO](https://acme.com/sso) support.
Customers love it. Setup is quick and painless for most firms."""


def test_exact_quote():
    assert find_quote("$30/user/month, billed annually", PAGE)[0]


def test_ignores_markdown_links_bold_and_smart_quotes():
    assert find_quote('Teams get "unlimited" recordings and SSO support.', PAGE)[0]
    assert find_quote("Pro - $30/user/month", PAGE)[0]


def test_case_and_whitespace_insensitive():
    assert find_quote("SETUP IS   QUICK and painless", PAGE)[0]


def test_ellipsis_fragments_must_appear_in_order():
    assert find_quote("Customers love it... painless for most firms", PAGE)[0]
    assert not find_quote("painless for most firms... Customers love it", PAGE)[0]


def test_paraphrase_is_rejected():
    assert find_quote("Setup is fast and easy for most firms", PAGE) == (False, "quote not found on cited page")


def test_too_short_is_rejected():
    assert find_quote("Pro", PAGE) == (False, "quote too short to verify")


def test_html_entities_in_quote_match_raw_page():
    page = "Dietitian coaching & support. Calories: 350 - 700, Sodium: < 700 mg"
    assert find_quote("Dietitian coaching &amp; support", page)[0]
    assert find_quote("Calories: 350 - 700, Sodium: &lt; 700 mg", page)[0]
