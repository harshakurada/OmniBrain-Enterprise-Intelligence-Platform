import hashlib
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from sqlalchemy.orm import Session
from backend.app.config.settings import settings
from backend.app.core.exceptions import AppException, ValidationException
from backend.app.database.models import DocumentChunkModel, DocumentModel, ExtractedAssetModel
from backend.app.services.chunking_service import RecursiveChunkingService
from backend.app.services.embedding_service import EmbeddingService
from backend.app.services.pdf_parser import PDFParserService
from backend.app.services.vector_store_service import (
    VectorRecord,
    VectorStoreBase,
    generate_vector_id,
)
from backend.app.services.visual_asset_service import VisualAssetService, VisualProcessingResult

logger = logging.getLogger("omnibrain.document_service")

ALLOWED_CONTENT_TYPES = {"application/pdf"}
ALLOWED_EXTENSIONS = {".pdf"}


class DocumentIngestionService:
    """Orchestrates the full document ingestion pipeline: validation,
    storage, multi-modal parsing, chunking, embedding, and vector
    indexing. Persists metadata for every stage to SQLite so progress
    and failures are always inspectable via the Documents API.
    """

    def __init__(
        self,
        db: Session,
        pdf_parser: PDFParserService,
        chunker: RecursiveChunkingService,
        embedder: EmbeddingService,
        vector_store: VectorStoreBase,
        visual_asset_service: Optional[VisualAssetService] = None,
    ):
        self.db = db
        self.pdf_parser = pdf_parser
        self.chunker = chunker
        self.embedder = embedder
        self.vector_store = vector_store
        self.visual_asset_service = visual_asset_service
        os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

    def validate_upload(self, filename: str, content_type: Optional[str], size: int) -> None:
        """Validates file type and size before any processing begins."""
        _, ext = os.path.splitext(filename.lower())
        if ext not in ALLOWED_EXTENSIONS:
            raise ValidationException(f"Unsupported file type '{ext}'. Only PDF files are accepted.")

        if content_type and content_type not in ALLOWED_CONTENT_TYPES:
            logger.warning(f"Unexpected content-type '{content_type}' for file '{filename}'; proceeding based on extension.")

        max_bytes = settings.MAX_FILE_SIZE_MB * 1024 * 1024
        if size > max_bytes:
            raise ValidationException(
                f"File '{filename}' exceeds the maximum allowed size of {settings.MAX_FILE_SIZE_MB} MB."
            )
        if size == 0:
            raise ValidationException(f"File '{filename}' is empty.")

    def ingest_file(self, file_bytes: bytes, filename: str, content_type: Optional[str] = None) -> DocumentModel:
        """Validates, stores, parses, chunks, embeds, and indexes a single
        PDF file, persisting a `DocumentModel` row that tracks its status
        through the pipeline (PENDING -> PROCESSING -> COMPLETED/FAILED).
        """
        self.validate_upload(filename, content_type, len(file_bytes))

        file_hash = hashlib.sha256(file_bytes).hexdigest()
        existing = self.db.query(DocumentModel).filter(DocumentModel.file_hash == file_hash).first()
        if existing:
            raise ValidationException(
                f"File '{filename}' has already been uploaded (document_id={existing.id}, status={existing.status}).",
                details={"document_id": existing.id, "status": existing.status},
            )

        stored_filename = f"{uuid.uuid4().hex}_{filename}"
        stored_path = os.path.join(settings.UPLOAD_DIR, stored_filename)
        with open(stored_path, "wb") as f:
            f.write(file_bytes)

        document = DocumentModel(
            filename=filename,
            file_hash=file_hash,
            file_size=len(file_bytes),
            content_type=content_type or "application/pdf",
            file_path=stored_path,
            status="PROCESSING",
        )
        self.db.add(document)
        self.db.commit()
        self.db.refresh(document)

        try:
            self._process_document(document, stored_path, filename)
        except AppException:
            self._mark_failed(document, "Processing failed due to a known application error.")
            raise
        except Exception as exc:
            logger.exception(f"Unexpected failure while processing document '{filename}'.")
            self._mark_failed(document, str(exc))
            raise

        return document

    def _process_document(self, document: DocumentModel, stored_path: str, filename: str) -> None:
        parsed = self.pdf_parser.parse_pdf(stored_path, filename)
        chunks = self.chunker.chunk_document(parsed.pages)

        # Module 4: analyze extracted images (Vision Agent) and structure detected
        # tables into the same embeddable shape as text chunks, so multi-modal
        # content is retrievable through the existing search pipeline unchanged.
        visual_result = None
        if self.visual_asset_service is not None:
            visual_result = self.visual_asset_service.process_document_assets(
                parsed=parsed, document_id=document.id, start_chunk_index=len(chunks)
            )

        combined_records = [
            {"chunk_index": c.chunk_index, "page_number": c.page_number, "content": c.content, "chunk_type": "text"}
            for c in chunks
        ]
        if visual_result:
            combined_records.extend(record.model_dump() for record in visual_result.chunk_records)

        document.page_count = parsed.page_count
        document.table_count = parsed.total_tables
        document.image_count = parsed.total_images

        if not combined_records:
            logger.warning(
                f"No extractable text or visual content found in '{filename}'; marking document COMPLETED with 0 chunks."
            )
            document.status = "COMPLETED"
            document.chunk_count = 0
            self.db.commit()
            return

        embeddings = self.embedder.generate_embeddings([r["content"] for r in combined_records])
        vector_records, chunk_models = self._build_indexed_chunks(document, combined_records, embeddings)

        self.vector_store.upsert(vector_records)

        self.db.add_all(chunk_models)
        if visual_result and visual_result.asset_models:
            self.db.add_all(visual_result.asset_models)

        document.status = "COMPLETED"
        document.chunk_count = len(chunk_models)
        self.db.commit()
        self.db.refresh(document)

        logger.info(
            f"Document '{filename}' (id={document.id}) processed successfully: "
            f"{document.page_count} page(s), {document.chunk_count} chunk(s) "
            f"(text={len(chunks)}, visual={len(combined_records) - len(chunks)}), "
            f"vector backend={self.vector_store.backend_name}."
        )

    def reprocess_visual_assets(self, document: DocumentModel, force: bool = False) -> VisualProcessingResult:
        """Re-parses the document's stored PDF and (re)runs Vision Agent
        analysis plus table structuring, indexing any newly produced visual
        chunks alongside the document's existing text chunks. Intended for
        documents ingested before visual processing was enabled, or to
        retry after a partial Vision API failure.
        """
        if self.visual_asset_service is None:
            raise AppException("Visual asset processing is not configured for this service instance.")

        existing_assets = (
            self.db.query(ExtractedAssetModel).filter(ExtractedAssetModel.document_id == document.id).count()
        )
        if existing_assets > 0 and not force:
            raise ValidationException(
                f"Document {document.id} already has {existing_assets} extracted visual asset(s). "
                "Pass force=true to reprocess and add another pass.",
                details={"existing_assets": existing_assets},
            )

        parsed = self.pdf_parser.parse_pdf(document.file_path, document.filename)
        visual_result = self.visual_asset_service.process_document_assets(
            parsed=parsed, document_id=document.id, start_chunk_index=document.chunk_count
        )

        document.image_count = parsed.total_images
        document.table_count = parsed.total_tables

        if visual_result.chunk_records:
            records = [r.model_dump() for r in visual_result.chunk_records]
            embeddings = self.embedder.generate_embeddings([r["content"] for r in records])
            vector_records, chunk_models = self._build_indexed_chunks(document, records, embeddings)

            self.vector_store.upsert(vector_records)
            self.db.add_all(chunk_models)
            self.db.add_all(visual_result.asset_models)
            document.chunk_count = document.chunk_count + len(chunk_models)

        self.db.commit()
        self.db.refresh(document)

        logger.info(
            f"Reprocessed visual assets for document {document.id}: "
            f"{visual_result.images_analyzed} image(s) analyzed, {visual_result.tables_indexed} table(s) indexed."
        )
        return visual_result

    def _build_indexed_chunks(
        self, document: DocumentModel, records: List[Dict[str, Any]], embeddings: List[List[float]]
    ) -> Tuple[List[VectorRecord], List[DocumentChunkModel]]:
        """Builds parallel `VectorRecord`/`DocumentChunkModel` lists for a
        batch of chunk-shaped records (`chunk_index`, `page_number`,
        `content`, `chunk_type`) and their corresponding embeddings. Shared
        by both initial ingestion and visual asset reprocessing.
        """
        vector_records: List[VectorRecord] = []
        chunk_models: List[DocumentChunkModel] = []
        for record, vector in zip(records, embeddings):
            vector_id = generate_vector_id()
            vector_records.append(
                VectorRecord(
                    id=vector_id,
                    vector=vector,
                    payload={
                        "document_id": document.id,
                        "filename": document.filename,
                        "page_number": record["page_number"],
                        "chunk_index": record["chunk_index"],
                        "content": record["content"],
                        "chunk_type": record["chunk_type"],
                    },
                )
            )
            chunk_models.append(
                DocumentChunkModel(
                    document_id=document.id,
                    chunk_index=record["chunk_index"],
                    page_number=record["page_number"],
                    chunk_type=record["chunk_type"],
                    content=record["content"],
                    vector_id=vector_id,
                    metadata_json=json.dumps(
                        {
                            "char_count": len(record["content"]),
                            "vector_backend": self.vector_store.backend_name,
                            "embedded_at": datetime.now(timezone.utc).isoformat(),
                        }
                    ),
                )
            )
        return vector_records, chunk_models

    def _mark_failed(self, document: DocumentModel, error_message: str) -> None:
        document.status = "FAILED"
        document.error_message = error_message[:2000]
        self.db.commit()
