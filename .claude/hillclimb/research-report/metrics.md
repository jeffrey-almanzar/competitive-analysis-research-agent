# Research-report eval

Runner: `src/evals/run_eval.py` · Cases: `src/evals/cases.toml` (15 human-reviewed ideas) · Grader: `src/evals/grading.py`

## Metrics (0–1, higher is better)

| Metric | What it measures |
| --- | --- |
| **citation_support** (headline) | Share of verified claims and prices whose quote, on its own, backs the whole claim. Judged by claude-sonnet-5-5 as supported, partial or unsupported; only "supported" counts. |
| verified_rate | Share of claims whose quote was found on the cited page (code check). 1 − flag rate. |
| competitor_recall | Share of the case's expected competitors that the report selected, matched by domain or name. |
| gap_grounding | Share of market gaps backed by at least one verified claim. |

The judge passed a known-answer check: it rejected an empty quote, "I don't know" and an off-topic quote, marked an overreaching claim "partial", and passed an exact match.

## Baseline (2026-11-19, claude-opus-5-5, max 6 competitors, 15 cases × 1 rep)

| Metric | Mean | 95% CI | Per-case SD |
| --- | --- | --- | --- |
| citation_support | 0.555 | ±0.021 | 0.042 |
| verified_rate | 0.989 | ±0.008 | 0.016 |
| competitor_recall | 0.568 | ±0.145 | 0.287 |
| gap_grounding | 1.000 | ±0.000 | 0.000 |

Cost per case: agent median $0.94 (range $0.76–$1.14), judge median $0.12. Full run: $15.66, 10 minutes at concurrency 3. Latency per report: median 88 s (range 65–115 s).

**What it can detect:**
- **citation_support:** changes of about 3 points or more at this size.
- **competitor_recall:** only changes of about 15 points or more. To detect smaller ones, add reps (`--reps 2` or `--reps 3`) or more cases.

## What the baseline shows

- **Claims overreach their quotes.** About 45% of verified claims are "partial": the claim bundles extra facts beyond the one short quote cited. For example, the quote "Sentry supports over 100 programming languages and frameworks" was cited for a claim that added "including iOS and Android".
- **Recall misses market leaders.** The agent picks small long-tail vendors over the obvious players. For example:
  - meeting-notes-sales found 0/4: Gong, Otter, Fireflies and Fathom were all missed.
  - Ramp, Expensify, Wave, QuickBooks, Clio and HelloFresh were also missed.
  - Exa's company search surfaces small companies, and selection doesn't favour the leaders.
- **One duplicate competitor:** freelance-marketplace selected both "fiverr" and "Fiverr Pro".
