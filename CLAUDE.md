# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **technical assessment** for Xertica to build a multi-agent AI compliance system for fraud alert processing. The goal: reduce alert resolution from 4.2 hours to <30 minutes while maintaining full regulatory audit trails (UIAF/Colombia, CNBV/Mexico, SBS/Peru).

Key constraint: All personal data processing must stay in Google Cloud (region: `us-central1`). No external API calls with customer data without anonymization.

## Expected Project Structure

```
compliance_agent/
├── agents/
│   ├── investigador.py      # Agent 1: BigQuery + GCS data gathering
│   ├── risk_analyzer.py     # Agent 2: 1-10 risk scoring with justification
│   └── decision_agent.py   # Agent 3: escalate/dismiss/request-info decision
├── graph/
│   └── pipeline.py          # LangGraph or Google ADK orchestration
├── tools/
│   ├── bigquery_tools.py    # BigQuery tools (mocks acceptable)
│   └── gcs_tools.py         # PDF extraction from GCS (mocks acceptable)
├── api/
│   └── main.py              # FastAPI endpoints
├── observability/
│   └── langfuse_config.py   # Langfuse tracing config
├── tests/
├── terraform/               # IaC for Cloud Run, GCS, Cloud SQL/AlloyDB, IAM
├── .github/workflows/       # CI/CD with 60% test coverage gate
├── docker-compose.yml
└── README.md
```

## Tech Stack

- **Agent orchestration:** LangGraph
- **LLM:** Vertex AI (Gemini) — justify alternatives
- **API:** FastAPI
- **Observability:** Langfuse (traces, latency, cost per alert)
- **Vector store:** pgvector
- **Infrastructure:** GCP — Cloud Run, GCS, BigQuery, Cloud SQL/AlloyDB
- **IaC:** Terraform
- **CI/CD:** GitHub Actions
- **Formatter:** Black

## Development Commands

No Makefile or pyproject.toml exists yet. When creating:

```bash
# Activate virtual environment
source .venv/bin/activate

# Run locally
docker-compose up

# Run tests (CI gate: 60% coverage minimum)
pytest --cov=compliance_agent --cov-fail-under=60

# Lint
ruff check .

# Format
ruff format .
```

## Deliverables Checklist

1. **Agentic code** — 3 agents runnable with `docker-compose up`. BigQuery/GCS mocks are explicitly acceptable.
2. **RAG** — Hybrid retrieval (dense embeddings + BM25 sparse). At least 5 example regulatory documents. Evaluation notebook with RAG quality metrics.
3. **CTO document** — Max 2-page PDF/Markdown for CFO audience: cost model, ROI projection (4.2h → 30min), break-even, primary risk + mitigation.
4. **Terraform + CI/CD** — Cloud Run, GCS bucket, Cloud SQL/AlloyDB, IAM. GitHub Actions workflow that fails below 60% test coverage.
5. **README** — RAG evaluation metrics (with formulas), open production question response (min 400 words), "Mi flujo con AI" section.

## Architecture Notes

- Agents work both in parallel and in sequence: Investigador → Risk Analyzer → Decision Agent
- Every decision must produce a human-readable audit trail (regulatory requirement)
- RAG chunking strategy must be justified (chunk size, overlap rationale)
- Decision Agent must cite specific regulations with confidence levels and step-by-step reasoning
- Production observability must cover: p95 pipeline latency, cost per alert, human escalation rate, LLM drift detection

## Open Production Scenario (README required)

After 3 weeks in production, the system sub-escalates PEP (Politically Exposed Persons) alerts — resolving them automatically when regulation requires mandatory human escalation. The README must address (min 400 words):
1. How to detect this before an auditor finds it (day-1 monitoring)
2. Most likely root cause (prompt failure, RAG gap, decision agent design)
3. Concrete technical fix
4. Architectural changes to prevent recurrence


## Workflow Orchestration

### 1. Plan Node Default
* Enter plan mode for ANY non-trivial task (3+ steps or architectural decisions)
* If something goes sideways, **STOP** and re-plan immediately – don't keep pushing
* Use plan mode for verification steps, not just building
* Write detailed specs upfront to reduce ambiguity

### 2. Subagent Strategy
* Use subagents liberally to keep main context window clean
* Offload research, exploration, and parallel analysis to subagents
* For complex problems, throw more compute at it via subagents
* One task per subagent for focused execution

### 3. Self-Improvement Loop
* After ANY correction from the user: update `tasks/lessons.md` with the pattern
* Write rules for yourself that prevent the same mistake
* Ruthlessly iterate on these lessons until mistake rate drops
* Review lessons at session start for relevant project

### 4. Verification Before Done
* Never mark a task complete without proving it works
* Diff behavior between main and your changes when relevant
* Ask yourself: "Would a staff engineer approve this?"
* Run tests, check logs, demonstrate correctness

### 5. Demand Elegance (Balanced)
* For non-trivial changes: pause and ask "is there a more elegant way?"
* If a fix feels hacky: "Knowing everything I know now, implement the elegant solution"
* Skip this for simple, obvious fixes – don't over-engineer
* Challenge your own work before presenting it

### 6. Autonomous Bug Fixing
* When given a bug report: just fix it. Don't ask for hand-holding
* Point at logs, errors, failing tests – then resolve them
* Zero context switching required from the user
* Go fix failing CI tests without being told how

---

## Task Management

1. **Plan First**: Write plan to `tasks/todo.md` with checkable items
2. **Verify Plan**: Check in before starting implementation
3. **Track Progress**: Mark items complete as you go
4. **Explain Changes**: High-level summary at each step
5. **Document Results**: Add review section to `tasks/todo.md`
6. **Capture Lessons**: Update `tasks/lessons.md` after corrections

---

## Core Principles

* **Simplicity First**: Make every change as simple as possible. Impact minimal code.
* **No Laziness**: Find root causes. No temporary fixes. Senior developer standards.
* **Minimal Impact**: Changes should only touch what's necessary. Avoid introducing bugs.

## Architecture

- Follow **Clean Architecture** principles strictly: separate layers for entities, use cases, interface adapters, and frameworks/drivers.
- Dependencies must point inward — outer layers depend on inner layers, never the reverse.
- Each layer must communicate through **well-defined interfaces** (abstractions, not concretions).

## Dependency Injection

- **Dependency Injection is mandatory** for every module. No module should instantiate its own dependencies directly.
- All dependencies must be injected through constructors or dedicated DI containers.
- Prefer interface-based injection to keep modules decoupled and testable.

## Interfaces

- Every service, repository, and external integration must have a clearly defined interface.
- Implementations must be swappable without modifying consuming code.
- Keep interfaces minimal and focused (Interface Segregation Principle).

## AWS Services

- When working with AWS services (SDK, CDK, Lambda, S3, DynamoDB, SQS, etc.), **always use Context7 MCP to fetch up-to-date documentation** before writing or modifying code.
- Do not rely on cached or assumed knowledge for AWS APIs — resolve via Context7 first.

## Terraform

- All infrastructure must be defined as code using **Terraform**.
- When writing or modifying Terraform configurations, **always use Context7 MCP to fetch up-to-date Terraform documentation** (providers, resources, data sources).
- Follow Terraform best practices: use modules, variables, outputs, and remote state.

## General

- Write clean, testable, and maintainable code.
- Prefer composition over inheritance.
- Keep functions and methods small and focused on a single responsibility.
