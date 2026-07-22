# OmniBrain – Agentic Multi-Modal RAG Orchestrator

OmniBrain is a production-ready, enterprise-grade Agentic Multi-Modal Retrieval-Augmented Generation (RAG) platform. The system is designed using clean architecture patterns to guarantee scalability, modularity, and maintainability.

---

## 🏛 Architecture Overview

OmniBrain separates backend and frontend layers:

- **Backend**: Python 3.12, FastAPI (high-performance web API), SQLAlchemy 2.0 (database mapping), SQLite (relational storage).
- **Frontend**: Streamlit, designed with custom styles to deliver a responsive, professional experience.
- **Infrastructure**: Containerized with Docker and orchestrated using Docker Compose.
- **Telemetry & Validation**: Automated health checks, structured log rotators, Pydantic configuration schemas, and unit/integration testing with Pytest.

---

## 📂 Folder Structure

```text
OmniBrain/
├── backend/                  # FastAPI Backend Application
│   └── app/
│       ├── api/              # API router registrations
│       │   └── v1/
│       │       ├── endpoints/# Endpoint controllers (e.g., health.py)
│       │       └── router.py # Aggregates all routers
│       ├── config/           # Base settings configurations (Pydantic Settings)
│       │   └── settings.py
│       ├── core/             # Log setup, custom exception handlers
│       │   ├── exceptions.py
│       │   └── logging_config.py
│       ├── database/         # Engine, Session Local lifecycle, and Base model declarations
│       │   ├── connection.py
│       │   └── models.py
│       ├── schemas/          # Data transfer object schemas (Pydantic validation)
│       │   └── health.py
│       └── main.py           # Application entry point & startup/shutdown context hook
├── frontend/                 # Streamlit UI
│   └── app.py                # Main entry point & session state dashboard
├── tests/                    # Automation Unit and Integration tests
│   ├── conftest.py           # Database transaction fixtures & clients
│   └── test_health.py        # End-to-end API sanity tests
├── logs/                     # Auto-generated application logs (configured with rotators)
├── Dockerfile                # Common multi-stage Docker build config
├── docker-compose.yml        # Orchestration configuration
├── .dockerignore             # Inclusions exclusion mapping
├── .env.example              # Env template
├── .env                      # Active configurations (ignored in git)
├── .gitignore                # Version control exclusions
├── pyproject.toml            # Pytest and linter settings
└── requirements.txt          # Shared python packages list
```

---

## 🛠 Setup & Run Instructions

### Prerequisites
- Python 3.12 (if running locally)
- Docker & Docker Compose (if running inside containers)

### Running Locally

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables**:
   Copy `.env.example` into a `.env` file:
   ```bash
   copy .env.example .env
   ```

3. **Start backend API**:
   ```bash
   python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
   ```
   *Verify Swagger interface at:* http://127.0.0.1:8000/docs

4. **Start Streamlit Dashboard**:
   ```bash
   streamlit run frontend/app.py
   ```
   *Access dashboard page at:* http://127.0.0.1:8501

### Running Tests

Execute Pytest from the root directory:
```bash
pytest
```

---

## 🐳 Containerized Orchestration (Docker)

To run the entire system in Docker containers with volume hot-reloading:

1. **Build and Launch Services**:
   ```bash
   docker compose up --build
   ```
2. **Access Applications**:
   - Backend API: http://localhost:8000/docs
   - Frontend Streamlit UI: http://localhost:8501
   - Backend Health Check: http://localhost:8000/api/v1/health
