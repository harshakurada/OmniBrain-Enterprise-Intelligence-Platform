import pytest
from fastapi import status
from backend.app.agents.graph import build_orchestrator_graph
from backend.app.agents.retrieval_agent import RetrievalAgent
from backend.app.agents.sql_agent import SQLAgentResult
from backend.app.agents.supervisor_agent import KeywordIntentClassifier, SupervisorAgent
from backend.app.agents.synthesizer_agent import ResponseSynthesizer
from backend.app.agents.vision_agent import VisionAgent, VisionAgentResult
from backend.app.services.search_service import SemanticSearchResult
from tests._test_helpers import (  # noqa: F401
    FakeSynthesizerLLM,
    isolated_client,
    isolated_orchestrator_client,
    make_pdf_bytes,
)

# ---------------------------------------------------------------------------
# Supervisor routing
# ---------------------------------------------------------------------------


def test_keyword_classifier_defaults_to_retrieval_only():
    classifier = KeywordIntentClassifier()
    decision = classifier.classify("What was the revenue growth in Q3?")
    assert decision.agents == ["retrieval"]
    assert decision.intent == "retrieval"


def test_keyword_classifier_detects_sql_intent():
    classifier = KeywordIntentClassifier()
    decision = classifier.classify("How many rows are in the sales table?")
    assert "sql" in decision.agents
    assert "retrieval" in decision.agents


def test_keyword_classifier_detects_vision_intent():
    classifier = KeywordIntentClassifier()
    decision = classifier.classify("Describe the chart in figure 2.")
    assert "vision" in decision.agents


def test_keyword_classifier_detects_combined_intent():
    classifier = KeywordIntentClassifier()
    decision = classifier.classify("How many rows does the revenue chart table show?")
    assert set(decision.agents) == {"retrieval", "sql", "vision"}
    assert decision.intent == "combined"


def test_supervisor_agent_falls_back_when_classifier_raises():
    class BrokenClassifier:
        def classify(self, query):
            raise RuntimeError("classifier unavailable")

    supervisor = SupervisorAgent(classifier=BrokenClassifier())
    decision = supervisor.decide("What is in the document?")
    assert decision.agents == ["retrieval"]


# ---------------------------------------------------------------------------
# Agent execution
# ---------------------------------------------------------------------------


class _FakeSearchService:
    """Deterministic fake mirroring `SemanticSearchService.search`'s signature,
    including the Module 4 `chunk_types` filter. Returns a single canned
    result of `chunk_type`, or nothing if the caller filters it out.
    """

    def __init__(self, chunk_type="text", chunk_index=0):
        self.chunk_type = chunk_type
        self.chunk_index = chunk_index

    def search(self, query, top_k, document_id=None, chunk_types=None):
        if chunk_types and self.chunk_type not in chunk_types:
            return []
        return [
            SemanticSearchResult(
                document_id=1, filename="a.pdf", page_number=1, chunk_index=self.chunk_index,
                content="Revenue grew 18% year over year.", score=0.9, chunk_type=self.chunk_type,
            )
        ]


def test_retrieval_agent_delegates_to_search_service():
    agent = RetrievalAgent(search_service=_FakeSearchService())
    results = agent.run(query="revenue growth", top_k=3)
    assert len(results) == 1
    assert results[0].filename == "a.pdf"


def test_vision_agent_returns_visual_results_when_found():
    agent = VisionAgent(search_service=_FakeSearchService(chunk_type="image_caption", chunk_index=1))
    result = agent.run(query="describe the chart")
    assert isinstance(result, VisionAgentResult)
    assert result.status == "success"
    assert result.data["results"][0]["chunk_type"] == "image_caption"


def test_vision_agent_returns_no_visual_content_when_nothing_found():
    class EmptySearchService:
        def search(self, query, top_k, document_id=None, chunk_types=None):
            return []

    agent = VisionAgent(search_service=EmptySearchService())
    result = agent.run(query="describe the chart")
    assert result.status == "no_visual_content"
    assert result.data is None


class _FakeSQLAgent:
    """Deterministic fake mirroring `SQLAgent.run`'s interface -- real SQL
    Agent behavior (generation, validation, execution) is covered in
    `tests/test_sql.py`; this file only needs a stand-in for graph wiring.
    """

    def __init__(self, status="unanswerable", message="No structured data available.", data=None):
        self.status = status
        self.message = message
        self.data = data

    def run(self, query, document_id=None):
        return SQLAgentResult(status=self.status, message=self.message, data=self.data)


