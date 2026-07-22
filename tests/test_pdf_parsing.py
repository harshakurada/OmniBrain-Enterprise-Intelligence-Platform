import os
import fitz
import pytest
from backend.app.core.exceptions import ValidationException
from backend.app.services.pdf_parser import PDFParserService


@pytest.fixture
def sample_pdf_path(tmp_path):
    """Builds a small, real two-page PDF on disk for parser tests."""
    doc = fitz.open()
    page1 = doc.new_page()
    page1.insert_text((72, 72), "Hello OmniBrain, this is page one.")
    page2 = doc.new_page()
    page2.insert_text((72, 72), "This is page two of the sample document.")

    path = tmp_path / "sample.pdf"
    doc.save(str(path))
    doc.close()
    return str(path)


def test_parse_pdf_extracts_text_and_page_numbers(sample_pdf_path, tmp_path):
    parser = PDFParserService(assets_dir=str(tmp_path / "assets"))
    result = parser.parse_pdf(sample_pdf_path, "sample.pdf")

    assert result.page_count == 2
    assert len(result.pages) == 2
    assert result.pages[0].page_number == 1
    assert "page one" in result.pages[0].text
    assert result.pages[1].page_number == 2
    assert "page two" in result.pages[1].text


def test_parse_pdf_raises_on_missing_file(tmp_path):
    parser = PDFParserService(assets_dir=str(tmp_path / "assets"))
    with pytest.raises(ValidationException):
        parser.parse_pdf(str(tmp_path / "does_not_exist.pdf"), "does_not_exist.pdf")


def test_parse_pdf_raises_on_empty_file(tmp_path):
    empty_path = tmp_path / "empty.pdf"
    empty_path.write_bytes(b"")

    parser = PDFParserService(assets_dir=str(tmp_path / "assets"))
    with pytest.raises(ValidationException):
        parser.parse_pdf(str(empty_path), "empty.pdf")
