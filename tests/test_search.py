import pytest
from fastapi import status
from tests._test_helpers import isolated_client, make_pdf_bytes  # noqa: F401

SAMPLE_TEXT = "OmniBrain semantic retrieval test passage about quarterly revenue growth."


def _upload_pdf(client, filename: str, text: str) -> int:
    pdf_bytes = make_pdf_bytes(text)
    response = client.post(
        "/api/v1/documents/upload",
        files=[("files", (filename, pdf_bytes, "application/pdf"))],
    )
    return response.json()["results"][0]["document_id"]


def test_search_returns_relevant_chunk_with_citation_metadata(isolated_client):
    document_id = _upload_pdf(isolated_client, "revenue.pdf", SAMPLE_TEXT)

    response = isolated_client.post(
        "/api/v1/search",
        json={"query": SAMPLE_TEXT, "top_k": 3},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total_results"] >= 1
    assert data["vector_backend"] == "faiss"

    top_result = data["results"][0]
    assert top_result["document_id"] == document_id
    assert top_result["filename"] == "revenue.pdf"
    assert top_result["page_number"] == 1
    assert "content" in top_result
    assert top_result["similarity_score"] == pytest.approx(1.0, abs=1e-3)


def test_search_can_be_scoped_to_a_single_document(isolated_client):
    doc_a = _upload_pdf(isolated_client, "doc_a.pdf", "Alpha content about apples and oranges.")
    _upload_pdf(isolated_client, "doc_b.pdf", "Beta content about apples and oranges too.")

    response = isolated_client.post(
        "/api/v1/search",
        json={"query": "apples and oranges", "top_k": 5, "document_id": doc_a},
    )

    assert response.status_code == status.HTTP_200_OK
    results = response.json()["results"]
    assert len(results) >= 1
    assert all(r["document_id"] == doc_a for r in results)


def test_search_with_no_indexed_documents_returns_empty_results(isolated_client):
    response = isolated_client.post(
        "/api/v1/search",
        json={"query": "anything at all", "top_k": 5},
    )

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["total_results"] == 0
    assert response.json()["results"] == []


def test_search_rejects_empty_query(isolated_client):
    response = isolated_client.post("/api/v1/search", json={"query": "", "top_k": 5})
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
