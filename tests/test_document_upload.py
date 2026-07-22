from fastapi import status
from backend.app.api.deps import get_embedding_service
from backend.app.main import app
from tests._test_helpers import FakeEmbeddingService, isolated_client, make_pdf_bytes  # noqa: F401


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


def test_failed_upload_can_be_retried_instead_of_permanently_blocked(isolated_client):
    """Regression test: a transient processing failure (e.g. an embedding
    API error partway through a large upload) must not permanently block
    every future re-upload of that same file via the duplicate-hash check.
    """
    pdf_bytes = make_pdf_bytes("Content that will fail to embed on the first attempt.")

    class BrokenEmbeddingService:
        def generate_embeddings(self, texts):
            raise RuntimeError("Simulated embedding API failure.")

    # First attempt: embedding fails, document is marked FAILED.
    app.dependency_overrides[get_embedding_service] = lambda: BrokenEmbeddingService()
    first = isolated_client.post(
        "/api/v1/documents/upload",
        files=[("files", ("retry_me.pdf", pdf_bytes, "application/pdf"))],
    )
    first_result = first.json()["results"][0]
    assert first_result["status"] == "FAILED"
    assert first_result["success"] is False
    # Regression: a failed upload must still surface a document_id so the
    # caller can inspect/correlate it (previously this was always null).
    assert first_result["document_id"] is not None
    first_document_id = first_result["document_id"]

    # Second attempt with the same file content: must retry (reusing the
    # same document row), not be rejected as "already uploaded".
    app.dependency_overrides[get_embedding_service] = lambda: FakeEmbeddingService()
    second = isolated_client.post(
        "/api/v1/documents/upload",
        files=[("files", ("retry_me.pdf", pdf_bytes, "application/pdf"))],
    )
    second_result = second.json()["results"][0]
    assert second_result["success"] is True
    assert second_result["status"] == "COMPLETED"
    assert second_result["document_id"] == first_document_id  # same row, reused

    detail = isolated_client.get(f"/api/v1/documents/{first_document_id}").json()
    assert detail["status"] == "COMPLETED"
    assert detail["error_message"] is None


def test_failed_upload_persists_full_error_details_for_diagnosis(isolated_client):
    """Regression test: the root-cause detail of a processing failure (e.g.
    'Connection error' from the OpenAI client) must be persisted on the
    document and returned by the API, not just a generic message -- so the
    failure is diagnosable without needing live backend terminal/log access.
    """
    from backend.app.core.exceptions import ExternalAPIException

    pdf_bytes = make_pdf_bytes("Content whose embedding call fails with a specific root cause.")

    class BrokenEmbeddingServiceWithDetails:
        def generate_embeddings(self, texts):
            raise ExternalAPIException(
                message="Failed to generate embeddings via OpenAI after multiple retries.",
                details="APIConnectionError: Connection error.",
            )

    app.dependency_overrides[get_embedding_service] = lambda: BrokenEmbeddingServiceWithDetails()
    response = isolated_client.post(
        "/api/v1/documents/upload",
        files=[("files", ("diagnose_me.pdf", pdf_bytes, "application/pdf"))],
    )
    result = response.json()["results"][0]
    assert result["status"] == "FAILED"
    assert "Connection error" in result["message"]

    detail = isolated_client.get(f"/api/v1/documents/{result['document_id']}").json()
    assert "Connection error" in detail["error_message"]
