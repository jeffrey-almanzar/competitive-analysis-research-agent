# Competitive Analysis Research Agent

**Problem:** Anyone starting a business, product, or channel needs to know who they’re up against, what those competitors charge, and where the gaps are. Doing that properly takes days of searching and reading. Chatbots answer in seconds, but they invent details and rarely show where a claim came from, so you can’t trust the result enough to spend money on it.

**Solution:** Describe what you want to build, and the agent researches the market for you over several steps. It finds competitors, reads their websites, pricing, and reviews, and returns a structured report where every claim links to its source. It also points out where competitors are weak and how you could stand out. When it can’t back a claim with a source, it flags it instead of guessing.

**Impact:** For users: research that takes days now takes minutes, with sources they can check before making a decision.
For my career: it’s the most in-demand agent pattern, multi-step research with tools. Running it as an MCP server adds MCP practice, which appeared in 22% of postings and 32% of software engineering roles.

**Technologies:** Python, FastAPI, Pydantic, and Celery, Redis, Claude API, LangGraph, MCP, Exa Web Search API, PostgreSQL, Evals, Next.js, TypeScript, OpenTelemetry, Langfuse, AWS Fargate, AWS RDS, AWS SQS, Terraform, GitHub Actions, Docker


## Overview

The Competitive Analysis Research Agent is designed to automate the labor-intensive process of market research by utilizing a multi-step agent pattern. This project focuses on gathering competitive intelligence by identifying competitors, analyzing their websites, pricing, and customer reviews, and generating a structured report that provides actionable insights with verifiable sources. This approach mitigates the common issue of chatbot-generated content, which often lacks traceability and accuracy, by ensuring every claim is backed by a source. 

At a high level, the system involves several components working in concert: a FastAPI-based backend handling the request lifecycle, Celery for asynchronous task management, Redis for caching, and PostgreSQL for structured data storage. The research process leverages the Claude API for natural language processing, Exa Web Search API for web scraping, and LangGraph for data parsing and manipulation. The entire system is orchestrated under an MCP (Multi-Component Pattern) server to handle distributed components effectively, and is deployed on AWS using Fargate for container management and RDS for database services.

Key concepts include the use of FastAPI for building scalable APIs, Celery for distributed task execution, and OpenTelemetry for monitoring and tracing. This project also explores the use of Terraform for infrastructure as code, Docker for containerization, and GitHub Actions for CI/CD. The integration of these technologies demonstrates a comprehensive approach to building a modern, cloud-native application.

## Architecture

```
+----------------+     +----------------+     +----------------+     +----------------+
| FastAPI Server |<--->|    Celery      |<--->|    Redis       |<--->| PostgreSQL     |
+----------------+     +----------------+     +----------------+     +----------------+
        |                    |                     |                     |
        v                    v                     v                     v
+----------------+     +----------------+     +----------------+     +----------------+
| Claude API     |     | Exa Web Search |     | LangGraph      |     | MCP Server     |
+----------------+     +----------------+     +----------------+     +----------------+
```
- **FastAPI Server**: Handles incoming HTTP requests and routes them to the appropriate services.
- **Celery**: Manages asynchronous tasks, allowing for parallel processing of research tasks.
- **Redis**: Serves as a caching layer to optimize performance and reduce load on the database.
- **PostgreSQL**: Stores structured data such as competitor information and research reports.
- **Claude API**: Utilized for NLP tasks, such as parsing competitor data and generating insights.
- **Exa Web Search API**: Conducts web scraping to gather data from competitor websites.
- **LangGraph**: Processes and organizes scraped data into a coherent structure.
- **MCP Server**: Coordinates the interaction between distributed components and ensures data consistency.

## Running Locally

**Prerequisites:** Docker Desktop (with Docker Compose).

1) **Start the stack** (PostgreSQL, Redis, FastAPI server, Celery worker):
   ```bash
   docker compose up -d --build
   ```
   The `migrate` service applies database migrations (Alembic) before the API and worker start. The `src/` folder is mounted into the containers, so the API reloads automatically when you edit code. Restart the worker after changing the agent: `docker compose restart worker`.

2) **Run research through the API**:
   ```bash
   curl localhost:8000/health
   # -> {"status": "ok", "database": "ok", "redis": "ok"}

   curl -X POST localhost:8000/research \
     -H 'Content-Type: application/json' \
     -d '{"idea": "AI meeting notes for small law firms", "max_competitors": 4}'
   # -> 202 {"id": "...", "status": "queued", "links": {"self": ".../research/<id>"}, ...}

   curl localhost:8000/research/<id>
   # while running: {"status": "running", "progress": {"step": "researching", "completed": 2, "total": 4, ...}}
   # when done:     {"status": "succeeded", "report": {...}, "links": {"markdown": ".../report.md"}}

   curl localhost:8000/research/<id>/report.md    # the report as Markdown
   curl localhost:8000/research                    # recent runs
   ```
   Each POST starts a real research run, which costs about $0.35 for 2 competitors and more for larger reports. Progress moves through `queued → planning → finding_competitors → researching (n/N) → verifying → analyzing_gaps → done`, or ends in `failed` with an `error`. Reports are stored in PostgreSQL in the tables `reports`, `competitors`, `sources`, `claims`, `price_plans` and `market_gaps`. Every claim keeps its quote, source URL and verification result, and links to its stored source page. Fetched pages are cached in Redis for 24 hours (`PAGE_CACHE_TTL_S`, where `0` disables the cache), so re-running research on the same companies skips repeat Exa requests.

   Interactive API docs: http://localhost:8000/docs

