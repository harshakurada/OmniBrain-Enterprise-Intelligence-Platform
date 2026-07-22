import logging
from typing import Any, Dict, List
from pydantic import BaseModel, Field

logger = logging.getLogger("omnibrain.guardrails.output")

# Phrases the Response Synthesizer (Modules 3-5) uses when it correctly
# declines to answer rather than inventing an ungrounded response. Matching
# one of these means the *absence* of citations is expected, not a
# hallucination risk.
_UNGROUNDED_REFUSAL_MARKERS = [
    "couldn't find grounded information",
    "generation temporarily unavailable",
    "i encountered an error while generating a response",
    "could not be answered from the structured database",
]


class OutputGuardrailResult(BaseModel):
    """Outcome of validating a synthesized response's grounding."""

    grounded: bool = Field(..., description="Whether the response is adequately backed by citations")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score for the response, 0.0-1.0")
    citation_count: int
    notes: str


class OutputGuardrailService:
    """Deterministic, offline response-grounding and hallucination-mitigation
    layer run after the Response Synthesizer. Since a full NLI/entailment
    model is out of scope for this module's tech stack, grounding is
    assessed heuristically from citation presence/relevance and from
    whether the response matches the Synthesizer's own known "I don't
    know" phrasing (a correct, non-hallucinated refusal).
    """

    def check(self, response_text: str, citations: List[Dict[str, Any]]) -> OutputGuardrailResult:
        """Returns an `OutputGuardrailResult` for a synthesized response. Never raises."""
        citation_count = len(citations)
        lowered = (response_text or "").lower()
        is_refusal = any(marker in lowered for marker in _UNGROUNDED_REFUSAL_MARKERS)

        if is_refusal:
            return OutputGuardrailResult(
                grounded=True,
                confidence=1.0,
                citation_count=citation_count,
                notes="Response correctly declined to answer without sufficient grounding.",
            )

        if not response_text or not response_text.strip():
            return OutputGuardrailResult(
                grounded=False, confidence=0.0, citation_count=0, notes="Response is empty."
            )

        if citation_count == 0:
            logger.warning("Output guardrail: non-refusal response has zero citations (possible hallucination).")
            return OutputGuardrailResult(
                grounded=False,
                confidence=0.2,
                citation_count=0,
                notes="No citations were found to support this response.",
            )

        avg_score = sum(float(c.get("similarity_score", 0.0)) for c in citations) / citation_count
        # Blend a citation-count factor (more independent sources -> more confidence)
        # with the average relevance score, capped at 1.0.
        count_factor = min(1.0, citation_count / 3.0)
        confidence = round(min(1.0, 0.4 * count_factor + 0.6 * max(0.0, avg_score)), 3)

        return OutputGuardrailResult(
            grounded=True,
            confidence=confidence,
            citation_count=citation_count,
            notes=f"Grounded by {citation_count} citation(s), average relevance {avg_score:.2f}.",
        )
