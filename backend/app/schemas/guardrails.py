from pydantic import BaseModel, Field


class GuardrailValidateRequest(BaseModel):
    """Request payload to run the input safety guardrail over arbitrary text."""

    text: str = Field(..., min_length=1, description="Text to check for prompt injection, jailbreak, or unsafe content")
