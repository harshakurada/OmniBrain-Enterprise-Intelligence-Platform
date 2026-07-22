import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.api.deps import get_active_vector_store, get_metrics_service
from backend.app.config.settings import settings
from backend.app.database.connection import get_db
from backend.app.observability.metrics_service import MetricsService
from backend.app.schemas.observability import (
    APIMetricsResponse,
    AgentPerformanceResponse,
    ExecutionHistoryResponse,
    RetrievalMetricsResponse,
    SystemHealthResponse,
)
from backend.app.services.vector_store_service import VectorStoreBase

logger = logging.getLogger("omnibrain.api.observability")
router = APIRouter()


@router.get(
    "/observability/health",
    response_model=SystemHealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Deep system health check across every reliability subsystem",
)
def system_health(
    db: Session = Depends(get_db),
    vector_store: VectorStoreBase = Depends(get_active_vector_store),
) -> SystemHealthResponse:
    """Checks the database connection, active vector store backend, and
    guardrail configuration -- a superset of the lightweight `/health`
    endpoint (Module 1), intended for dashboards/monitoring.
    """
    checks: dict = {}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as exc:
        checks["database"] = f"unhealthy: {exc}"

    checks["vector_store"] = f"healthy ({vector_store.backend_name})"
    checks["guardrails"] = "enabled" if settings.GUARDRAILS_ENABLED else "disabled"
    checks["openai_api_key"] = "configured" if settings.OPENAI_API_KEY and settings.OPENAI_API_KEY != "mock-key" else "not configured"

    overall_status = "healthy" if all("unhealthy" not in v for v in checks.values()) else "degraded"

    return SystemHealthResponse(
        status=overall_status,
        version=settings.APP_VERSION,
        environment=settings.ENVIRONMENT,
        database=checks["database"],
        vector_backend=vector_store.backend_name,
        guardrails_enabled=settings.GUARDRAILS_ENABLED,
        checks=checks,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@router.get(
    "/observability/metrics",
    response_model=APIMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Aggregate API latency and error-rate metrics",
)
def api_metrics(metrics: MetricsService = Depends(get_metrics_service)) -> APIMetricsResponse:
    return APIMetricsResponse(**metrics.get_api_metrics())


@router.get(
    "/observability/agents/performance",
    response_model=AgentPerformanceResponse,
    status_code=status.HTTP_200_OK,
    summary="Per-agent performance statistics (invocations, avg duration, success rate)",
)
def agent_performance(metrics: MetricsService = Depends(get_metrics_service)) -> AgentPerformanceResponse:
    return AgentPerformanceResponse(agents=metrics.get_agent_performance())


@router.get(
    "/observability/retrieval",
    response_model=RetrievalMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Aggregate retrieval quality statistics",
)
def retrieval_metrics(metrics: MetricsService = Depends(get_metrics_service)) -> RetrievalMetricsResponse:
    return RetrievalMetricsResponse(**metrics.get_retrieval_metrics())


@router.get(
    "/observability/execution-history",
    response_model=ExecutionHistoryResponse,
    status_code=status.HTTP_200_OK,
    summary="Recent agent execution history across all orchestration runs",
)
def execution_history(
    limit: int = Query(50, ge=1, le=500),
    metrics: MetricsService = Depends(get_metrics_service),
) -> ExecutionHistoryResponse:
    return ExecutionHistoryResponse(history=metrics.get_execution_history(limit=limit))
