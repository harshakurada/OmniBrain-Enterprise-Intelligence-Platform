import logging
import uuid
from typing import List
from fastapi import APIRouter, Depends, Query, status
from backend.app.api.deps import get_evaluation_history_store, get_evaluation_service
from backend.app.core.exceptions import NotFoundException
from backend.app.evaluation.evaluation_service import EvaluationHistoryStore, EvaluationReport, EvaluationService
from backend.app.schemas.evaluation import EvaluateRequest

logger = logging.getLogger("omnibrain.api.evaluation")
router = APIRouter()


@router.post(
    "/evaluation/evaluate",
    response_model=EvaluationReport,
    status_code=status.HTTP_200_OK,
    summary="Run the evaluation pipeline over an ad-hoc orchestration-shaped payload",
)
def evaluate(
    request: EvaluateRequest,
    evaluation_service: EvaluationService = Depends(get_evaluation_service),
    history: EvaluationHistoryStore = Depends(get_evaluation_history_store),
) -> EvaluationReport:
    """Computes retrieval-quality, citation-coverage, and grounding metrics
    for an arbitrary (not necessarily live) orchestration result -- useful
    for testing or offline analysis without a running LangGraph invocation.
    The resulting report is stored the same way an automatic `/orchestrate`
    evaluation is, so it's fetchable via `GET /evaluation/reports/{thread_id}`.
    """
    thread_id = request.thread_id or f"adhoc-{uuid.uuid4().hex[:8]}"
    report = evaluation_service.evaluate(thread_id, request.model_dump())
    history.add(report)
    return report


@router.get(
    "/evaluation/reports",
    response_model=List[EvaluationReport],
    status_code=status.HTTP_200_OK,
    summary="List recent automatic evaluation reports",
)
def list_reports(
    limit: int = Query(50, ge=1, le=200),
    history: EvaluationHistoryStore = Depends(get_evaluation_history_store),
) -> List[EvaluationReport]:
    """Every `/orchestrate` call is automatically evaluated and recorded
    here; this returns the most recent reports.
    """
    return history.list_recent(limit=limit)


@router.get(
    "/evaluation/reports/{thread_id}",
    response_model=EvaluationReport,
    status_code=status.HTTP_200_OK,
    summary="Fetch a single evaluation report by thread id",
)
def get_report(
    thread_id: str,
    history: EvaluationHistoryStore = Depends(get_evaluation_history_store),
) -> EvaluationReport:
    report = history.get(thread_id)
    if not report:
        raise NotFoundException(f"No evaluation report found for thread_id={thread_id}.")
    return report
