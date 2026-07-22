from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class DocumentUploadItemResult(BaseModel):
    """Outcome of processing a single file within an upload batch."""

    filename: str = Field(..., description="Original name of the uploaded file")
    success: bool = Field(..., description="Whether the file was ingested successfully")
    status: str = Field(..., description="Final document status: COMPLETED, FAILED, or REJECTED")
    document_id: Optional[int] = Field(None, description="Database id of the created document, if any")
    page_count: Optional[int] = Field(None, description="Number of pages extracted")
    chunk_count: Optional[int] = Field(None, description="Number of text chunks generated and indexed")
    message: Optional[str] = Field(None, description="Human-readable status or error message")


class DocumentUploadResponse(BaseModel):
    """Response returned for a (possibly multi-file) upload request."""

    total_files: int
    successful: int
    failed: int
    results: List[DocumentUploadItemResult]


class DocumentSummary(BaseModel):
    """Lightweight document metadata used in list views."""

    id: int
    filename: str
    status: str
    file_size: int
    page_count: int
    table_count: int
    image_count: int
    chunk_count: int
    error_message: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentListResponse(BaseModel):
    total: int
    documents: List[DocumentSummary]
