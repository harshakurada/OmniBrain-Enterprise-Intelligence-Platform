import logging
from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from sqlalchemy.orm import Session
from backend.app.api.deps import get_document_ingestion_service, get_vision_analysis_service
from backend.app.core.exceptions import NotFoundException, ValidationException
from backend.app.database.connection import get_db
from backend.app.database.models import DocumentModel
from backend.app.schemas.vision import VisionAnalyzeResponse, VisualProcessingResponse
from backend.app.services.document_service import DocumentIngestionService
from backend.app.services.vision_analysis_service import VisionAnalysisService

logger = logging.getLogger("omnibrain.api.vision")
router = APIRouter()

_IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/gif"}


@router.post(
    "/vision/analyze",
    response_model=VisionAnalyzeResponse,
    status_code=status.HTTP_200_OK,
    summary="Analyze a single standalone image with the Vision model",
    response_description="Concise description and visual-type classification of the uploaded image.",
)
def analyze_image(
    file: UploadFile = File(..., description="A single image file (PNG, JPEG, WEBP, or GIF)"),
    vision_analyzer: VisionAnalysisService = Depends(get_vision_analysis_service),
) -> VisionAnalyzeResponse:
    """Runs standalone Vision Agent analysis over an uploaded image, without
    requiring it to belong to an ingested document. Useful for testing the
    Vision model or analyzing images sourced outside the PDF pipeline.
    """
    if file.content_type and file.content_type not in _IMAGE_CONTENT_TYPES:
        raise ValidationException(f"Unsupported image content-type '{file.content_type}'.")

    image_bytes = file.file.read()
    if not image_bytes:
        raise ValidationException("Uploaded image file is empty.")

    image_format = (file.filename or "image.png").rsplit(".", 1)[-1].lower()
    result = vision_analyzer.analyze_image_bytes(image_bytes, image_format=image_format)

    return VisionAnalyzeResponse(description=result.description, visual_type=result.visual_type)


@router.post(
    "/vision/documents/{document_id}/process",
    response_model=VisualProcessingResponse,
    status_code=status.HTTP_200_OK,
    summary="(Re)run visual asset processing for an ingested document",
    response_description="Counts of images analyzed/skipped/failed and tables indexed.",
)
def process_document_visuals(
    document_id: int,
    force: bool = Query(False, description="Reprocess even if visual assets already exist for this document"),
    db: Session = Depends(get_db),
    ingestion_service: DocumentIngestionService = Depends(get_document_ingestion_service),
) -> VisualProcessingResponse:
    """Extracts images/tables from the document's stored PDF (Module 2),
    analyzes each image with the Vision Agent, structures each table, and
    indexes the results into the multi-modal retrieval pipeline. Intended
    for documents ingested before Module 4 existed, or to retry after a
    partial Vision API failure.
    """
    document = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
    if not document:
        raise NotFoundException(f"Document with id={document_id} was not found.")

    result = ingestion_service.reprocess_visual_assets(document, force=force)

    return VisualProcessingResponse(
        document_id=document_id,
        images_analyzed=result.images_analyzed,
        images_skipped=result.images_skipped,
        images_failed=result.images_failed,
        tables_indexed=result.tables_indexed,
        chunks_added=len(result.chunk_records),
    )
