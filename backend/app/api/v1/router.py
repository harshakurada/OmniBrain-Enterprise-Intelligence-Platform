from fastapi import APIRouter
from backend.app.api.v1.endpoints import (
    documents,
    evaluation,
    guardrails,
    health,
    observability,
    orchestrator,
    search,
    sql,
    vision,
)

api_router = APIRouter()

# Include routers
api_router.include_router(health.router, tags=["Health"])
api_router.include_router(documents.router, tags=["Documents"])
api_router.include_router(search.router, tags=["Search"])
api_router.include_router(orchestrator.router, tags=["Orchestrator"])
api_router.include_router(vision.router, tags=["Vision"])
api_router.include_router(sql.router, tags=["SQL"])
api_router.include_router(guardrails.router, tags=["Guardrails"])
api_router.include_router(evaluation.router, tags=["Evaluation"])
api_router.include_router(observability.router, tags=["Observability"])