3) **Use the web app**: open http://localhost:3001. Describe an idea and follow the run's progress. In the finished report, every claim has its source domain beside it; click a claim to see the quote it came from. Verified claims have a solid teal rule. Unconfirmed ones have a hatched amber rule and are listed separately. The frontend is Next.js 16 and TypeScript in `web/`. It calls the API through a `/api` proxy, so the browser never needs the backend's address.

4) **Connect Claude to the agent (MCP)**: the `mcp` service serves the agent as MCP tools at `http://localhost:8001/mcp`:
   - `start_research` starts a paid run.
   - `get_research` returns a run's status and can wait for it to finish.
   - `get_report` returns the report as Markdown or JSON.
   - `list_research` lists recent runs.
   - `list_competitors` lists a report's competitors with their verified pricing.

   For Claude Code:
   ```bash
   claude mcp add --transport http competitive-research http://localhost:8001/mcp
   ```
   For Claude Desktop, add this to `claude_desktop_config.json` (it starts the server over stdio inside Docker):
   ```json
   {
     "mcpServers": {
       "competitive-research": {
         "command": "docker",
         "args": ["compose", "-f", "/ABSOLUTE/PATH/TO/competitive-analysis-research-agent/docker-compose.yml",
                  "run", "--rm", "-T", "mcp", "python", "-m", "app.mcp_server", "--stdio"]
       }
     }
   }
   ```
   The server's instructions tell Claude to confirm with you before starting a run, and to reuse existing reports for ideas that have already been researched.

5) **Run competitor research from the CLI**:
   Copy `.env.example` to `.env` and fill in `ANTHROPIC_API_KEY` and `EXA_API_KEY`. Then:
   ```bash
   docker compose run --rm api python -m app.research "AI meeting notes for small law firms"
   ```
   It prints a Markdown report and saves `.md` and `.json` copies to `src/reports/`. The agent is a LangGraph graph (`plan → find_competitors → research_competitor ×N in parallel → verify → analyze_gaps`). Each claim and price comes with its source URL and a verbatim quote. A claim counts as verified only if code finds its quote on the cited page. Anything that fails is listed under _Flagged_, and the market-gap analysis may cite only verified claims. Options: `--max-competitors N`, `-v`.

   Run the offline tests (no API keys needed):
   ```bash
   docker compose run --rm api python -m pytest -q tests
   ```

6) **Tracing (self-hosted Langfuse)**:
   ```bash
   ./scripts/init-env.sh                 # one time: random local secrets in .env
   docker compose --profile tracing up -d
   ```
   Open http://localhost:3000 and log in with `LANGFUSE_INIT_USER_EMAIL` / `LANGFUSE_INIT_USER_PASSWORD` from `.env`. Each research run appears as one trace, made of graph-node spans, Claude generations (with token usage) and Exa tool calls. Without the `tracing` profile running, tracing turns itself off.

7) **Evals**:
   ```bash
   docker compose run --rm api python -m evals.run_eval --cases meal-kits,error-monitoring
   docker compose run --rm api python -m evals.run_eval            # all cases in src/evals/cases.toml
   ```
   This runs the real agent on each case and scores it on four measures:
   - **Citation support** (headline): share of verified claims whose quote actually backs them up, judged by Claude Sonnet 5.5.
   - **Quote found rate**: share of claims whose quote appears on the cited page. 1 minus this is the flag rate.
   - **Competitor recall**: share of each case's expected competitors that the report found.
   - **Gap grounding**: share of market gaps backed by verified evidence.

   The runner also records cost, tokens, latency and Exa requests. Results go to `.claude/hillclimb/research-report/baseline/`. The first run, and any run after the eval code changes, must add `--approve-harness`.

8) **View logs / stop**:
   ```bash
   docker compose logs -f api worker
   docker compose down
   ```

## Local Environment (Cloud Simulation)

To simulate the AWS environment locally, start LocalStack using the optional `aws` profile.

1) **Emulated Services**: AWS Fargate (ECS), RDS, SQS
2) **Start LocalStack**:
   ```bash
   docker compose --profile aws up -d
   ```
3) **Deploy Terraform on LocalStack**:
   ```bash
   cd src/infra
   terraform init
   terraform apply -var 'endpoint_url=http://localhost:4566'
   ```
4) **Configure Application**:
   Set environment variables to point to LocalStack endpoints:
   ```bash
   export AWS_ENDPOINT_URL=http://localhost:4566
   ```
