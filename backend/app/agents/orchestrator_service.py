import logging
import uuid
from typing import Any, Dict, Optional
from langgraph.graph.state import CompiledStateGraph
from backend.app.agents.state import AgentState
from backend.app.evaluation.evaluation_service import EvaluationHistoryStore, EvaluationService
from backend.app.observability.metrics_service import MetricsService

logger = logging.getLogger("omnibrain.agents.orchestrator")


class OrchestratorService:
    """High-level entry point that drives the LangGraph multi-agent workflow
    and hands back its resulting state for the API layer to shape into a
    response. Conversation state and execution history are preserved across
    calls that share the same `thread_id` via the graph's checkpointer.

    When observability/evaluation collaborators are supplied (Module 6),
    every run's execution trace and retrieval statistics are recorded into
    `MetricsService`, and a full `EvaluationReport` is computed and stored.
    Both are best-effort: any failure recording metrics/evaluation is
    logged and swallowed so it can never break orchestration itself.
    """

    def __init__(
        self,
        graph: CompiledStateGraph,
        metrics_service: Optional[MetricsService] = None,
        evaluation_service: Optional[EvaluationService] = None,
        evaluation_history: Optional[EvaluationHistoryStore] = None,
    ):
        self.graph = graph
        self.metrics_service = metrics_service
        self.evaluation_service = evaluation_service
        self.evaluation_history = evaluation_history

    def run(
        self,
        query: str,
        top_k: int,
        document_id: Optional[int] = None,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Executes the orchestrator graph for `query` and returns the final
        graph state, augmented with the `thread_id` the run executed under.
        """
        thread_id = thread_id or str(uuid.uuid4())
        initial_state: AgentState = {
            "query": query,
            "document_id": document_id,
            "top_k": top_k,
            "execution_trace": [],
            "errors": [],
        }
        config = {"configurable": {"thread_id": thread_id}}

        logger.info(f"Executing orchestration graph (thread_id={thread_id}) for query: {query!r}")
        final_state = self.graph.invoke(initial_state, config=config)
        final_state["thread_id"] = thread_id

        self._record_observability(thread_id, final_state)
        return final_state

    def _record_observability(self, thread_id: str, final_state: Dict[str, Any]) -> None:
        """Best-effort metrics/evaluation recording -- never raises."""
        try:
            if self.metrics_service:
                for step in final_state.get("execution_trace", []):
                    self.metrics_service.record_agent_execution(
                        agent=step["agent"], action=step["action"], status=step["status"],
                        duration_ms=step["duration_ms"], request_id=thread_id,
                    )
                retrieval_results = final_state.get("retrieval_results") or []
                if retrieval_results:
                    avg_score = sum(r.get("score", 0.0) for r in retrieval_results) / len(retrieval_results)
                    self.metrics_service.record_retrieval_stats(
                        top_k=final_state.get("top_k", 0),
                        result_count=len(retrieval_results),
                        avg_score=avg_score,
                        request_id=thread_id,
                    )

            if self.evaluation_service and self.evaluation_history:
                report = self.evaluation_service.evaluate(thread_id, final_state)
                self.evaluation_history.add(report)
        except Exception:
            logger.exception("Failed to record orchestration observability data (non-fatal).")
