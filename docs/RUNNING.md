# Running the project

Operational details behind the [README](../README.md): the local stack, every interface, tracing, evals and the AWS deployment.

## Contents

- [Prerequisites](#prerequisites)
- [Local stack](#local-stack)
- [HTTP API](#http-api)
- [Web app](#web-app)
- [MCP server (Claude Desktop / Claude Code)](#mcp-server-claude-desktop--claude-code)
- [CLI](#cli)
- [Tests](#tests)
- [Tracing with Langfuse](#tracing-with-langfuse)
- [Evals](#evals)
- [Deploying to AWS](#deploying-to-aws)
- [Configuration](#configuration)

## Prerequisites

- Docker Desktop with Docker Compose.
- An Anthropic API key and an Exa API key, both in `.env`:

```bash
cp .env.example .env    # then set ANTHROPIC_API_KEY and EXA_API_KEY
```

Every research run calls the Claude API and Exa and costs money. The tests and the read-only endpoints don't.

## Local stack

```bash
docker compose up -d --build
```

| Service | Port | What it does |
| --- | --- | --- |
| `web` | 3001 | Next.js frontend |
| `api` | 8000 | FastAPI: queue runs, poll progress, read reports |
| `worker` | — | Celery worker that runs the LangGraph agent |
| `mcp` | 8001 | MCP server (streamable HTTP at `/mcp`) |
| `postgres` | 5432 | Reports, competitors, claims, sources, price plans and market gaps |
| `redis` | 6379 | Celery broker, plus a 24-hour cache of fetched pages |
| `migrate` | — | Runs `alembic upgrade head` once, before `api` and `worker` start |

The `src/` and `web/` folders are mounted into the containers, so the API and the web app reload when you edit code. Restart the worker after changing the agent: `docker compose restart worker`.

```bash
docker compose logs -f api worker
docker compose down
```

## HTTP API

```bash
curl localhost:8000/health
# {"status": "ok", "database": "ok", "redis": "ok"}

curl localhost:8000/models
# models with capability hints, token prices and estimated cost per competitor

curl -X POST localhost:8000/research \
  -H 'Content-Type: application/json' \
  -d '{"idea": "AI meeting notes for small law firms", "max_competitors": 4, "model": "claude-haiku-5-5"}'
# 202 {"id": "...", "status": "queued", "links": {"self": ".../research/<id>"}}

curl localhost:8000/research/<id>
# running: {"status": "running", "progress": {"step": "researching", "completed": 2, "total": 4}}
# done:    {"status": "succeeded", "report": {...}, "links": {"markdown": ".../report.md"}}

curl localhost:8000/research/<id>/report.md
curl localhost:8000/research
```

- **`model`:** one of `claude-haiku-5-5` (the default and cheapest), `claude-sonnet-5-5` or `claude-opus-5-5`.
- **Progress steps:** `queued → planning → finding_competitors → researching (n/N) → verifying → analyzing_gaps → done`, or `failed` with an `error`.

Interactive docs are at http://localhost:8000/docs.

## Web app

Open http://localhost:3001.

1. Describe an idea, then pick a model and a number of competitors. The hint under the controls shows the model's strengths and the estimated cost.
2. Follow the run's progress on the next page.
3. In the report, click any claim to see the verbatim quote and the page it came from.

The browser calls `/api/*`, which Next.js forwards to the API, so the browser never needs the API's address.

## MCP server (Claude Desktop / Claude Code)

| Tool | Read-only | What it does |
| --- | --- | --- |
| `start_research` | no | Queues a run. It costs money, so the server's instructions tell Claude to confirm with you first. |
| `get_research` | yes | Status and progress. Can wait up to 120 s for a run to finish. |
| `get_report` | yes | The full report, as Markdown or JSON. |
| `list_research` | yes | Recent runs. |
| `list_competitors` | yes | Competitors with their verified pricing and claim counts. |

**Claude Code** (HTTP):

```bash
claude mcp add --transport http competitive-research http://localhost:8001/mcp
```

**Claude Desktop** (stdio inside the running container). Add this to `~/Library/Application Support/Claude/claude_desktop_config.json`, then restart Claude Desktop:

```json
{
  "mcpServers": {
    "competitive-research": {
      "command": "/usr/local/bin/docker",
      "args": ["compose", "-f", "/ABSOLUTE/PATH/TO/competitive-analysis-research-agent/docker-compose.yml",
               "exec", "-T", "mcp", "python", "-m", "app.mcp_server", "--stdio"]
    }
  }
}
```

Use the full path to `docker` (find it with `which docker`). Claude Desktop doesn't load your shell's `PATH`.

## CLI

```bash
docker compose run --rm api python -m app.research "AI meeting notes for small law firms" \
  --model claude-haiku-5-5 --max-competitors 4
```

This prints the Markdown report and saves `.md` and `.json` copies to `src/reports/`.

## Tests

```bash
docker compose run --rm api python -m pytest -q tests
```

The 38 tests run offline, with Claude and Exa faked and SQLite in place of PostgreSQL. They need no API keys and cost nothing.

## Tracing with Langfuse

```bash
./scripts/init-env.sh                     # one time: random local secrets in .env
docker compose --profile tracing up -d    # self-hosted Langfuse at http://localhost:3000
```

Log in with `LANGFUSE_INIT_USER_EMAIL` and `LANGFUSE_INIT_USER_PASSWORD` from `.env`. Each run is one trace, made of a span per graph node, a generation per Claude call (with token usage) and a tool span per Exa request. When Langfuse isn't running, tracing turns itself off.

## Evals

```bash
docker compose run --rm api python -m evals.run_eval --cases meal-kits,error-monitoring
docker compose run --rm api python -m evals.run_eval                       # all 15 cases
docker compose run --rm api python -m evals.run_eval --model claude-haiku-5-5 --variant v1
```

- **Cost:** a full run with Opus 5.5 costs about $16 (agent plus judge).
- **Output:** results are written to `.claude/hillclimb/research-report/<variant>/`.
- **Approval:** the first run, and any run after the eval code changes, needs `--approve-harness`.

Metrics are defined in [metrics.md](../.claude/hillclimb/research-report/metrics.md).

## Deploying to AWS

The Terraform configuration lives in `infra/aws/`. `scripts/aws.sh` wraps the full deploy, demo and teardown lifecycle.

```bash
scripts/aws.sh plan       # shows the 29 resources; saves the plan
scripts/aws.sh apply      # creates exactly that plan, builds and pushes arm64 images, starts services
scripts/aws.sh status     # service health and the URL
scripts/aws.sh allow-ip   # your public IP changed? re-point the load balancer rule
scripts/aws.sh destroy    # deletes everything
```

- **Credentials:** the script uses your AWS credentials, and reads the Anthropic and Exa keys from `.env`.
- **Access:** the load balancer accepts traffic only from your current public IP, because the app has no login.
- **Budget alert:** set `BUDGET_EMAIL=you@example.com` before `plan` to add a monthly cost alert.
- **Cost:** about $0.15/hour while running, in us-east-2 at list prices.
- **State file:** the Terraform state holds secrets. It stays local and is git-ignored.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | — | Claude API |
| `EXA_API_KEY` | — | Exa search and page fetching |
| `CLAUDE_MODEL` | `claude-haiku-5-5` | Model used when a request doesn't choose one |
| `DATABASE_URL` | local Postgres | SQLAlchemy URL (`postgresql+psycopg://…`) |
| `REDIS_URL` | `redis://localhost:6379/0` | Celery broker and page cache |
| `PAGE_CACHE_TTL_S` | `86400` | Fetched-page cache lifetime; `0` disables it |
| `LANGFUSE_HOST`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY` | — | Tracing; leave unset to disable |
| `RESEARCH_SOFT_TIME_LIMIT_S` | `900` | Per-run time limit in the worker |
