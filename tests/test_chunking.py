import pytest
from backend.app.services.chunking_service import RecursiveChunkingService
from backend.app.services.pdf_parser import ParsedPage


def make_page(page_number: int, text: str) -> ParsedPage:
    return ParsedPage(page_number=page_number, text=text, tables=[], images=[])


def test_chunk_document_preserves_page_numbers():
    chunker = RecursiveChunkingService(chunk_size=50, chunk_overlap=10)
    pages = [
        make_page(1, "Alpha beta gamma delta epsilon zeta eta theta iota kappa. " * 3),
        make_page(2, "Second page content that should map to page number two only."),
    ]

    chunks = chunker.chunk_document(pages)

    assert len(chunks) > 0
    assert all(c.page_number in (1, 2) for c in chunks)
    page_1_chunks = [c for c in chunks if c.page_number == 1]
    page_2_chunks = [c for c in chunks if c.page_number == 2]
    assert page_1_chunks
    assert page_2_chunks


def test_chunk_index_is_sequential_across_document():
    chunker = RecursiveChunkingService(chunk_size=30, chunk_overlap=5)
    pages = [
        make_page(1, "word " * 40),
        make_page(2, "term " * 40),
    ]

    chunks = chunker.chunk_document(pages)
    indices = [c.chunk_index for c in chunks]

    assert indices == list(range(len(chunks)))


def test_chunk_size_is_respected():
    chunk_size = 40
    chunker = RecursiveChunkingService(chunk_size=chunk_size, chunk_overlap=5)
    pages = [make_page(1, "x" * 500)]

    chunks = chunker.chunk_document(pages)

    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk.content) <= chunk_size


def test_empty_page_text_produces_no_chunks():
    chunker = RecursiveChunkingService(chunk_size=100, chunk_overlap=10)
    pages = [make_page(1, "   "), make_page(2, "")]

    chunks = chunker.chunk_document(pages)

    assert chunks == []


def test_invalid_overlap_raises_value_error():
    with pytest.raises(ValueError):
        RecursiveChunkingService(chunk_size=100, chunk_overlap=200)


def test_chunk_size_and_overlap_are_configurable():
    custom_chunker = RecursiveChunkingService(chunk_size=123, chunk_overlap=17)

    assert custom_chunker.chunk_size == 123
    assert custom_chunker.chunk_overlap == 17
