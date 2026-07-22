from typing import List, Optional
from pydantic import BaseModel, Field


class OrchestrateRequest(BaseModel):
    """Request payload for the agentic orchestration endpoint."""

    query: str = Field(..., min_length=1, description="Natural language user query")
    top_k: int = Field(5, ge=1, le=50, description="Number of top matching chunks the Retrieval Agent should fetch")
    document_id: Optional[int] = Field(None, description="Restrict retrieval to a single document, if provided")
    thread_id: Optional[str] = Field(
        None, description="Conversation/session id. Reuse it across calls to maintain execution history; omit to start a new one."
    )


class CitationItem(BaseModel):
    """A single source citation backing the synthesized response."""

    document_id: int
    filename: str
    page_number: int
    chunk_index: int
    similarity_score: float = Field(..., description="Cosine similarity score, higher is more relevant")
    chunk_type: str = Field("text", description="'text', 'image_caption', or 'table'")


class AgentTraceStep(BaseModel):
    """A single step of the agent execution trace."""

    agent: str = Field(..., description="Name of the agent/node that executed this step")
    action: str = Field(..., description="Action performed by the agent")
    status: str = Field(..., description="'success', 'error', or 'blocked'")
    detail: str = Field(..., description="Human-readable outcome summary")
    duration_ms: float = Field(..., description="Execution time for this step, in milliseconds")


class InputGuardrailInfo(BaseModel):
    """Outcome of the pre-agent input safety check (Module 6)."""

    passed: bool
    risk_level: str = Field(..., description="'none', 'low', 'medium', or 'high'")
    reason: Optional[str] = None


class OutputGuardrailInfo(BaseModel):
    """Outcome of the post-synthesis grounding/confidence check (Module 6)."""

    grounded: bool
    confidence: float = Field(..., ge=0.0, le=1.0)
    citation_count: int
    notes: str


class OrchestrateResponse(BaseModel):
    """Response payload for the agentic orchestration endpoint: the final
    grounded response, its source citations, the full multi-agent
    execution trace, and guardrail outcomes.
    """

    thread_id: str
    query: str
    intent: str
    agents_invoked: List[str]
    final_response: str
    citations: List[CitationItem]
    execution_trace: List[AgentTraceStep]
    blocked: bool = Field(False, description="True if the request was blocked by the input guardrail")
    input_guardrail: Optional[InputGuardrailInfo] = None
    output_guardrail: Optional[OutputGuardrailInfo] = None
