# Render a Report as Markdown with a numbered citation for every claim.

from app.research.schemas import Report

CATEGORY_ORDER = ["product", "target_customer", "positioning", "feature", "strength", "weakness", "other"]
CATEGORY_LABELS = {
    "product": "Product",
    "target_customer": "Target customer",
    "positioning": "Positioning",
    "feature": "Features",
    "strength": "Strengths",
    "weakness": "Weaknesses",
    "other": "Other",
}


def to_markdown(report: Report) -> str:
    refs: dict[str, int] = {}

    def cite(url: str) -> str:
        if url not in refs:
            refs[url] = len(refs) + 1
        return f"[{refs[url]}]"

    lines = [
        "# Competitive analysis",
        "",
        f"**Idea:** {report.idea}",
        "",
        f"_Generated {report.generated_at:%Y-%m-%d %H:%M} UTC with {report.model}. "
        f"{len(report.competitors)} competitors._",
        "",
    ]

    for comp in report.competitors:
        lines += [f"## {comp.name}", "", f"{comp.homepage_url} — {comp.why_competitor}", ""]

        if comp.pricing:
            lines += ["**Pricing**", "", "| Plan | Price | Source |", "| --- | --- | --- |"]
            for p in comp.pricing:
                lines.append(f"| {p.plan_name} | {p.price} | {cite(p.source_url)} |")
            lines.append("")
        else:
            lines += ["**Pricing:** not found on the fetched pages.", ""]

        for cat in CATEGORY_ORDER:
            claims = [c for c in comp.claims if c.category == cat]
            if not claims:
                continue
            lines += [f"**{CATEGORY_LABELS[cat]}**", ""]
            for c in claims:
                lines.append(f'- {c.text} {cite(c.source_url)}\n  > "{c.quote}"')
            lines.append("")

        if comp.dropped_items:
            lines += [f"_{comp.dropped_items} item(s) dropped for citing a page that wasn't fetched._", ""]

    lines += ["## Sources", ""]
    lines += [f"{n}. {url}" for url, n in refs.items()]
    return "\n".join(lines) + "\n"
