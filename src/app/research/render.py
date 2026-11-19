# Render a Report as Markdown with a numbered citation for every claim.
# Verified items are listed normally; items whose quote couldn't be found on the
# cited page are shown separately under "Flagged".

from app.research.schemas import Claim, Report

CATEGORY_ORDER = [
    "product", "target_customer", "positioning", "feature",
    "strength", "weakness", "customer_praise", "customer_complaint", "other",
]
CATEGORY_LABELS = {
    "product": "Product",
    "target_customer": "Target customer",
    "positioning": "Positioning",
    "feature": "Features",
    "strength": "Strengths",
    "weakness": "Weaknesses",
    "customer_praise": "What customers praise",
    "customer_complaint": "What customers complain about",
    "other": "Other",
}


def _pct(n: int, total: int) -> str:
    return f"{n}/{total} ({round(100 * n / total)}%)" if total else "0/0"


def to_markdown(report: Report) -> str:
    refs: dict[str, int] = {}

    def cite(url: str) -> str:
        if url not in refs:
            refs[url] = len(refs) + 1
        return f"[{refs[url]}]"

    s = report.stats
    lines = [
        "# Competitive analysis",
        "",
        f"**Idea:** {report.idea}",
        "",
        f"_Generated {report.generated_at:%Y-%m-%d %H:%M} UTC with {report.model}. "
        f"{len(report.competitors)} competitors._",
        "",
        f"**Source check:** {_pct(s.claims_verified, s.claims_total)} claims and "
        f"{_pct(s.prices_verified, s.prices_total)} prices were confirmed by finding the quote "
        "on the cited page. The rest are listed under _Flagged_.",
        "",
    ]

    # Index claims and prices by ID so gaps can show their evidence.
    by_id: dict[str, tuple[str, str, str, str]] = {}
    for comp in report.competitors:
        for c in comp.claims:
            by_id[c.id] = (comp.name, c.text, c.quote, c.source_url)
        for p in comp.pricing:
            by_id[p.id] = (comp.name, f"{p.plan_name}: {p.price}", p.quote, p.source_url)

    supported = [g for g in report.gaps if g.supported]
    unsupported = [g for g in report.gaps if not g.supported]
    if supported:
        lines += ["## Market gaps and how to stand out", ""]
        for n, g in enumerate(supported, 1):
            lines += [f"### {n}. {g.title}", "", g.description, "", f"**How to stand out:** {g.how_to_stand_out}", "", "Evidence:"]
            for eid in g.evidence_ids:
                name, text, _quote, url = by_id[eid]
                lines.append(f"- {name}: {text} {cite(url)}")
            lines.append("")
    if unsupported:
        lines += ["**Flagged gaps** (no verified evidence; treat as unconfirmed):", ""]
        lines += [f"- {g.title}: {g.description}" for g in unsupported]
        lines.append("")

    for comp in report.competitors:
        lines += [f"## {comp.name}", "", f"{comp.homepage_url} — {comp.why_competitor}", ""]

        prices = [p for p in comp.pricing if p.verified]
        if prices:
            lines += ["**Pricing**", "", "| Plan | Price | Source |", "| --- | --- | --- |"]
            lines += [f"| {p.plan_name} | {p.price} | {cite(p.source_url)} |" for p in prices]
            lines.append("")
        else:
            lines += ["**Pricing:** no verified pricing found on the fetched pages.", ""]

        for cat in CATEGORY_ORDER:
            claims = [c for c in comp.claims if c.category == cat and c.verified]
            if claims:
                lines += [f"**{CATEGORY_LABELS[cat]}**", ""]
                lines += [_claim_line(c, cite) for c in claims]
                lines.append("")

        flagged = [c for c in comp.claims if not c.verified]
        flagged_prices = [p for p in comp.pricing if not p.verified]
        if flagged or flagged_prices:
            lines += ["**Flagged** (could not confirm against the source; don't rely on these):", ""]
            lines += [f"- {p.plan_name}: {p.price} {cite(p.source_url)} — _{p.note}_" for p in flagged_prices]
            lines += [f"- {c.text} {cite(c.source_url)} — _{c.note}_" for c in flagged]
            lines.append("")

    if report.errors:
        lines += ["## Problems during research", ""]
        lines += [f"- {e}" for e in report.errors]
        lines.append("")

    lines += ["## Sources", ""]
    lines += [f"{n}. {url}" for url, n in refs.items()]
    return "\n".join(lines) + "\n"


def _claim_line(c: Claim, cite) -> str:
    return f'- {c.text} {cite(c.source_url)}\n  > "{c.quote}"'