5) **Verify Setup**:
   Use LocalStack CLI to check resources:
   ```bash
   awslocal ecs list-clusters
   awslocal rds describe-db-instances
   ```

## Cloud Deployment

Deploying to AWS uses the same Terraform configuration used for LocalStack. Here are the steps:

1) **Update Terraform Configuration**: Change the provider configuration to use real AWS credentials and region.
   ```hcl
   provider "aws" {
     region = "us-west-2"
     access_key = "<YOUR_ACCESS_KEY>"
     secret_key = "<YOUR_SECRET_KEY>"
   }
   ```
2) **Deploy**:
   ```bash
   cd src/infra
   terraform init
   terraform apply
   ```
3) **Post-Deployment Checklist**:
   - Ensure all ECS tasks are running without errors.
   - Check RDS instance accessibility.
   - Verify SQS queues are correctly configured.

## Load Testing

k6 load-tests the API's read paths (`/health`, `GET /research`, `GET /research/{id}`).

1) **Tool**: k6
2) **Scenario**: Ramp-up to 100 VUs over 1 minute, sustain for 5 minutes
3) **Execution**:
   ```bash
   RUN_ID=<an existing run id> k6 run loadtest/k6.js
   ```
   The script deliberately never calls `POST /research`. Every POST queues a real research run that spends Claude and Exa credits, so load-testing it against real keys would run up a large bill.
4) **Observing Results**:
   Use OpenTelemetry to collect and visualize metrics in Grafana.
   - Ensure OpenTelemetry is configured to export metrics to Prometheus.
   - Visualize in Grafana dashboard.

## Target Metrics

| Metric | Target | How to Measure |
| --- | --- | --- |
| Target QPS / RPS | 1,000 sustained req/s | Measured using k6 and OpenTelemetry metrics exported to Prometheus. |
| p50 / p95 / p99 latency | p99 < 300ms | Latency is measured during load tests with k6 and monitored using OpenTelemetry. |
| Error rate | < 0.1% | Error rate is tracked by monitoring HTTP error responses during load tests. |
| Saturation point | Degradation starting at ~2,500 req/s | Identified during load tests by observing latency spikes and error rates. |

## Testing (Unit / Integration)

Unit and integration tests are crucial to ensure the reliability of the Competitive Analysis Research Agent.

- **Unit Tests**: Focus on individual functions, especially those interacting with external APIs.
  ```python
  def test_parse_competitor_data():
      raw_data = "..."
      parsed_data = parse_competitor_data(raw_data)
      assert parsed_data is not None
  ```

- **Integration Tests**: Test the complete flow from API request to data retrieval and report generation.
  ```python
  def test_research_workflow(client):
      response = client.post('/research', json={'query': 'AI tools'})
      assert response.status_code == 200
      assert 'task_id' in response.json()
  ```

## Technical Challenges

### Data Consistency in Distributed Systems

**Why it's hard:** Ensuring data consistency across multiple services and asynchronous tasks can be challenging, especially when dealing with eventual consistency models.

**How it's solved:** This project uses Redis as a centralized cache to maintain interim data states, and Celery ensures task idempotency by checking task completion before proceeding.

### Asynchronous Task Management

**Why it's hard:** Managing and scaling asynchronous tasks without overloading the system is complex.

**How it's solved:** Celery is configured with worker pools and rate limiting to control task execution and prevent bottlenecks.

### Source Verification

**Why it's hard:** Automatically verifying the credibility of sources and linking them correctly adds complexity.

**How it's solved:** Each claim is linked to its source by storing source metadata in PostgreSQL, and claims without verifiable sources are flagged during processing.


## Takeaways

- Implemented a scalable FastAPI application using asynchronous task management with Celery.
- Deployed a cloud-native application using Terraform and AWS Fargate.
- Conducted load testing with k6 and monitored performance with OpenTelemetry and Grafana.
- Ensured data consistency and source verification in a distributed system using Redis and PostgreSQL.

## Learning Path

### FastAPI

FastAPI is a modern, fast (high-performance), web framework for building APIs with Python 3.6+ based on standard Python type hints.

1. Understand the basics of FastAPI and its asynchronous capabilities.
2. Build a simple API with endpoints and learn how to handle requests and responses.
3. Integrate Pydantic for data validation and serialization.
4. Implement middleware and dependency injection.
5. Explore advanced features like WebSockets and background tasks.


- https://fastapi.tiangolo.com/
- https://www.udemy.com/course/fastapi-the-complete-guide/

### OpenTelemetry

OpenTelemetry provides a single set of APIs, libraries, agents, and instrumentation to capture distributed traces and metrics from your applications.

1. Learn the basics of distributed tracing and metrics.
2. Set up OpenTelemetry in a Python application.
3. Instrument your application to capture traces and metrics.
4. Export data to Prometheus and visualize in Grafana.
5. Explore the use of OpenTelemetry with other languages and frameworks.

- https://opentelemetry.io/docs/
- https://www.youtube.com/watch?v=5kBfF8j0XfI