def test_response_synthesizer_dedupes_and_cites_chunks():
    synthesizer = ResponseSynthesizer(llm=FakeSynthesizerLLM())
    duplicate_chunk = {
        "document_id": 1, "filename": "a.pdf", "page_number": 1,
        "chunk_index": 0, "content": "Revenue grew 18%.", "score": 0.9,
    }
    response_text, citations = synthesizer.synthesize(
        query="revenue growth", retrieval_results=[duplicate_chunk, duplicate_chunk]
    )
    assert response_text == "Fake grounded answer based on retrieved context."
    assert len(citations) == 1
    assert citations[0]["filename"] == "a.pdf"


def test_response_synthesizer_returns_ungrounded_notice_with_no_chunks():
    synthesizer = ResponseSynthesizer(llm=FakeSynthesizerLLM())
    response_text, citations = synthesizer.synthesize(query="anything", retrieval_results=[])
    assert citations == []
    assert "couldn't find grounded information" in response_text


# ---------------------------------------------------------------------------
# LangGraph flow / state transitions
# ---------------------------------------------------------------------------


def _build_test_graph(search_service=None, vision_search_service=None):
    supervisor = SupervisorAgent(classifier=KeywordIntentClassifier())
    retrieval_agent = RetrievalAgent(search_service=search_service or _FakeSearchService())
    vision_agent = VisionAgent(
        search_service=vision_search_service or _FakeSearchService(chunk_type="image_caption", chunk_index=1)
    )
    return build_orchestrator_graph(
        supervisor=supervisor,
        retrieval_agent=retrieval_agent,
        vision_agent=vision_agent,
        sql_agent=_FakeSQLAgent(),
        synthesizer=ResponseSynthesizer(llm=FakeSynthesizerLLM()),
    )


def test_graph_routes_retrieval_only_query_through_retrieval_and_synthesizer():
    graph = _build_test_graph()
    result = graph.invoke(
        {"query": "What was the revenue growth?", "top_k": 3, "execution_trace": [], "errors": []},
        config={"configurable": {"thread_id": "t-retrieval"}},
    )
    assert result["agents_to_invoke"] == ["retrieval"]
    trace_agents = [t["agent"] for t in result["execution_trace"]]
    # Module 6: guardrails_input runs before the Supervisor, guardrails_output runs
    # after the Synthesizer, on every request.
    assert trace_agents == ["guardrails_input", "supervisor", "retrieval_agent", "synthesizer", "guardrails_output"]
    assert result["final_response"] == "Fake grounded answer based on retrieved context."
    assert len(result["citations"]) == 1


def test_graph_fans_out_and_back_in_for_combined_intent():
    graph = _build_test_graph()
    result = graph.invoke(
        {
            "query": "How many rows does the revenue chart table show?",
            "top_k": 3, "execution_trace": [], "errors": [],
        },
        config={"configurable": {"thread_id": "t-combined"}},
    )
    trace_agents = {t["agent"] for t in result["execution_trace"]}
    assert trace_agents == {
        "guardrails_input", "supervisor", "retrieval_agent", "vision_agent", "sql_agent",
        "synthesizer", "guardrails_output",
    }
    # synthesizer must run exactly once, after every fanned-out agent, and be
    # immediately followed by the output guardrail as the last step.
    trace_order = [t["agent"] for t in result["execution_trace"]]
    synth_index = trace_order.index("synthesizer")
    assert trace_order[synth_index + 1] == "guardrails_output"
    assert synth_index == len(result["execution_trace"]) - 2


def test_graph_persists_conversation_state_across_calls_with_same_thread_id():
    from langgraph.checkpoint.memory import MemorySaver

    supervisor = SupervisorAgent(classifier=KeywordIntentClassifier())
    graph = build_orchestrator_graph(
        supervisor=supervisor,
        retrieval_agent=RetrievalAgent(search_service=_FakeSearchService()),
        vision_agent=VisionAgent(search_service=_FakeSearchService(chunk_type="image_caption", chunk_index=1)),
        sql_agent=_FakeSQLAgent(),
        synthesizer=ResponseSynthesizer(llm=FakeSynthesizerLLM()),
        checkpointer=MemorySaver(),
    )
    config = {"configurable": {"thread_id": "t-persist"}}
    graph.invoke({"query": "first question", "top_k": 3, "execution_trace": [], "errors": []}, config=config)
    state = graph.get_state(config)
    assert state.values["query"] == "first question"
    assert len(state.values["execution_trace"]) >= 1


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------


