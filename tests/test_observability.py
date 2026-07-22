import pytest
from fastapi import status
from backend.app.api.deps import get_metrics_service
from backend.app.observability.metrics_service import MetricsService
from backend.app.observability.request_context import get_request_id, set_request_id
from tests._test_helpers import isolated_client, isolated_orchestrator_client, make_pdf_bytes  # noqa: F401


@pytest.fixture(autouse=True)
def fresh_metrics_service():
    """Resets the process-wide metrics singleton so tests are deterministic
    regardless of execution order and prior test activity.
    """
    get_metrics_service.cache_clear()
    yield
    get_metrics_service.cache_clear()


# ---------------------------------------------------------------------------
# Request context
# ---------------------------------------------------------------------------


def test_set_and_get_request_id_roundtrip():
    set_request_id("abc123")
    assert get_request_id() == "abc123"


def test_set_request_id_generates_one_when_omitted():
    rid = set_request_id(None)
    assert rid
    assert get_request_id() == rid


# ---------------------------------------------------------------------------
# MetricsService
# ---------------------------------------------------------------------------


def test_metrics_service_records_and_aggregates_api_requests():
    service = MetricsService()
    service.record_api_request("r1", "GET", "/api/v1/health", 200, 10.0)
    service.record_api_request("r2", "GET", "/api/v1/health", 200, 20.0)
    service.record_api_request("r3", "GET", "/api/v1/health", 500, 30.0)

    metrics = service.get_api_metrics()
    assert metrics["total_requests"] == 3
    assert metrics["avg_latency_ms"] == pytest.approx(20.0)
    assert metrics["error_rate"] == pytest.approx(1 / 3, abs=1e-3)
    assert len(metrics["recent"]) == 3


def test_metrics_service_empty_api_metrics():
    service = MetricsService()
    metrics = service.get_api_metrics()
    assert metrics == {"total_requests": 0, "avg_latency_ms": 0.0, "p95_latency_ms": 0.0, "error_rate": 0.0, "recent": []}


def test_metrics_service_agent_performance_per_agent_stats():
    service = MetricsService()
    service.record_agent_execution("retrieval_agent", "semantic_search", "success", 15.0)
    service.record_agent_execution("retrieval_agent", "semantic_search", "success", 25.0)
    service.record_agent_execution("retrieval_agent", "semantic_search", "error", 5.0)

    stats = service.get_agent_performance()
    assert stats["retrieval_agent"]["invocations"] == 3
    assert stats["retrieval_agent"]["avg_duration_ms"] == pytest.approx(15.0)
    assert stats["retrieval_agent"]["success_rate"] == pytest.approx(2 / 3, abs=1e-3)


def test_metrics_service_retrieval_stats_aggregation():
    service = MetricsService()
    service.record_retrieval_stats(top_k=5, result_count=3, avg_score=0.8)
    service.record_retrieval_stats(top_k=5, result_count=5, avg_score=0.6)

    metrics = service.get_retrieval_metrics()
    assert metrics["total_retrievals"] == 2
    assert metrics["avg_result_count"] == pytest.approx(4.0)
    assert metrics["avg_score"] == pytest.approx(0.7)


def test_metrics_service_execution_history_respects_limit():
    service = MetricsService()
    for i in range(10):
        service.record_agent_execution("supervisor", "classify_intent", "success", float(i))
    history = service.get_execution_history(limit=3)
    assert len(history) == 3
    assert [h["duration_ms"] for h in history] == [7.0, 8.0, 9.0]


def test_metrics_service_history_is_capped():
    service = MetricsService(history_size=5)
    for i in range(20):
        service.record_api_request(f"r{i}", "GET", "/x", 200, 1.0)
    metrics = service.get_api_metrics()
    assert metrics["total_requests"] == 5


# ---------------------------------------------------------------------------
# Middleware: X-Request-ID header + automatic API metrics recording
# ---------------------------------------------------------------------------


def test_response_includes_request_id_header(isolated_client):
    response = isolated_client.get("/api/v1/health")
    assert "X-Request-ID" in response.headers
    assert response.headers["X-Request-ID"]


def test_request_id_header_is_echoed_back_when_provided(isolated_client):
    response = isolated_client.get("/api/v1/health", headers={"X-Request-ID": "client-supplied-id"})
    assert response.headers["X-Request-ID"] == "client-supplied-id"


