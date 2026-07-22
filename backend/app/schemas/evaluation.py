from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EvaluateRequest(BaseModel):
    """Ad-hoc evaluation request. The fields mirror a completed orchestration
    run's relevant final-state, so evaluation can be exercised independently
    of a live `/orchestrate` call (e.g. for testing or offline analysis).
    """

    thread_id: Optional[str] = Field(None, description="Omit to auto-generate an id for this ad-hoc evaluation")
    query: str = ""
    intent: str = ""
    agents_invoked: List[str] = Field(default_factory=list)
    retrieval_results: List[Dict[str, Any]] = Field(default_factory=list)
    citations: List[Dict[str, Any]] = Field(default_factory=list)
    execution_trace: List[Dict[str, Any]] = Field(default_factory=list)
    output_guardrail: Optional[Dict[str, Any]] = None
