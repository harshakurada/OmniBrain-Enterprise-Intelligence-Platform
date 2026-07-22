import pytest
from fastapi import status
from backend.app.api.deps import get_evaluation_history_store
from backend.app.evaluation.evaluation_service import EvaluationHistoryStore, EvaluationReport, EvaluationService
from tests._test_helpers import (  # noqa: F401
    isolated_client,
    isolated_orchestrator_client,
    make_pdf_bytes,
)


@pytest.fixture(autouse=True)
def fresh_evaluation_history():
    """Resets the process-wide evaluation history singleton so tests are
    deterministic regardless of execution order.
    """
    get_evaluation_history_store.cache_clear()
    yield
    get_evaluation_history_store.cache_clear()


# ---------------------------------------------------------------------------
# EvaluationService: retrieval quality, citation coverage, agent timing
# ---------------------------------------------------------------------------


def _sample_final_state(**overrides):
    base = {
        "query": "What was the revenue growth?",
        "intent": "retrieval",
        "agents_to_invoke": ["retrieval"],
        "retrieval_results": [
            {"document_id": 1, "filename": "a.pdf", "page_number": 1, "chunk_index": 0, "content": "x", "score": 0.9},
            {"document_id": 1, "filename": "a.pdf", "page_number": 2, "chunk_index": 1, "content": "y", "score": 0.7},
        ],
        "citations": [
            {"document_id": 1, "filename": "a.pdf", "page_number": 1, "chunk_index": 0, "similarity_score": 0.9, "chunk_type": "text"},
        ],
        "execution_trace": [
            {"agent": "supervisor", "action": "classify_intent", "status": "success", "detail": "", "duration_ms": 10.0},
            {"agent": "retrieval_agent", "action": "semantic_search", "status": "success", "detail": "", "duration_ms": 20.0},
            {"agent": "synthesizer", "action": "generate_response", "status": "success", "detail": "", "duration_ms": 30.0},
        ],
        "output_guardrail": {"grounded": True, "confidence": 0.85, "citation_count": 1, "notes": "ok"},
    }
    base.update(overrides)
    return base


def test_evaluation_service_computes_retrieval_quality():
    report = EvaluationService().evaluate("t1", _sample_final_state())
    assert report.retrieval_quality is not None
    assert report.retrieval_quality.result_count == 2
    assert report.retrieval_quality.avg_similarity_score == pytest.approx(0.8, abs=1e-3)
    assert report.retrieval_quality.min_similarity_score == pytest.approx(0.7)
    assert report.retrieval_quality.max_similarity_score == pytest.approx(0.9)


def test_evaluation_service_handles_no_retrieval_results():
    report = EvaluationService().evaluate("t2", _sample_final_state(retrieval_results=[]))
    assert report.retrieval_quality is None


def test_evaluation_service_pulls_grounding_and_confidence_from_output_guardrail():
    report = EvaluationService().evaluate("t3", _sample_final_state())
    assert report.grounded is True
    assert report.confidence == pytest.approx(0.85)
    assert report.citation_count == 1
    assert report.citation_coverage == 1.0


def test_evaluation_service_aggregates_agent_durations():
    report = EvaluationService().evaluate("t4", _sample_final_state())
    assert report.agent_durations_ms == {"supervisor": 10.0, "retrieval_agent": 20.0, "synthesizer": 30.0}
    assert report.total_duration_ms == pytest.approx(60.0)


def test_evaluation_service_zero_citations_and_not_grounded():
    state = _sample_final_state(
        citations=[], output_guardrail={"grounded": False, "confidence": 0.2, "citation_count": 0, "notes": "no citations"}
    )
    report = EvaluationService().evaluate("t5", state)
    assert report.grounded is False
    assert report.citation_coverage == 0.0
    assert report.citation_count == 0


# ---------------------------------------------------------------------------
# EvaluationHistoryStore
# ---------------------------------------------------------------------------


