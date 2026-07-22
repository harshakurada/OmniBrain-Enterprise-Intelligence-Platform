from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class VisionAnalyzeResponse(BaseModel):
    """Response for ad-hoc, standalone image analysis (not tied to a document)."""

    description: str = Field(..., description="Concise factual description of the image")
    visual_type: str = Field(..., description="One of: chart, graph, table, diagram, screenshot, photo, other")


class ExtractedAssetSummary(BaseModel):
    """A single extracted visual asset (image or table) belonging to a document."""

    id: int
    document_id: int
    asset_type: str = Field(..., description="'image' or 'table'")
    page_number: int
    caption: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentAssetsResponse(BaseModel):
    """List of extracted visual assets for a single document."""

    document_id: int
    total: int
    assets: List[ExtractedAssetSummary]


class VisualProcessingResponse(BaseModel):
    """Outcome of (re)running visual asset processing for a document."""

    document_id: int
    images_analyzed: int
    images_skipped: int
    images_failed: int
    tables_indexed: int
    chunks_added: int
