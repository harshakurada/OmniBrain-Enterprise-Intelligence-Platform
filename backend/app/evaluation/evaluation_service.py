import logging
import threading
from collections import OrderedDict
from datetime import datetime, timezone
from statistics import mean
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from backend.app.config.settings import settings

logger = logging.getLogger("omnibrain.evaluation")


class RetrievalQualityMetrics(BaseModel):
    """Quality statistics for the retrieval results of a single run."""

    result_count: int
    avg_similarity_score: float
    min_similarity_score: float
    max_similarity_score: float


class EvaluationReport(BaseModel):
    """End-to-end evaluation of a single orchestration run: retrieval
    quality, citation coverage, grounding/confidence, and per-agent timing.
    """

    thread_id: str
    query: str
    intent: str
    agents_invoked: List[str] = Field(default_factory=list)
    retrieval_quality: Optional[RetrievalQualityMetrics] = None
    citation_count: int
    citation_coverage: float = Field(..., ge=0.0, le=1.0)
    grounded: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    agent_durations_ms: Dict[str, float] = Field(default_factory=dict)
    total_duration_ms: float
    evaluated_at: str


class EvaluationService:
    """Computes retrieval-quality, citation-coverage, and agent-performance
    metrics for a completed orchestration run, producing a structured
    `EvaluationReport`. Purely derived from the run's own final graph state
    (plus the Output Guardrail's grounding/confidence result) -- no extra
    LLM calls, so evaluation is fast, free, and fully deterministic.
    """

    def evaluate(self, thread_id: str, final_state: Dict[str, Any]) -> EvaluationReport:
        retrieval_results = final_state.get("retrieval_results") or []
        retrieval_quality = None
        if retrieval_results:
            scores = [float(r.get("score", 0.0)) for r in retrieval_results]
            retrieval_quality = RetrievalQualityMetrics(
                result_count=len(scores),
                avg_similarity_score=round(mean(scores), 3),
                min_similarity_score=round(min(scores), 3),
                max_similarity_score=round(max(scores), 3),
            )

        citations = final_state.get("citations") or []
        output_guardrail = final_state.get("output_guardrail") or {}
        grounded = bool(output_guardrail.get("grounded", bool(citations)))
        confidence = float(output_guardrail.get("confidence", 1.0 if citations else 0.0))
        # Citation coverage: fraction-style signal (1.0 = response is backed by
        # at least one citation, or correctly declined to answer ungrounded).
        citation_coverage = 1.0 if (citations or grounded) else 0.0

        agent_durations: Dict[str, float] = {}
        total_duration = 0.0
        for step in final_state.get("execution_trace", []):
            agent_durations[step["agent"]] = agent_durations.get(step["agent"], 0.0) + step["duration_ms"]
            total_duration += step["duration_ms"]

        return EvaluationReport(
            thread_id=thread_id,
            query=final_state.get("query", ""),
            intent=final_state.get("intent", ""),
            agents_invoked=final_state.get("agents_to_invoke", []),
            retrieval_quality=retrieval_quality,
            citation_count=len(citations),
            citation_coverage=citation_coverage,
            grounded=grounded,
            confidence=round(confidence, 3),
            agent_durations_ms={k: round(v, 2) for k, v in agent_durations.items()},
            total_duration_ms=round(total_duration, 2),
            evaluated_at=datetime.now(timezone.utc).isoformat(),
        )


class EvaluationHistoryStore:
    """Thread-safe, capped in-memory store of evaluation reports keyed by
    thread_id, most-recently-added last. A process-wide singleton (see
    `backend.app.api.deps.get_evaluation_history_store`).
    """

    def __init__(self, max_size: Optional[int] = None):
        self._max_size = max_size or settings.EVALUATION_HISTORY_SIZE
        self._lock = threading.Lock()
        self._reports: "OrderedDict[str, EvaluationReport]" = OrderedDict()

    def add(self, report: EvaluationReport) -> None:
        with self._lock:
            self._reports[report.thread_id] = report
            self._reports.move_to_end(report.thread_id)
            while len(self._reports) > self._max_size:
                self._reports.popitem(last=False)

    def get(self, thread_id: str) -> Optional[EvaluationReport]:
        with self._lock:
            return self._reports.get(thread_id)

    def list_recent(self, limit: int = 50) -> List[EvaluationReport]:
        with self._lock:
            items = list(self._reports.values())
        return items[-limit:]
