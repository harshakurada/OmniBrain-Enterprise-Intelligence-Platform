import logging
from fastapi import APIRouter, Depends, status
from backend.app.agents.orchestrator_service import OrchestratorService
from backend.app.api.deps import get_orchestrator_service
from backend.app.schemas.orchestrator import (
    AgentTraceStep,
    CitationItem,
    InputGuardrailInfo,
    OrchestrateRequest,
    OrchestrateResponse,
    OutputGuardrailInfo,
)

logger = logging.getLogger("omnibrain.api.orchestrator")
router = APIRouter()


@router.post(
    "/orchestrate",
    response_model=OrchestrateResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute the LangGraph multi-agent orchestration workflow",
    response_description="Grounded final response, source citations, and the full agent execution trace.",
)
def orchestrate(
    request: OrchestrateRequest,
    orchestrator: OrchestratorService = Depends(get_orchestrator_service),
) -> OrchestrateResponse:
    """Routes the user's query through the Supervisor Agent, executes
    whichever of the Retrieval / Vision / SQL agents are selected, and
    returns a citation-grounded response synthesized from their combined
    outputs, along with the full step-by-step execution trace.
    """
    final_state = orchestrator.run(
        query=request.query,
        top_k=request.top_k,
        document_id=request.document_id,
        thread_id=request.thread_id,
    )

    input_guardrail = final_state.get("input_guardrail")
    output_guardrail = final_state.get("output_guardrail")

    return OrchestrateResponse(
        thread_id=final_state["thread_id"],
        query=request.query,
        intent=final_state.get("intent", "retrieval"),
        agents_invoked=final_state.get("agents_to_invoke", []),
        final_response=final_state.get("final_response", ""),
        citations=[CitationItem(**c) for c in final_state.get("citations", [])],
        execution_trace=[AgentTraceStep(**t) for t in final_state.get("execution_trace", [])],
        blocked=final_state.get("blocked", False),
        input_guardrail=InputGuardrailInfo(**input_guardrail) if input_guardrail else None,
        output_guardrail=OutputGuardrailInfo(**output_guardrail) if output_guardrail else None,
    )