def test_middleware_automatically_records_api_metrics(isolated_client):
    isolated_client.get("/api/v1/health")
    isolated_client.get("/api/v1/health")

    metrics_response = isolated_client.get("/api/v1/observability/metrics")
    data = metrics_response.json()
    assert data["total_requests"] >= 2
    assert any(r["path"] == "/api/v1/health" for r in data["recent"])


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


def test_observability_health_endpoint(isolated_client):
    response = isolated_client.get("/api/v1/observability/health")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "healthy"
    assert data["database"] == "healthy"
    assert "vector_store" in data["checks"]
    assert data["guardrails_enabled"] is True


def test_observability_agent_performance_endpoint_reflects_orchestrate_run(isolated_orchestrator_client):
    pdf_bytes = make_pdf_bytes("Content for observability agent performance test.")
    isolated_orchestrator_client.post(
        "/api/v1/documents/upload", files=[("files", ("a.pdf", pdf_bytes, "application/pdf"))]
    )
    isolated_orchestrator_client.post(
        "/api/v1/orchestrate", json={"query": "content for observability agent performance test"}
    )

    response = isolated_orchestrator_client.get("/api/v1/observability/agents/performance")
    assert response.status_code == status.HTTP_200_OK
    agents = response.json()["agents"]
    assert "supervisor" in agents
    assert "guardrails_input" in agents
    assert "guardrails_output" in agents
    assert agents["supervisor"]["invocations"] >= 1


def test_observability_execution_history_endpoint(isolated_orchestrator_client):
    isolated_orchestrator_client.post("/api/v1/orchestrate", json={"query": "What was the revenue growth?"})
    response = isolated_orchestrator_client.get("/api/v1/observability/execution-history?limit=10")
    assert response.status_code == status.HTTP_200_OK
    history = response.json()["history"]
    assert len(history) > 0
    assert all("agent" in h and "duration_ms" in h for h in history)


def test_observability_retrieval_metrics_endpoint(isolated_orchestrator_client):
    pdf_bytes = make_pdf_bytes("Retrieval metrics endpoint test content.")
    isolated_orchestrator_client.post(
        "/api/v1/documents/upload", files=[("files", ("a.pdf", pdf_bytes, "application/pdf"))]
    )
    isolated_orchestrator_client.post("/api/v1/orchestrate", json={"query": "retrieval metrics endpoint test"})

    response = isolated_orchestrator_client.get("/api/v1/observability/retrieval")
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total_retrievals"] >= 1


# ---------------------------------------------------------------------------
# Reliability: observability recording failures never break orchestration
# ---------------------------------------------------------------------------


def test_orchestrator_service_survives_broken_metrics_service():
    from backend.app.agents.graph import build_orchestrator_graph
    from backend.app.agents.orchestrator_service import OrchestratorService
    from backend.app.agents.retrieval_agent import RetrievalAgent
    from backend.app.agents.sql_agent import SQLAgentResult
    from backend.app.agents.supervisor_agent import KeywordIntentClassifier, SupervisorAgent
    from backend.app.agents.synthesizer_agent import ResponseSynthesizer
    from backend.app.agents.vision_agent import VisionAgent
    from backend.app.services.search_service import SemanticSearchResult
    from tests._test_helpers import FakeSynthesizerLLM

    class _FakeSearchService:
        def search(self, query, top_k, document_id=None, chunk_types=None):
            return [
                SemanticSearchResult(
                    document_id=1, filename="a.pdf", page_number=1, chunk_index=0,
                    content="x", score=0.9, chunk_type="text",
                )
            ]

    class _FakeSQLAgent:
        def run(self, query, document_id=None):
            return SQLAgentResult(status="unanswerable", message="n/a", data=None)

    class BrokenMetricsService:
        def record_agent_execution(self, *args, **kwargs):
            raise RuntimeError("metrics backend down")

        def record_retrieval_stats(self, *args, **kwargs):
            raise RuntimeError("metrics backend down")

    graph = build_orchestrator_graph(
        supervisor=SupervisorAgent(classifier=KeywordIntentClassifier()),
        retrieval_agent=RetrievalAgent(search_service=_FakeSearchService()),
        vision_agent=VisionAgent(search_service=_FakeSearchService()),
        sql_agent=_FakeSQLAgent(),
        synthesizer=ResponseSynthesizer(llm=FakeSynthesizerLLM()),
    )
    orchestrator = OrchestratorService(graph=graph, metrics_service=BrokenMetricsService())

    result = orchestrator.run(query="What was the revenue growth?", top_k=3)
    assert result["final_response"]