def test_evaluation_history_store_add_and_get_roundtrip():
    store = EvaluationHistoryStore()
    report = EvaluationService().evaluate("thread-abc", _sample_final_state())
    store.add(report)
    fetched = store.get("thread-abc")
    assert fetched is not None
    assert fetched.thread_id == "thread-abc"


def test_evaluation_history_store_get_missing_returns_none():
    store = EvaluationHistoryStore()
    assert store.get("does-not-exist") is None


def test_evaluation_history_store_list_recent_respects_limit_and_order():
    store = EvaluationHistoryStore()
    service = EvaluationService()
    for i in range(5):
        store.add(service.evaluate(f"thread-{i}", _sample_final_state()))
    recent = store.list_recent(limit=3)
    assert [r.thread_id for r in recent] == ["thread-2", "thread-3", "thread-4"]


def test_evaluation_history_store_evicts_oldest_beyond_max_size():
    store = EvaluationHistoryStore(max_size=2)
    service = EvaluationService()
    for i in range(4):
        store.add(service.evaluate(f"thread-{i}", _sample_final_state()))
    all_reports = store.list_recent(limit=10)
    assert [r.thread_id for r in all_reports] == ["thread-2", "thread-3"]


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


def test_evaluate_endpoint_ad_hoc(isolated_client):
    response = isolated_client.post(
        "/api/v1/evaluation/evaluate",
        json={
            "query": "test query",
            "intent": "retrieval",
            "agents_invoked": ["retrieval"],
            "retrieval_results": [
                {"document_id": 1, "filename": "a.pdf", "page_number": 1, "chunk_index": 0, "content": "x", "score": 0.8}
            ],
            "citations": [{"document_id": 1, "filename": "a.pdf", "page_number": 1, "chunk_index": 0, "similarity_score": 0.8}],
            "execution_trace": [
                {"agent": "supervisor", "action": "classify_intent", "status": "success", "detail": "", "duration_ms": 5.0}
            ],
        },
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["retrieval_quality"]["result_count"] == 1
    assert data["citation_count"] == 1
    assert data["thread_id"]


def test_evaluation_reports_endpoint_lists_recent(isolated_client):
    isolated_client.post("/api/v1/evaluation/evaluate", json={"query": "q1", "thread_id": "report-1"})
    isolated_client.post("/api/v1/evaluation/evaluate", json={"query": "q2", "thread_id": "report-2"})

    response = isolated_client.get("/api/v1/evaluation/reports")
    assert response.status_code == status.HTTP_200_OK
    thread_ids = {r["thread_id"] for r in response.json()}
    assert {"report-1", "report-2"}.issubset(thread_ids)


def test_evaluation_report_by_thread_id_endpoint(isolated_client):
    isolated_client.post("/api/v1/evaluation/evaluate", json={"query": "q1", "thread_id": "specific-thread"})
    response = isolated_client.get("/api/v1/evaluation/reports/specific-thread")
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["thread_id"] == "specific-thread"


def test_evaluation_report_by_thread_id_endpoint_404_when_missing(isolated_client):
    response = isolated_client.get("/api/v1/evaluation/reports/nonexistent-thread")
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# End-to-end: /orchestrate automatically records an evaluation report
# ---------------------------------------------------------------------------


def test_orchestrate_call_automatically_produces_a_fetchable_evaluation_report(isolated_orchestrator_client):
    pdf_bytes = make_pdf_bytes("Quarterly revenue growth content for evaluation test.")
    isolated_orchestrator_client.post(
        "/api/v1/documents/upload", files=[("files", ("a.pdf", pdf_bytes, "application/pdf"))]
    )

    orchestrate_response = isolated_orchestrator_client.post(
        "/api/v1/orchestrate", json={"query": "quarterly revenue growth content"}
    )
    thread_id = orchestrate_response.json()["thread_id"]

    report_response = isolated_orchestrator_client.get(f"/api/v1/evaluation/reports/{thread_id}")
    assert report_response.status_code == status.HTTP_200_OK
    report = report_response.json()
    assert report["thread_id"] == thread_id
    assert report["total_duration_ms"] > 0
    assert "retrieval_agent" in report["agent_durations_ms"]
