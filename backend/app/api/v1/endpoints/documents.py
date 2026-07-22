import logging
import os
from typing import List
from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from backend.app.api.deps import get_document_ingestion_service
from backend.app.core.exceptions import AppException, NotFoundException
from backend.app.database.connection import get_db
from backend.app.database.models import DocumentModel, ExtractedAssetModel
from backend.app.schemas.document import (
    DocumentListResponse,
    DocumentSummary,
    DocumentUploadItemResult,
    DocumentUploadResponse,
)
from backend.app.schemas.vision import DocumentAssetsResponse, ExtractedAssetSummary
from backend.app.services.document_service import DocumentIngestionService

logger = logging.getLogger("omnibrain.api.documents")
router = APIRouter()


@router.post(
    "/documents/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_200_OK,
    summary="Upload one or more PDF documents for ingestion",
    response_description="Per-file ingestion status, including page and chunk counts.",
)
def upload_documents(
    files: List[UploadFile] = File(..., description="One or more PDF files to ingest"),
    ingestion_service: DocumentIngestionService = Depends(get_document_ingestion_service),
) -> DocumentUploadResponse:
    """Uploads and synchronously processes one or more PDF files through
    the full ingestion pipeline: validation, storage, multi-modal
    parsing, recursive chunking, embedding generation, and vector
    indexing. Each file is processed independently -- a failure on one
    file does not abort the rest of the batch.
    """
    results: List[DocumentUploadItemResult] = []

    for upload in files:
        filename = upload.filename or "unnamed.pdf"
        try:
            file_bytes = upload.file.read()
            document = ingestion_service.ingest_file(
                file_bytes=file_bytes,
                filename=filename,
                content_type=upload.content_type,
            )
            results.append(
                DocumentUploadItemResult(
                    filename=filename,
                    success=document.status == "COMPLETED",
                    status=document.status,
                    document_id=document.id,
                    page_count=document.page_count,
                    chunk_count=document.chunk_count,
                    message=document.error_message or "Document ingested successfully.",
                )
            )
        except AppException as exc:
            logger.warning(f"Rejected upload '{filename}': {exc.message}")
            results.append(
                DocumentUploadItemResult(
                    filename=filename,
                    success=False,
                    status="REJECTED",
                    message=exc.message,
                )
            )
        except Exception as exc:
            logger.exception(f"Unexpected error ingesting '{filename}'.")
            results.append(
                DocumentUploadItemResult(
                    filename=filename,
                    success=False,
                    status="FAILED",
                    message=f"Unexpected error: {exc}",
                )
            )
        finally:
            upload.file.close()

    return DocumentUploadResponse(
        total_files=len(results),
        successful=sum(1 for r in results if r.success),
        failed=sum(1 for r in results if not r.success),
        results=results,
    )


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    status_code=status.HTTP_200_OK,
    summary="List all ingested documents",
)
def list_documents(db: Session = Depends(get_db)) -> DocumentListResponse:
    """Returns metadata for every document that has been uploaded, most
    recently created first.
    """
    documents = db.query(DocumentModel).order_by(DocumentModel.created_at.desc()).all()
    return DocumentListResponse(
        total=len(documents),
        documents=[DocumentSummary.model_validate(doc) for doc in documents],
    )


@router.get(
    "/documents/{document_id}",
    response_model=DocumentSummary,
    status_code=status.HTTP_200_OK,
    summary="Get metadata for a single document",
)
def get_document(document_id: int, db: Session = Depends(get_db)) -> DocumentSummary:
    """Returns metadata for a single document by id, or 404 if not found."""
    document = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
    if not document:
        raise NotFoundException(f"Document with id={document_id} was not found.")
    return DocumentSummary.model_validate(document)


@router.get(
    "/documents/{document_id}/assets",
    response_model=DocumentAssetsResponse,
    status_code=status.HTTP_200_OK,
    summary="List extracted visual assets (images and tables) for a document",
)
def list_document_assets(document_id: int, db: Session = Depends(get_db)) -> DocumentAssetsResponse:
    """Returns every image/table extracted from the document by Module 2's
    parser and analyzed/structured by Module 4's Vision Agent pipeline.
    """
    document = db.query(DocumentModel).filter(DocumentModel.id == document_id).first()
    if not document:
        raise NotFoundException(f"Document with id={document_id} was not found.")

    assets = (
        db.query(ExtractedAssetModel)
        .filter(ExtractedAssetModel.document_id == document_id)
        .order_by(ExtractedAssetModel.page_number.asc())
        .all()
    )
    return DocumentAssetsResponse(
        document_id=document_id,
        total=len(assets),
        assets=[ExtractedAssetSummary.model_validate(a) for a in assets],
    )


@router.get(
    "/documents/{document_id}/assets/{asset_id}/file",
    status_code=status.HTTP_200_OK,
    summary="Download the raw file for an extracted visual asset (image or table markdown)",
)
def get_document_asset_file(document_id: int, asset_id: int, db: Session = Depends(get_db)) -> FileResponse:
    """Streams the extracted asset's underlying file back to the caller, so
    the frontend can preview images without needing filesystem access to
    the backend's storage directory.
    """
    asset = (
        db.query(ExtractedAssetModel)
        .filter(ExtractedAssetModel.id == asset_id, ExtractedAssetModel.document_id == document_id)
        .first()
    )
    if not asset or not os.path.exists(asset.asset_path):
        raise NotFoundException(f"Asset file for asset_id={asset_id} was not found.")

    return FileResponse(asset.asset_path)
