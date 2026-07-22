from fastapi import status
from tests._test_helpers import isolated_client, make_pdf_bytes  # noqa: F401


def test_upload_single_pdf_succeeds(isolated_client):
    pdf_bytes = make_pdf_bytes("Hello OmniBrain, this is a test document about ingestion pipelines.")

    response = isolated_client.post(
        "/api/v1/documents/upload",
        files=[("files", ("test.pdf", pdf_bytes, "application/pdf"))],
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total_files"] == 1
    assert data["successful"] == 1
    assert data["failed"] == 0

    result = data["results"][0]
    assert result["success"] is True
    assert result["status"] == "COMPLETED"
    assert result["document_id"] is not None
    assert result["page_count"] == 1
    assert result["chunk_count"] >= 1


def test_upload_rejects_non_pdf_file(isolated_client):
    response = isolated_client.post(
        "/api/v1/documents/upload",
        files=[("files", ("notes.txt", b"just some text", "text/plain"))],
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["successful"] == 0
    assert data["failed"] == 1
    assert data["results"][0]["status"] == "REJECTED"


def test_upload_batch_partial_failure_does_not_abort_other_files(isolated_client):
    good_pdf = make_pdf_bytes("Valid content for a valid PDF file.")

    response = isolated_client.post(
        "/api/v1/documents/upload",
        files=[
            ("files", ("bad.txt", b"not a pdf", "text/plain")),
            ("files", ("good.pdf", good_pdf, "application/pdf")),
        ],
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["total_files"] == 2
    assert data["successful"] == 1
    assert data["failed"] == 1

    statuses = {r["filename"]: r["status"] for r in data["results"]}
    assert statuses["bad.txt"] == "REJECTED"
    assert statuses["good.pdf"] == "COMPLETED"


def test_duplicate_upload_is_rejected(isolated_client):
    pdf_bytes = make_pdf_bytes("Duplicate detection content.")

    first = isolated_client.post(
        "/api/v1/documents/upload",
        files=[("files", ("dup.pdf", pdf_bytes, "application/pdf"))],
    )
    assert first.json()["successful"] == 1

    second = isolated_client.post(
        "/api/v1/documents/upload",
        files=[("files", ("dup.pdf", pdf_bytes, "application/pdf"))],
    )
    data = second.json()
    assert data["successful"] == 0
    assert data["failed"] == 1
    assert "already been uploaded" in data["results"][0]["message"]


def test_list_and_get_document(isolated_client):
    pdf_bytes = make_pdf_bytes("Listing and retrieval test content.")
    upload_response = isolated_client.post(
        "/api/v1/documents/upload",
        files=[("files", ("list_me.pdf", pdf_bytes, "application/pdf"))],
    )
    document_id = upload_response.json()["results"][0]["document_id"]

    list_response = isolated_client.get("/api/v1/documents")
    assert list_response.status_code == status.HTTP_200_OK
    assert list_response.json()["total"] >= 1
    assert any(doc["id"] == document_id for doc in list_response.json()["documents"])

    detail_response = isolated_client.get(f"/api/v1/documents/{document_id}")
    assert detail_response.status_code == status.HTTP_200_OK
    assert detail_response.json()["filename"] == "list_me.pdf"


def test_get_nonexistent_document_returns_404(isolated_client):
    response = isolated_client.get("/api/v1/documents/999999")
    assert response.status_code == status.HTTP_404_NOT_FOUND
