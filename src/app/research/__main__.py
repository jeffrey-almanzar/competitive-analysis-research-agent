# CLI: python -m app.research "your business idea"

import argparse
import logging
import re
import sys
from pathlib import Path

from app.research.pipeline import run_research
from app.research.render import to_markdown


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60] or "report"


def main() -> int:
    parser = argparse.ArgumentParser(description="Research competitors for a business idea.")
    parser.add_argument("idea", help="What you want to build, in a sentence or two.")
    parser.add_argument("--max-competitors", type=int, default=6)
    parser.add_argument("--out-dir", default="reports", help="Where to write the .json and .md report.")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    # Keep HTTP client noise out of the default output.
    for noisy in ("httpx", "httpx2", "anthropic"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    report = run_research(args.idea, max_competitors=args.max_competitors)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{report.generated_at:%Y%m%d-%H%M%S}-{_slug(args.idea)}"
    (out_dir / f"{stem}.json").write_text(report.model_dump_json(indent=2))
    markdown = to_markdown(report)
    (out_dir / f"{stem}.md").write_text(markdown)

    print(markdown)
    print(f"Saved {out_dir / stem}.json and .md", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
