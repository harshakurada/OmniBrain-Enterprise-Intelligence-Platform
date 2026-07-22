import logging
import threading
from collections import deque
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Deque, Dict, List, Optional
from pydantic import BaseModel, Field
from backend.app.config.settings import settings

logger = logging.getLogger("omnibrain.observability.metrics")


class APIRequestRecord(BaseModel):
    """A single recorded API request."""

    request_id: str
    method: str
    path: str
    status_code: int
    duration_ms: float
    timestamp: str


class AgentExecutionRecord(BaseModel):
    """A single recorded agent/graph-node execution step."""

    request_id: Optional[str] = None
    agent: str
    action: str
    status: str
    duration_ms: float
    timestamp: str


class RetrievalStatsRecord(BaseModel):
    """A single recorded retrieval operation's quality statistics."""

    request_id: Optional[str] = None
    top_k: int
    result_count: int
    avg_score: float
    timestamp: str


class MetricsService:
    """Thread-safe, in-process observability store: capped rolling history
    of API requests, agent executions, and retrieval statistics, plus
    aggregate reporting. Intentionally dependency-free (no Prometheus/
    OpenTelemetry client) per Module 6's tech-stack constraint of reusing
    only existing project dependencies. A process-wide singleton (see
    `backend.app.api.deps.get_metrics_service`), so history survives across
    requests but resets on restart -- acceptable for this application's
    scope, consistent with the LangGraph checkpointer's `MemorySaver`.
    """

    def __init__(self, history_size: Optional[int] = None):
        self._history_size = history_size or settings.METRICS_HISTORY_SIZE
        self._lock = threading.Lock()
        self._api_requests: Deque[APIRequestRecord] = deque(maxlen=self._history_size)
        self._agent_executions: Deque[AgentExecutionRecord] = deque(maxlen=self._history_size)
        self._retrieval_stats: Deque[RetrievalStatsRecord] = deque(maxlen=self._history_size)

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def record_api_request(self, request_id: str, method: str, path: str, status_code: int, duration_ms: float) -> None:
        record = APIRequestRecord(
            request_id=request_id, method=method, path=path, status_code=status_code,
            duration_ms=round(duration_ms, 2), timestamp=self._now(),
        )
        with self._lock:
            self._api_requests.append(record)

    def record_agent_execution(
        self, agent: str, action: str, status: str, duration_ms: float, request_id: Optional[str] = None
    ) -> None:
        record = AgentExecutionRecord(
            request_id=request_id, agent=agent, action=action, status=status,
            duration_ms=round(duration_ms, 2), timestamp=self._now(),
        )
        with self._lock:
            self._agent_executions.append(record)

    def record_retrieval_stats(
        self, top_k: int, result_count: int, avg_score: float, request_id: Optional[str] = None
    ) -> None:
        record = RetrievalStatsRecord(
            request_id=request_id, top_k=top_k, result_count=result_count,
            avg_score=round(avg_score, 3), timestamp=self._now(),
        )
        with self._lock:
            self._retrieval_stats.append(record)

    def get_api_metrics(self) -> Dict[str, Any]:
        """Aggregate API latency/error statistics plus the most recent requests."""
        with self._lock:
            records = list(self._api_requests)
        if not records:
            return {"total_requests": 0, "avg_latency_ms": 0.0, "p95_latency_ms": 0.0, "error_rate": 0.0, "recent": []}

        durations = sorted(r.duration_ms for r in records)
        errors = sum(1 for r in records if r.status_code >= 400)
        p95_index = max(0, int(len(durations) * 0.95) - 1)
        return {
            "total_requests": len(records),
            "avg_latency_ms": round(mean(durations), 2),
            "p95_latency_ms": round(durations[p95_index], 2),
            "error_rate": round(errors / len(records), 3),
            "recent": [r.model_dump() for r in records[-20:]],
        }

    def get_agent_performance(self) -> Dict[str, Any]:
        """Per-agent invocation counts, average duration, and success rate."""
        with self._lock:
            records = list(self._agent_executions)

        by_agent: Dict[str, List[AgentExecutionRecord]] = {}
        for record in records:
            by_agent.setdefault(record.agent, []).append(record)

        stats: Dict[str, Any] = {}
        for agent, recs in by_agent.items():
            durations = [r.duration_ms for r in recs]
            successes = sum(1 for r in recs if r.status == "success")
            stats[agent] = {
                "invocations": len(recs),
                "avg_duration_ms": round(mean(durations), 2),
                "success_rate": round(successes / len(recs), 3),
            }
        return stats

    def get_retrieval_metrics(self) -> Dict[str, Any]:
        """Aggregate retrieval quality statistics across recorded runs."""
        with self._lock:
            records = list(self._retrieval_stats)
        if not records:
            return {"total_retrievals": 0, "avg_result_count": 0.0, "avg_score": 0.0}
        return {
            "total_retrievals": len(records),
            "avg_result_count": round(mean(r.result_count for r in records), 2),
            "avg_score": round(mean(r.avg_score for r in records), 3),
        }

    def get_execution_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """The most recent agent execution records, oldest first."""
        with self._lock:
            records = list(self._agent_executions)[-limit:]
        return [r.model_dump() for r in records]
