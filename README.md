# OmniBrain – Agentic Multi-Modal RAG Orchestrator

OmniBrain is a production-ready, multi-agent Retrieval-Augmented Generation (RAG) platform. A LangGraph-orchestrated Supervisor routes natural-language questions to specialized Retrieval, Vision, and SQL agents, synthesizes a single citation-grounded answer, and validates it through a guardrails/evaluation/observability layer — all served by a FastAPI backend with a Streamlit UI.

---

## 🚀 Live Demo

This project runs as two local services (FastAPI backend + Streamlit UI) rather than a single hosted app, so there is no public URL to click — run it on your own machine in under a minute:

```bash
git clone https://github.com/harshakurada/OmniBrain-Enterprise-Intelligence-Platform.git
cd OmniBrain-Enterprise-Intelligence-Platform
pip install -r requirements.txt
cp .env.example .env   # then set a real OPENAI_API_KEY inside .env

python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 &
streamlit run frontend/app.py
```

| | |
|---|---|
| **Streamlit UI** | http://127.0.0.1:8501 |
| **API docs (Swagger)** | http://127.0.0.1:8000/docs |
| **Health check** | http://127.0.0.1:8000/api/v1/health |

Try it: **Upload Documents** → upload a PDF → **Orchestrator Chat** → ask a question about it → watch the live multi-agent trace and grounded, cited answer. See [Section 8](#8-docker-deployment) for a one-command Docker Compose deployment instead.

---

## 1. Architecture Overview

### Module map

| Module | Capability |
|---|---|
| 1 | FastAPI/Streamlit scaffold, SQLite persistence, config, logging, health check |
| 2 | PDF ingestion pipeline: parsing, chunking, OpenAI embeddings, vector indexing (Qdrant, falls back to local FAISS) |
| 3 | LangGraph multi-agent orchestrator: Supervisor, Retrieval Agent, Response Synthesizer |
| 4 | Vision Intelligence: image/table extraction, Vision Agent (GPT-4o), multi-modal retrieval |
| 5 | SQL Intelligence: Text-to-SQL Agent, read-only-enforced schema discovery/execution |
| 6 | Guardrails (prompt-injection/jailbreak detection, response grounding), Evaluation, Observability (metrics, request tracing) |
| 7 | Production hardening: startup validation, Docker, connection reuse, structured logging, deployment docs |

### Request flow (`POST /api/v1/orchestrate`)

```
START
  │
  ▼
guardrails_input  ──(blocked)──▶ guardrails_output ──▶ END
  │ (passed)
  ▼
supervisor  (classifies intent, decides which agents to invoke)
  │
  ├──▶ retrieval_agent   (semantic search: text + image + table chunks)
  ├──▶ vision_agent      (multi-modal search restricted to image/table chunks)
  └──▶ sql_agent         (Text-to-SQL over the app's own metadata DB)
  │        (agents run in parallel, fan back in)
  ▼
synthesizer  (merges results, dedupes, generates one grounded answer + citations)
  │
  ▼
guardrails_output  (scores grounding/confidence)
  │
  ▼
END
```

Conversation state and execution history persist per `thread_id` via LangGraph's `MemorySaver` checkpointer. Every run's execution trace, retrieval statistics, and a full evaluation report are recorded automatically (see [Observability](#7-observability--evaluation)).

### Backend layering

```
backend/app/
├── api/            FastAPI routers + dependency-injection providers (deps.py)
├── agents/         LangGraph nodes, graph assembly, orchestrator entry point
├── guardrails/      Input/output safety checks (Module 6)
├── evaluation/      Automatic per-run evaluation reports (Module 6)
├── observability/   Request-id context, in-process metrics store (Module 6)
├── services/        Business logic: parsing, chunking, embeddings, vector store,
│                     vision analysis, Text-to-SQL, SQL execution
├── schemas/         Pydantic request/response DTOs (one file per feature area)
├── database/        SQLAlchemy engine/session setup, ORM models
├── config/          Centralized Pydantic Settings (env-driven)
└── core/            Exception handlers, logging setup, startup validation
```

Every service is constructed through `backend/app/api/deps.py`, FastAPI's dependency-injection layer — swap an implementation there (e.g. a different vector store) without touching callers.

---

## 2. Folder Structure

```text
OmniBrain/
├── backend/app/               FastAPI backend (see layering above)
├── frontend/app.py            Streamlit UI (Home, Dashboard, Upload, Search,
│                               SQL Intelligence, Orchestrator Chat, Observability, Settings)
├── tests/                     Pytest suite (one file per module/feature area)
├── storage/                   Runtime data: uploads, extracted assets, FAISS index (git-ignored)
├── logs/                      Rotating application logs (git-ignored)
├── .streamlit/config.toml     Streamlit deployment configuration
├── Dockerfile                 Backend production image (multi-stage, non-root)
├── Dockerfile.frontend        Frontend production image (lightweight dependency set)
├── docker-compose.yml         Full-stack orchestration with health checks + named volumes
├── requirements.txt           Backend dependencies
├── requirements-frontend.txt  Frontend-only dependencies (streamlit, httpx, dotenv)
├── .env.example                Full environment variable reference
└── pyproject.toml             Pytest/ruff configuration
```

---

## 3. Installation Guide

### Prerequisites
- Python 3.12
- An OpenAI API key (optional — the app runs and degrades gracefully without one; see [Troubleshooting](#9-troubleshooting))
- Docker & Docker Compose (only if deploying via containers)
- Qdrant (optional — falls back to a local FAISS index automatically if unreachable)

### Local setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env   # Windows: copy .env.example .env
# then edit .env and set OPENAI_API_KEY (and anything else you want to change)

# 3. Start the backend
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
# Swagger UI: http://127.0.0.1:8000/docs

# 4. Start the frontend (separate terminal)
streamlit run frontend/app.py
# UI: http://127.0.0.1:8501
```

### Running tests

```bash
pytest
```

The suite (170 tests as of Module 7) runs entirely offline against deterministic fakes for the OpenAI/embedding/vision/SQL-generation calls — no API key or running Qdrant instance required.

---

## 4. Configuration Guide

All configuration is centralized in `backend/app/config/settings.py` (Pydantic `BaseSettings`), loaded from `.env`. See `.env.example` for the complete, grouped reference with defaults. Key groups:

| Group | Examples | Notes |
|---|---|---|
| General | `ENVIRONMENT`, `DEBUG`, `APP_VERSION` | `ENVIRONMENT` must be `development`/`staging`/`production`; validated at import time |
| Backend | `BACKEND_HOST`, `BACKEND_PORT`, `CORS_ORIGINS`, `UVICORN_WORKERS` | Keep `UVICORN_WORKERS=1` — see [Known Limitations](#10-known-limitations) |
| Database | `DATABASE_URL` | SQLite by default; any SQLAlchemy-supported URL works |
| Logging | `LOG_LEVEL`, `LOG_FORMAT`, `LOG_FILE_PATH`, `LOG_ROTATION` | `LOG_FORMAT=json` for log-aggregator-friendly structured logs |
| OpenAI | `OPENAI_API_KEY`, `OPENAI_MODEL`, `EMBEDDING_MODEL`, `LLM_REQUEST_TIMEOUT_SECONDS`, `LLM_MAX_RETRIES` | Every `ChatOpenAI` call across all agents is timeout/retry-bounded |
| Ingestion | `UPLOAD_DIR`, `ASSETS_DIR`, `MAX_FILE_SIZE_MB`, `DEFAULT_CHUNK_SIZE`, `DEFAULT_CHUNK_OVERLAP` | |
| Vector store | `QDRANT_HOST`, `QDRANT_PORT`, `FAISS_STORAGE_PATH`, `VECTOR_DIMENSION` | Auto-fallback: Qdrant → local FAISS |
| Vision | `VISION_MODEL`, `VISION_MIN_IMAGE_DIMENSION`, `VISION_MAX_IMAGES_PER_DOCUMENT` | |
| SQL | `SQL_MAX_ROWS` | Caps rows returned/read-only-enforced by the SQL Agent |
| Guardrails | `GUARDRAILS_ENABLED`, `GUARDRAIL_MAX_INPUT_LENGTH` | |
| Observability | `METRICS_HISTORY_SIZE`, `EVALUATION_HISTORY_SIZE` | Capped in-memory history sizes |

### Secrets handling
- `.env` is git-ignored (only `.env.example`, with placeholder values, is committed).
- In Docker, secrets are injected via `env_file:`/`environment:` in `docker-compose.yml` — never baked into the image.
- Startup validation (`backend/app/core/startup_validation.py`) warns (does not block) if `ENVIRONMENT=production` is combined with `DEBUG=true`, a wildcard `CORS_ORIGINS`, or a placeholder `OPENAI_API_KEY`.

---

## 5. API Usage

Full interactive documentation is always available at `/docs` (Swagger) and `/redoc`. Summary by feature area (all prefixed with `/api/v1`):

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Basic liveness + DB check |
| POST | `/documents/upload` | Ingest one or more PDFs (parse → chunk → embed → index) |
| GET | `/documents`, `/documents/{id}` | List / inspect ingested documents |
| GET | `/documents/{id}/assets`, `/documents/{id}/assets/{asset_id}/file` | Extracted images/tables + file download |
| POST | `/search` | Semantic search (multi-modal by default; filter via `chunk_types`) |
| POST | `/orchestrate` | Full multi-agent pipeline: guardrails → routing → agents → synthesis → guardrails |
| POST | `/vision/analyze` | Standalone image analysis |
| POST | `/vision/documents/{id}/process` | (Re)run visual asset processing for a document |
| GET | `/sql/tables`, `/sql/schema` | Structured-data schema discovery |
| POST | `/sql/execute` | Execute raw, validated read-only SQL |
| POST | `/sql/query` | Natural-language question → SQL → results |
| POST | `/guardrails/validate` | Run the input safety check standalone |
| POST | `/evaluation/evaluate`, GET `/evaluation/reports[/{thread_id}]` | Ad-hoc evaluation / automatic report history |
| GET | `/observability/health` | Deep system health (DB, vector backend, guardrails, version) |
| GET | `/observability/metrics`, `/observability/agents/performance`, `/observability/retrieval`, `/observability/execution-history` | Latency, per-agent, retrieval, and trace metrics |

### Example: ask a question

```bash
curl -X POST http://localhost:8000/api/v1/orchestrate \
  -H "Content-Type: application/json" \
  -d '{"query": "How many documents have been uploaded?"}'
```

Response includes `final_response`, `citations` (tagged `text`/`image_caption`/`table`/`database`), the full `execution_trace`, and `input_guardrail`/`output_guardrail` results.

---

## 6. Streamlit UI

| Page | Purpose |
|---|---|
| Home | Platform overview |
| Dashboard | Ingestion metrics (documents, chunks, status) |
| Upload Documents | PDF ingestion + extracted visual asset preview |
| Semantic Search | Multi-modal search with modality filter |
| SQL Intelligence | Schema browser, natural-language query, raw SQL console |
| Orchestrator Chat | Full agent pipeline with live execution trace + citations |
| Observability | System health, guardrail tester, agent performance, API metrics, execution history, evaluation reports |
| Settings | Model/connection configuration reference |

Deployment-friendly config lives in `.streamlit/config.toml` (headless mode, disabled telemetry, XSRF protection). The sidebar footer shows the running backend URL, environment, and `APP_VERSION`.

---

## 7. Observability & Evaluation

- **Every API request** gets a correlation id (`X-Request-ID` header, propagated into every log line) and its latency/status recorded.
- **Every `/orchestrate` run** automatically records per-agent timing into the metrics store and produces an `EvaluationReport` (retrieval quality, citation coverage, grounding, confidence) fetchable by `thread_id`.
- **Guardrails** run on every request: input is checked for prompt injection/jailbreak/unsafe content *before* any agent executes; the final response is scored for grounding/confidence afterward.
- All of this is visible live on the Streamlit **Observability** page, or via the `/observability/*` and `/evaluation/*` endpoints.

---

## 8. Docker Deployment

Two images, both multi-stage/non-root with a container-level `HEALTHCHECK`:

- **`Dockerfile`** — backend (full dependency set: LangChain/LangGraph/FAISS/PyMuPDF/etc.)
- **`Dockerfile.frontend`** — frontend (lightweight: streamlit/httpx/dotenv only)

```bash
# Build and start the full stack
docker compose up -d --build

# Backend:  http://localhost:8000/docs
# Frontend: http://localhost:8501
```

`docker-compose.yml`:
- Named volumes (`omnibrain_storage`, `omnibrain_logs`) persist uploads, the FAISS index, the SQLite DB, and logs across container restarts/recreation.
- Both services have `HEALTHCHECK`s; the frontend waits on the backend's `service_healthy` condition before starting.
- `restart: unless-stopped` and per-service memory/CPU limits (`mem_limit`/`cpus`).

To run without Qdrant (default), the app transparently falls back to the bundled FAISS index — no extra service required. To use Qdrant, run it separately and point `QDRANT_HOST`/`QDRANT_PORT` at it via `.env`.

**Verified**: both images build and start successfully, report `healthy` via Docker `HEALTHCHECK`, and data (a real SQLite write) survives a full `docker compose down && docker compose up`.

---

## 9. Troubleshooting

| Symptom | Cause / Fix |
|---|---|
| `/orchestrate` returns responses like *"I couldn't find grounded information..."* even with documents uploaded | No valid `OPENAI_API_KEY` configured. This is intentional graceful degradation, not a crash — every LLM-backed agent (Supervisor, Synthesizer, Vision, SQL generation) catches API failures and falls back to a safe default (keyword routing, "ungrounded" notice, etc). Set a real key in `.env` to get real answers. |
| Search backend shows `"vector_backend": "faiss"` instead of `"qdrant"` | Qdrant wasn't reachable at `QDRANT_HOST:QDRANT_PORT` at startup; this is the intended automatic fallback, not an error. |
| `docker compose up` fails with a port-already-in-use error | Another process (often a leftover local `uvicorn`/`streamlit` run) is already bound to 8000/8501. Stop it, or change the host-side port mapping in `docker-compose.yml`. |
| Windows: `pkill`/background processes from a previous session won't stop | On Windows, prefer `Get-NetTCPConnection -LocalPort <port>` + `Stop-Process -Id <pid> -Force` in PowerShell (or Task Manager) over `pkill`, which is unreliable for Windows-native Python processes launched from Git Bash. |
| SQL Agent rejects a generated/typed query | By design — only single, read-only `SELECT`/`WITH` statements are allowed (see `backend/app/services/sql_database_service.py::validate_readonly_sql`). Destructive keywords (`DROP`, `DELETE`, ...) and multi-statement input are rejected with a 400, and a second layer (`PRAGMA query_only`) enforces it at the SQLite connection level even if validation were bypassed. |
| Startup fails immediately with a `StartupValidationError` | A required directory couldn't be created, or `DATABASE_URL` is empty — this is fail-fast by design (Module 7) so a broken deployment crashes loudly instead of running silently unusable. Check the log line just above the traceback for which check failed. |
| Conversation/metrics/evaluation history resets unexpectedly | These are in-process singletons (see [Known Limitations](#10-known-limitations)) — they reset on process restart and are not shared if you run more than one backend worker/replica. |

---

## 10. Known Limitations

- **Single-process state**: LangGraph's `MemorySaver` checkpointer, the metrics store, and the evaluation-report store are in-process singletons. Running `UVICORN_WORKERS > 1` or multiple backend replicas gives each process independent state. Scaling out safely would require externalizing these to a shared backend (e.g. Redis) — out of scope for this module.
- **SQL Agent scope**: answers questions about OmniBrain's *own* ingestion metadata (documents/chunks/assets tables), not arbitrary external databases.
- **Output guardrail grounding check** is a citation-presence/relevance heuristic, not a full NLI/entailment model (no such dependency is in the approved tech stack).
