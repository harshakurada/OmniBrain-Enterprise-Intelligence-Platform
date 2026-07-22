import io
import logging
import os
import uuid
from typing import List, Optional
import fitz  # PyMuPDF
import pdfplumber
from PIL import Image
from pydantic import BaseModel, Field
from backend.app.config.settings import settings
from backend.app.core.exceptions import ValidationException, AppException

logger = logging.getLogger("omnibrain.pdf_parser")


class ParsedTable(BaseModel):
    page_number: int
    table_index: int
    markdown_content: str
    row_count: int
    col_count: int


class ParsedImage(BaseModel):
    page_number: int
    image_index: int
    file_path: str
    width: int
    height: int
    format: str


class ParsedPage(BaseModel):
    page_number: int
    text: str
    tables: List[ParsedTable] = Field(default_factory=list)
    images: List[ParsedImage] = Field(default_factory=list)


class ParsedPDFResult(BaseModel):
    filename: str
    page_count: int
    pages: List[ParsedPage] = Field(default_factory=list)
    total_tables: int = 0
    total_images: int = 0


class PDFParserService:
    """Enterprise multi-modal PDF extractor for text, tables, and images."""

    def __init__(self, assets_dir: Optional[str] = None):
        self.assets_dir = assets_dir or settings.ASSETS_DIR
        os.makedirs(self.assets_dir, exist_ok=True)

    def parse_pdf(self, file_path: str, filename: str) -> ParsedPDFResult:
        """Parses a PDF file from disk, extracting text, markdown tables, and images per page.

        Handles corrupt, empty, and password-protected PDFs gracefully.
        """
        logger.info(f"Starting multi-modal parsing for file: {filename} ({file_path})")

        if not os.path.exists(file_path):
            raise ValidationException(f"Specified file does not exist: {filename}")

        if os.path.getsize(file_path) == 0:
            raise ValidationException(f"Uploaded file is empty: {filename}")

        # Check PyMuPDF document opening
        try:
            doc = fitz.open(file_path)
        except Exception as e:
            logger.error(f"Failed to open PDF file {filename}: {str(e)}")
            raise ValidationException(f"Corrupted or invalid PDF file: {filename}. Error: {str(e)}")

        if doc.is_encrypted:
            logger.error(f"PDF file is password protected: {filename}")
            raise ValidationException(f"PDF file is password protected/encrypted and cannot be parsed: {filename}")

        page_count = len(doc)
        if page_count == 0:
            doc.close()
            raise ValidationException(f"PDF contains 0 pages: {filename}")

        pages_result: List[ParsedPage] = []
        total_tables = 0
        total_images = 0

        # Open pdfplumber for table extraction
        try:
            plumber_doc = pdfplumber.open(file_path)
        except Exception as e:
            logger.warning(f"pdfplumber failed to open {filename}, falling back to text-only extraction: {str(e)}")
            plumber_doc = None

        try:
            for page_idx in range(page_count):
                page_num = page_idx + 1
                fitz_page = doc[page_idx]

                # 1. Extract Text
                text_content = fitz_page.get_text("text").strip()

                # 2. Extract Tables (using pdfplumber)
                page_tables: List[ParsedTable] = []
                if plumber_doc and page_idx < len(plumber_doc.pages):
                    try:
                        p_page = plumber_doc.pages[page_idx]
                        extracted_tables = p_page.extract_tables()
                        for tbl_idx, table_data in enumerate(extracted_tables):
                            if not table_data or len(table_data) == 0:
                                continue

                            # Convert 2D list to markdown
                            markdown_table = self._table_to_markdown(table_data)
                            if markdown_table:
                                parsed_tbl = ParsedTable(
                                    page_number=page_num,
                                    table_index=tbl_idx + 1,
                                    markdown_content=markdown_table,
                                    row_count=len(table_data),
                                    col_count=len(table_data[0]) if table_data[0] else 0,
                                )
                                page_tables.append(parsed_tbl)
                                total_tables += 1
                    except Exception as tbl_err:
                        logger.warning(f"Failed extracting tables on page {page_num} of {filename}: {str(tbl_err)}")

                # 3. Extract Embedded Images (using PyMuPDF)
                page_images: List[ParsedImage] = []
                try:
                    image_list = fitz_page.get_images(full=True)
                    for img_idx, img_info in enumerate(image_list):
                        xref = img_info[0]
                        base_image = doc.extract_image(xref)
                        if base_image:
                            image_bytes = base_image["image"]
                            image_ext = base_image["ext"]
                            img_filename = f"img_{uuid.uuid4().hex[:8]}_p{page_num}_i{img_idx+1}.{image_ext}"
                            img_save_path = os.path.join(self.assets_dir, img_filename)

                            with open(img_save_path, "wb") as f:
                                f.write(image_bytes)

                            # Retrieve dimensions using PIL
                            try:
                                with Image.open(io.BytesIO(image_bytes)) as pil_img:
                                    w, h = pil_img.size
                            except Exception:
                                w, h = (0, 0)

                            parsed_img = ParsedImage(
                                page_number=page_num,
                                image_index=img_idx + 1,
                                file_path=img_save_path,
                                width=w,
                                height=h,
                                format=image_ext,
                            )
                            page_images.append(parsed_img)
                            total_images += 1
                except Exception as img_err:
                    logger.warning(f"Failed extracting images on page {page_num} of {filename}: {str(img_err)}")

                pages_result.append(
                    ParsedPage(
                        page_number=page_num,
                        text=text_content,
                        tables=page_tables,
                        images=page_images,
                    )
                )

        finally:
            doc.close()
            if plumber_doc:
                plumber_doc.close()

        logger.info(
            f"Parsed {filename} successfully: {page_count} pages, {total_tables} tables, {total_images} images."
        )

        return ParsedPDFResult(
            filename=filename,
            page_count=page_count,
            pages=pages_result,
            total_tables=total_tables,
            total_images=total_images,
        )

    def _table_to_markdown(self, table_data: List[List[Optional[str]]]) -> str:
        """Converts raw pdfplumber table rows into clean Markdown table format."""
        if not table_data or len(table_data) == 0:
            return ""

        def clean_cell(cell: Optional[str]) -> str:
            if cell is None:
                return ""
            return str(cell).replace("\n", " ").replace("|", "\\|").strip()

        # Build header
        header = [clean_cell(c) for c in table_data[0]]
        header_str = "| " + " | ".join(header) + " |"
        separator_str = "| " + " | ".join(["---"] * len(header)) + " |"

        # Build rows
        rows_str = []
        for row in table_data[1:]:
            cleaned_row = [clean_cell(c) for c in row]
            # Pad or trim row to match header length
            if len(cleaned_row) < len(header):
                cleaned_row.extend([""] * (len(header) - len(cleaned_row)))
            elif len(cleaned_row) > len(header):
                cleaned_row = cleaned_row[: len(header)]
            rows_str.append("| " + " | ".join(cleaned_row) + " |")

        return "\n".join([header_str, separator_str] + rows_str)
