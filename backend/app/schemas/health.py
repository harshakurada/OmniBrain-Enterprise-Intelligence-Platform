from typing import Optional
from pydantic import BaseModel, Field


class DatabaseStatus(BaseModel):
    status: str = Field(..., description="Status of the database connection ('healthy' or 'unhealthy')")
    details: Optional[str] = Field(None, description="Optional details or error message if unhealthy")


class HealthCheckResponse(BaseModel):
    status: str = Field(..., description="Overall health status of the API ('healthy' or 'unhealthy')")
    environment: str = Field(..., description="Active execution environment (e.g. development, production)")
    database: DatabaseStatus = Field(..., description="Health status of the underlying database connection")
    timestamp: str = Field(..., description="ISO 8601 formatted current timestamp")
