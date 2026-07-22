import logging
from fastapi import APIRouter, Depends, status
from backend.app.api.deps import get_input_guardrail_service
from backend.app.guardrails.input_guardrail import InputGuardrailResult, InputGuardrailService
from backend.app.schemas.guardrails import GuardrailValidateRequest

logger = logging.getLogger("omnibrain.api.guardrails")
router = APIRouter()


@router.post(
    "/guardrails/validate",
    response_model=InputGuardrailResult,
    status_code=status.HTTP_200_OK,
    summary="Run the input safety guardrail over arbitrary text",
    response_description="Whether the text passes, its risk level, and any prompt-injection/jailbreak/unsafe-content findings.",
)
def validate_input(
    request: GuardrailValidateRequest,
    guardrail: InputGuardrailService = Depends(get_input_guardrail_service),
) -> InputGuardrailResult:
    """Runs the same deterministic input safety checks the orchestrator
    applies before every agent run, without executing any agent.
    """
    return guardrail.check(request.text)
