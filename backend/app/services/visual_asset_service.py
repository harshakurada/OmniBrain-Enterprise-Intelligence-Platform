import json
import logging
import os
import uuid
from typing import List, Optional
from pydantic import BaseModel
from backend.app.config.settings import settings
from backend.app.core.exceptions import AppException
from backend.app.database.models import ExtractedAssetModel
from backend.app.services.pdf_parser import ParsedPDFResult, ParsedTable
from backend.app.services.vision_analysis_service import VisionAnalysisService

logger = logging.getLogger("omnibrain.visual_asset")


class VisualChunkRecord(BaseModel):
    """An embeddable piece of visual content (an image description or a
    structured table), shaped identically to `TextChunk` so it can flow
    through the same embedding/indexing path as regular text chunks.
    """

    chunk_index: int
    page_number: int
    content: str
    chunk_type: str  # "image_caption" or "table"


class VisualProcessingResult(BaseModel):
    """Outcome of running visual asset processing over a parsed document."""

    chunk_records: List[VisualChunkRecord]
    asset_models: List[ExtractedAssetModel]
    images_analyzed: int
    images_skipped: int
    images_failed: int
    tables_indexed: int

    model_config = {"arbitrary_types_allowed": True}


class VisualAssetService:
    """Turns the images and tables already extracted by Module 2's
    `PDFParserService` into retrievable, citation-ready content: images are
    sent to the Vision Agent (`VisionAnalysisService`) for a structured
    description, and tables are persisted as Markdown assets. Both produce
    `VisualChunkRecord`s the ingestion pipeline embeds and indexes exactly
    like text chunks, plus `ExtractedAssetModel` rows for asset listing and
    preview.
    """

    def __init__(
        self,
        vision_analyzer: VisionAnalysisService,
        assets_dir: Optional[str] = None,
        min_image_dimension: Optional[int] = None,
        max_images_per_document: Optional[int] = None,
    ):
        self.vision_analyzer = vision_analyzer
        self.assets_dir = assets_dir or settings.ASSETS_DIR
        self.min_image_dimension = (
            min_image_dimension if min_image_dimension is not None else settings.VISION_MIN_IMAGE_DIMENSION
        )
        self.max_images_per_document = (
            max_images_per_document if max_images_per_document is not None else settings.VISION_MAX_IMAGES_PER_DOCUMENT
        )
        self._tables_dir = os.path.join(self.assets_dir, "tables")
        os.makedirs(self._tables_dir, exist_ok=True)

    def process_document_assets(
        self, parsed: ParsedPDFResult, document_id: int, start_chunk_index: int
    ) -> VisualProcessingResult:
        """Analyzes every extracted image and structures every detected table
        across `parsed.pages`. Never raises -- a failed image analysis is
        logged and skipped so one bad image cannot fail the whole document.
        """
        chunk_index = start_chunk_index
        chunk_records: List[VisualChunkRecord] = []
        asset_models: List[ExtractedAssetModel] = []
        images_analyzed = 0
        images_skipped = 0
        images_failed = 0

        for page in parsed.pages:
            for image in page.images:
                if images_analyzed >= self.max_images_per_document:
                    images_skipped += 1
                    continue
                if image.width < self.min_image_dimension or image.height < self.min_image_dimension:
                    logger.info(
                        f"Skipping decorative image on page {image.page_number} "
                        f"({image.width}x{image.height}px, below {self.min_image_dimension}px threshold)."
                    )
                    images_skipped += 1
                    continue

                try:
                    description = self.vision_analyzer.analyze_image_path(image.file_path)
                except AppException as exc:
                    logger.warning(f"Vision analysis failed for image on page {image.page_number}: {exc.message}")
                    images_failed += 1
                    continue

                images_analyzed += 1
                asset_models.append(
                    ExtractedAssetModel(
                        document_id=document_id,
                        asset_type="image",
                        page_number=image.page_number,
                        asset_path=image.file_path,
                        caption=description.description,
                        metadata_json=json.dumps(
                            {
                                "visual_type": description.visual_type,
                                "width": image.width,
                                "height": image.height,
                                "format": image.format,
                            }
                        ),
                    )
                )
                chunk_records.append(
                    VisualChunkRecord(
                        chunk_index=chunk_index,
                        page_number=image.page_number,
                        content=f"[{description.visual_type}] {description.description}",
                        chunk_type="image_caption",
                    )
                )
                chunk_index += 1

            for table in page.tables:
                asset_path = self._persist_table_markdown(document_id, table)
                caption = f"Table with {table.row_count} row(s) and {table.col_count} column(s)."
                asset_models.append(
                    ExtractedAssetModel(
                        document_id=document_id,
                        asset_type="table",
                        page_number=table.page_number,
                        asset_path=asset_path,
                        caption=caption,
                        metadata_json=json.dumps({"row_count": table.row_count, "col_count": table.col_count}),
                    )
                )
                chunk_records.append(
                    VisualChunkRecord(
                        chunk_index=chunk_index,
                        page_number=table.page_number,
                        content=table.markdown_content,
                        chunk_type="table",
                    )
                )
                chunk_index += 1

        logger.info(
            f"Visual asset processing for document_id={document_id}: "
            f"{images_analyzed} image(s) analyzed, {images_skipped} skipped, {images_failed} failed, "
            f"{parsed.total_tables} table(s) indexed."
        )

        return VisualProcessingResult(
            chunk_records=chunk_records,
            asset_models=asset_models,
            images_analyzed=images_analyzed,
            images_skipped=images_skipped,
            images_failed=images_failed,
            tables_indexed=parsed.total_tables,
        )

    def _persist_table_markdown(self, document_id: int, table: ParsedTable) -> str:
        filename = f"table_{document_id}_{uuid.uuid4().hex[:8]}_p{table.page_number}_t{table.table_index}.md"
        path = os.path.join(self._tables_dir, filename)
        with open(path, "w", encoding="utf-8") as f:
            f.write(table.markdown_content)
        return path
