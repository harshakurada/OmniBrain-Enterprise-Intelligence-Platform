from datetime import datetime
import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy import text
from sqlalchemy.orm import Session
from backend.app.config.settings import settings
from backend.app.database.connection import get_db
from backend.app.schemas.health import HealthCheckResponse, DatabaseStatus

logger = logging.getLogger("omnibrain.api.health")
router = APIRouter()


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    status_code=status.HTTP_200_OK,
    summary="Perform a Health Check",
    response_description="Return the health status of the API and database.",
)
def check_health(db: Session = Depends(get_db)) -> HealthCheckResponse:
    """Endpoint to verify API service status, environment details, and verify

    that the SQLite database connection is fully active.
    """
    db_status = "healthy"
    db_details = None

    try:
        # Run a simple SQL query to test connectivity
        db.execute(text("SELECT 1"))
    except Exception as e:
        logger.exception("Healthcheck failed to query database.")
        db_status = "unhealthy"
        db_details = str(e)

    # Determine overall status
    overall_status = "healthy" if db_status == "healthy" else "unhealthy"

    return HealthCheckResponse(
        status=overall_status,
        environment=settings.ENVIRONMENT,
        database=DatabaseStatus(status=db_status, details=db_details),
        timestamp=datetime.utcnow().isoformat() + "Z",
    )
