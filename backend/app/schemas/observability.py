from typing import Any, Dict, List
from pydantic import BaseModel, Field


class SystemHealthResponse(BaseModel):
    """Deep system health check covering every reliability subsystem."""

    status: str = Field(..., description="'healthy' or 'degraded'")
    version: str
    environment: str
    database: str
    vector_backend: str
    guardrails_enabled: bool
    checks: Dict[str, str]
    timestamp: str


class APIMetricsResponse(BaseModel):
    """Aggregate API latency/error statistics."""

    total_requests: int
    avg_latency_ms: float
    p95_latency_ms: float
    error_rate: float
    recent: List[Dict[str, Any]] = Field(default_factory=list)


class AgentPerformanceResponse(BaseModel):
    """Per-agent invocation counts, average duration, and success rate."""

    agents: Dict[str, Dict[str, Any]]


class RetrievalMetricsResponse(BaseModel):
    """Aggregate retrieval-quality statistics across recorded runs."""

    total_retrievals: int
    avg_result_count: float
    avg_score: float


class ExecutionHistoryResponse(BaseModel):
    """Recent agent execution records, oldest first."""

    history: List[Dict[str, Any]]
