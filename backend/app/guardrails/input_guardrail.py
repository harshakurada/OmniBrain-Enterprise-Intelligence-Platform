import logging
import re
from typing import List, Optional
from pydantic import BaseModel, Field
from backend.app.config.settings import settings

logger = logging.getLogger("omnibrain.guardrails.input")

# Deterministic, offline pattern sets -- mirrors the Supervisor's
# `KeywordIntentClassifier` philosophy (Module 3): a fast, dependency-free
# heuristic layer that never needs network access and never hangs.
_PROMPT_INJECTION_PATTERNS = [
    r"ignore (all |any )?(the )?(previous|prior|above) instructions",
    r"disregard (all |any )?(the )?(previous|prior|above) instructions",
    r"forget (all |any )?(the )?(previous|prior) (instructions|context|rules)",
    r"reveal (your |the )?(system prompt|hidden instructions|instructions)",
    r"new instructions\s*:",
    r"override (your |the )?(instructions|rules|guidelines|configuration)",
    r"you are now\s+\w+",
]

_JAILBREAK_PATTERNS = [
    r"\bDAN\b",
    r"do anything now",
    r"\bjailbreak\b",
    r"act as an? (unfiltered|uncensored|unrestricted) (ai|assistant|model)",
    r"pretend (you have no|there are no) (restrictions|rules|filters|limitations)",
    r"no ethical guidelines",
    r"without any (restrictions|limitations|filters)",
    r"developer mode",
]

_UNSAFE_CONTENT_PATTERNS = [
    r"how to (make|build|synthesize) (a |an )?(bomb|explosive|weapon)",
    r"how to (hack|exploit) .*(system|account|network) without (permission|authorization)",
]


class GuardrailFinding(BaseModel):
    """A single guardrail rule that matched the input."""

    category: str = Field(..., description="'prompt_injection', 'jailbreak', 'unsafe_content', or 'input_too_long'")
    pattern: str = Field(..., description="The rule/pattern that triggered this finding")


class InputGuardrailResult(BaseModel):
    """Outcome of running the input safety checks over a user query."""

    passed: bool = Field(..., description="False if the input should be blocked before any agent runs")
    risk_level: str = Field(..., description="'none', 'low', 'medium', or 'high'")
    findings: List[GuardrailFinding] = Field(default_factory=list)
    reason: Optional[str] = None


class InputGuardrailService:
    """Deterministic, offline input safety layer run before the Supervisor:
    detects prompt injection attempts, jailbreak attempts, unsafe-content
    requests, and oversized input. High-risk findings block the request
    before any agent (and therefore any LLM/API cost) runs.
    """

    def __init__(self, max_input_length: Optional[int] = None):
        self.max_input_length = max_input_length or settings.GUARDRAIL_MAX_INPUT_LENGTH

    def check(self, text: str) -> InputGuardrailResult:
        """Returns an `InputGuardrailResult` for `text`. Never raises."""
        findings: List[GuardrailFinding] = []

        for category, patterns in (
            ("prompt_injection", _PROMPT_INJECTION_PATTERNS),
            ("jailbreak", _JAILBREAK_PATTERNS),
            ("unsafe_content", _UNSAFE_CONTENT_PATTERNS),
        ):
            for pattern in patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    findings.append(GuardrailFinding(category=category, pattern=pattern))

        if len(text) > self.max_input_length:
            findings.append(GuardrailFinding(category="input_too_long", pattern="max_length_exceeded"))

        high_risk_categories = {"prompt_injection", "jailbreak", "unsafe_content"}
        has_high_risk = any(f.category in high_risk_categories for f in findings)
        risk_level = "high" if has_high_risk else ("medium" if findings else "none")
        passed = not has_high_risk

        reason = None
        if findings:
            categories = sorted({f.category for f in findings})
            reason = f"Detected {len(findings)} guardrail flag(s): {', '.join(categories)}."
            logger.warning(f"Input guardrail flagged query (risk_level={risk_level}): {reason}")

        return InputGuardrailResult(passed=passed, risk_level=risk_level, findings=findings, reason=reason)