def test_graph_degrades_gracefully_when_retrieval_agent_raises():
    class BrokenSearchService:
        def search(self, query, top_k, document_id=None, chunk_types=None):
            raise RuntimeError("vector store unavailable")

    graph = _build_test_graph(search_service=BrokenSearchService())
    result = graph.invoke(
        {"query": "What was the revenue growth?", "top_k": 3, "execution_trace": [], "errors": []},
        config={"configurable": {"thread_id": "t-broken-retrieval"}},
    )
    retrieval_trace = next(t for t in result["execution_trace"] if t["agent"] == "retrieval_agent")
    assert retrieval_trace["status"] == "error"
    assert any("retrieval_agent" in e for e in result["errors"])
    # The graph still reaches the synthesizer and returns a response instead of crashing.
    assert result["final_response"]


def test_graph_degrades_gracefully_when_synthesizer_raises():
    class BrokenSynthesizer:
        def synthesize(self, **kwargs):
            raise RuntimeError("llm unavailable")

    supervisor = SupervisorAgent(classifier=KeywordIntentClassifier())
    graph = build_orchestrator_graph(
        supervisor=supervisor,
        retrieval_agent=RetrievalAgent(search_service=_FakeSearchService()),
        vision_agent=VisionAgent(search_service=_FakeSearchService(chunk_type="image_caption", chunk_index=1)),
        sql_agent=_FakeSQLAgent(),
        synthesizer=BrokenSynthesizer(),
    )
    result = graph.invoke(
        {"query": "What was the revenue growth?", "top_k": 3, "execution_trace": [], "errors": []},
        config={"configurable": {"thread_id": "t-broken-synth"}},
    )
    assert "error while generating a response" in result["final_response"]
    assert any("synthesizer" in e for e in result["errors"])


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


def _upload_pdf(client, filename: str, text: str) -> int:
    pdf_bytes = make_pdf_bytes(text)
    response = client.post(
        "/api/v1/documents/upload",
        files=[("files", (filename, pdf_bytes, "application/pdf"))],
    )
    return response.json()["results"][0]["document_id"]


def test_orchestrate_endpoint_returns_grounded_response_with_trace_and_citations(isolated_orchestrator_client):
    document_id = _upload_pdf(
        isolated_orchestrator_client, "revenue.pdf",
        "OmniBrain semantic retrieval test passage about quarterly revenue growth.",
    )

    response = isolated_orchestrator_client.post(
        "/api/v1/orchestrate",
        json={"query": "quarterly revenue growth", "top_k": 3},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["agents_invoked"] == ["retrieval"]
    assert data["final_response"] == "Fake grounded answer based on retrieved context."
    assert len(data["citations"]) >= 1
    assert data["citations"][0]["document_id"] == document_id
    assert [step["agent"] for step in data["execution_trace"]] == [
        "guardrails_input", "supervisor", "retrieval_agent", "synthesizer", "guardrails_output",
    ]
    assert data["thread_id"]
    assert data["blocked"] is False
    assert data["input_guardrail"]["passed"] is True
    assert data["output_guardrail"]["grounded"] is True


def test_orchestrate_endpoint_routes_sql_keywords_to_sql_agent(isolated_orchestrator_client):
    response = isolated_orchestrator_client.post(
        "/api/v1/orchestrate",
        json={"query": "How many rows are in the sales table?"},
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "sql" in data["agents_invoked"]
    assert "sql_agent" in [step["agent"] for step in data["execution_trace"]]


def test_orchestrate_endpoint_preserves_thread_id_across_calls(isolated_orchestrator_client):
    first = isolated_orchestrator_client.post(
        "/api/v1/orchestrate", json={"query": "first turn", "thread_id": "conversation-1"}
    )
    second = isolated_orchestrator_client.post(
        "/api/v1/orchestrate", json={"query": "second turn", "thread_id": "conversation-1"}
    )
    assert first.json()["thread_id"] == "conversation-1"
    assert second.json()["thread_id"] == "conversation-1"


def test_orchestrate_endpoint_rejects_empty_query(isolated_orchestrator_client):
    response = isolated_orchestrator_client.post("/api/v1/orchestrate", json={"query": ""})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
