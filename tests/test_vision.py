import os
import pytest
from fastapi import status
from backend.app.api.deps import get_vision_analysis_service
from backend.app.core.exceptions import ExternalAPIException
from backend.app.main import app
from backend.app.services.pdf_parser import PDFParserService
from backend.app.services.vision_analysis_service import VisionAnalysisService, VisionDescription
from backend.app.services.visual_asset_service import VisualAssetService
from tests._test_helpers import (  # noqa: F401
    FakeVisionAnalysisService,
    isolated_client,
    isolated_orchestrator_client,
    make_pdf_bytes,
    make_pdf_with_image_bytes,
    make_pdf_with_table_bytes,
)

# ---------------------------------------------------------------------------
# Image extraction (Module 2 parser, exercised again here for Module 4 use)
# ---------------------------------------------------------------------------


def test_pdf_parser_extracts_embedded_image_with_page_and_dimensions(tmp_path):
    pdf_bytes = make_pdf_with_image_bytes(image_size=(100, 80))
    pdf_path = tmp_path / "img.pdf"
    pdf_path.write_bytes(pdf_bytes)

    parser = PDFParserService(assets_dir=str(tmp_path / "assets"))
    result = parser.parse_pdf(str(pdf_path), "img.pdf")

    assert result.total_images == 1
    image = result.pages[0].images[0]
    assert image.page_number == 1
    assert (image.width, image.height) == (100, 80)
    assert os.path.exists(image.file_path)


# ---------------------------------------------------------------------------
# Table detection (Module 2 parser)
# ---------------------------------------------------------------------------


def test_pdf_parser_detects_ruled_table_with_structured_content(tmp_path):
    pdf_bytes = make_pdf_with_table_bytes()
    pdf_path = tmp_path / "table.pdf"
    pdf_path.write_bytes(pdf_bytes)

    parser = PDFParserService(assets_dir=str(tmp_path / "assets"))
    result = parser.parse_pdf(str(pdf_path), "table.pdf")

    assert result.total_tables == 1
    table = result.pages[0].tables[0]
    assert table.page_number == 1
    assert table.row_count == 2
    assert table.col_count == 3
    assert "Segment" in table.markdown_content


# ---------------------------------------------------------------------------
# Vision processing (VisionAnalysisService + VisualAssetService)
# ---------------------------------------------------------------------------


def test_visual_asset_service_analyzes_images_into_embeddable_chunks(tmp_path):
    pdf_bytes = make_pdf_with_image_bytes()
    pdf_path = tmp_path / "img.pdf"
    pdf_path.write_bytes(pdf_bytes)

    parser = PDFParserService(assets_dir=str(tmp_path / "assets"))
    parsed = parser.parse_pdf(str(pdf_path), "img.pdf")

    service = VisualAssetService(vision_analyzer=FakeVisionAnalysisService())
    result = service.process_document_assets(parsed=parsed, document_id=1, start_chunk_index=5)

    assert result.images_analyzed == 1
    assert result.images_failed == 0
    assert len(result.chunk_records) == 1
    chunk = result.chunk_records[0]
    assert chunk.chunk_index == 5
    assert chunk.chunk_type == "image_caption"
    assert "bar chart" in chunk.content

    assert len(result.asset_models) == 1
    asset = result.asset_models[0]
    assert asset.asset_type == "image"
    assert asset.caption == "A bar chart showing quarterly revenue growth."


def test_visual_asset_service_indexes_tables_as_markdown(tmp_path):
    pdf_bytes = make_pdf_with_table_bytes()
    pdf_path = tmp_path / "table.pdf"
    pdf_path.write_bytes(pdf_bytes)

    parser = PDFParserService(assets_dir=str(tmp_path / "assets"))
    parsed = parser.parse_pdf(str(pdf_path), "table.pdf")

    service = VisualAssetService(vision_analyzer=FakeVisionAnalysisService())
    result = service.process_document_assets(parsed=parsed, document_id=1, start_chunk_index=0)

    assert result.tables_indexed == 1
    chunk = result.chunk_records[0]
    assert chunk.chunk_type == "table"
    assert "Segment" in chunk.content

    asset = result.asset_models[0]
    assert asset.asset_type == "table"
    assert os.path.exists(asset.asset_path)
    with open(asset.asset_path, encoding="utf-8") as f:
        assert "Segment" in f.read()


def test_visual_asset_service_skips_decorative_icons_below_size_threshold(tmp_path):
    pdf_bytes = make_pdf_with_image_bytes(image_size=(10, 10))
    pdf_path = tmp_path / "icon.pdf"
    pdf_path.write_bytes(pdf_bytes)

    parser = PDFParserService(assets_dir=str(tmp_path / "assets"))
    parsed = parser.parse_pdf(str(pdf_path), "icon.pdf")

    service = VisualAssetService(vision_analyzer=FakeVisionAnalysisService(), min_image_dimension=32)
    result = service.process_document_assets(parsed=parsed, document_id=1, start_chunk_index=0)

    assert result.images_analyzed == 0
    assert result.images_skipped == 1
    assert result.chunk_records == []


def test_visual_asset_service_handles_vision_failure_without_crashing(tmp_path):
    class BrokenVisionAnalyzer:
        def analyze_image_path(self, image_path):
            raise ExternalAPIException(message="Vision API unavailable")

    pdf_bytes = make_pdf_with_image_bytes()
    pdf_path = tmp_path / "img.pdf"
    pdf_path.write_bytes(pdf_bytes)

    parser = PDFParserService(assets_dir=str(tmp_path / "assets"))
    parsed = parser.parse_pdf(str(pdf_path), "img.pdf")

    service = VisualAssetService(vision_analyzer=BrokenVisionAnalyzer())
    result = service.process_document_assets(parsed=parsed, document_id=1, start_chunk_index=0)

    assert result.images_failed == 1
    assert result.images_analyzed == 0
    assert result.chunk_records == []


def test_vision_analysis_service_wraps_llm_failures():
    class BrokenStructuredLLM:
        def invoke(self, messages):
            raise RuntimeError("upstream failure")

    class BrokenLLM:
        def with_structured_output(self, schema):
            return BrokenStructuredLLM()

    service = VisionAnalysisService(llm=BrokenLLM())
    with pytest.raises(ExternalAPIException):
        service.analyze_image_bytes(b"not-a-real-image", image_format="png")


# ---------------------------------------------------------------------------
# API: document ingestion with visual processing
# ---------------------------------------------------------------------------


def test_document_upload_extracts_and_analyzes_embedded_image(isolated_client):
    pdf_bytes = make_pdf_with_image_bytes()

    upload = isolated_client.post(
        "/api/v1/documents/upload",
        files=[("files", ("img.pdf", pdf_bytes, "application/pdf"))],
    )
    assert upload.status_code == status.HTTP_200_OK
    result = upload.json()["results"][0]
    assert result["status"] == "COMPLETED"
    document_id = result["document_id"]
    assert result["chunk_count"] >= 2  # 1 text chunk + 1 image_caption chunk

    doc_detail = isolated_client.get(f"/api/v1/documents/{document_id}").json()
    assert doc_detail["image_count"] == 1

    assets_response = isolated_client.get(f"/api/v1/documents/{document_id}/assets")
    assert assets_response.status_code == status.HTTP_200_OK
    assets = assets_response.json()["assets"]
    assert len(assets) == 1
    assert assets[0]["asset_type"] == "image"
    assert assets[0]["caption"] == "A bar chart showing quarterly revenue growth."

    asset_id = assets[0]["id"]
    file_response = isolated_client.get(f"/api/v1/documents/{document_id}/assets/{asset_id}/file")
    assert file_response.status_code == status.HTTP_200_OK
    assert len(file_response.content) > 0


def test_document_upload_indexes_detected_table(isolated_client):
    pdf_bytes = make_pdf_with_table_bytes()

    upload = isolated_client.post(
        "/api/v1/documents/upload",
        files=[("files", ("table.pdf", pdf_bytes, "application/pdf"))],
    )
    document_id = upload.json()["results"][0]["document_id"]

    doc_detail = isolated_client.get(f"/api/v1/documents/{document_id}").json()
    assert doc_detail["table_count"] == 1

    assets = isolated_client.get(f"/api/v1/documents/{document_id}/assets").json()["assets"]
    assert any(a["asset_type"] == "table" for a in assets)


def test_document_assets_for_nonexistent_document_returns_404(isolated_client):
    response = isolated_client.get("/api/v1/documents/999999/assets")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_asset_file_for_nonexistent_asset_returns_404(isolated_client):
    pdf_bytes = make_pdf_bytes("Just text, no visuals.")
    upload = isolated_client.post(
        "/api/v1/documents/upload", files=[("files", ("plain.pdf", pdf_bytes, "application/pdf"))]
    )
    document_id = upload.json()["results"][0]["document_id"]

    response = isolated_client.get(f"/api/v1/documents/{document_id}/assets/999999/file")
    assert response.status_code == status.HTTP_404_NOT_FOUND


def test_visual_processing_failure_does_not_fail_document_ingestion(isolated_client):
    class BrokenVisionAnalyzer:
        def analyze_image_path(self, image_path):
            raise ExternalAPIException(message="Vision API unavailable")

    app.dependency_overrides[get_vision_analysis_service] = lambda: BrokenVisionAnalyzer()
    try:
        pdf_bytes = make_pdf_with_image_bytes()
        upload = isolated_client.post(
            "/api/v1/documents/upload",
            files=[("files", ("img.pdf", pdf_bytes, "application/pdf"))],
        )
        assert upload.status_code == status.HTTP_200_OK
        result = upload.json()["results"][0]
        assert result["status"] == "COMPLETED"
        assert result["chunk_count"] == 1  # only the text chunk; the image failed and was skipped

        document_id = result["document_id"]
        assets = isolated_client.get(f"/api/v1/documents/{document_id}/assets").json()["assets"]
        assert assets == []
    finally:
        app.dependency_overrides.pop(get_vision_analysis_service, None)


# ---------------------------------------------------------------------------
# API: standalone vision analysis
# ---------------------------------------------------------------------------


def test_vision_analyze_endpoint_returns_description_and_type(isolated_client):
    import io
    from PIL import Image

    image = Image.new("RGB", (50, 50), color=(10, 200, 10))
    buf = io.BytesIO()
    image.save(buf, format="PNG")

    response = isolated_client.post(
        "/api/v1/vision/analyze",
        files=[("file", ("test.png", buf.getvalue(), "image/png"))],
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["description"] == "A bar chart showing quarterly revenue growth."
    assert data["visual_type"] == "chart"


def test_vision_analyze_endpoint_rejects_non_image_content_type(isolated_client):
    response = isolated_client.post(
        "/api/v1/vision/analyze",
        files=[("file", ("notes.txt", b"just text", "text/plain"))],
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


# ---------------------------------------------------------------------------
# API: (re)processing visual assets for an already-ingested document
# ---------------------------------------------------------------------------


def test_reprocess_visuals_guards_against_duplicate_processing(isolated_client):
    pdf_bytes = make_pdf_with_image_bytes()
    upload = isolated_client.post(
        "/api/v1/documents/upload", files=[("files", ("img.pdf", pdf_bytes, "application/pdf"))]
    )
    document_id = upload.json()["results"][0]["document_id"]

    # Assets were already created automatically during ingestion.
    without_force = isolated_client.post(f"/api/v1/vision/documents/{document_id}/process")
    assert without_force.status_code == status.HTTP_400_BAD_REQUEST

    with_force = isolated_client.post(f"/api/v1/vision/documents/{document_id}/process?force=true")
    assert with_force.status_code == status.HTTP_200_OK
    data = with_force.json()
    assert data["images_analyzed"] == 1
    assert data["chunks_added"] == 1


def test_reprocess_visuals_for_nonexistent_document_returns_404(isolated_client):
    response = isolated_client.post("/api/v1/vision/documents/999999/process")
    assert response.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------------------
# Multi-modal retrieval
# ---------------------------------------------------------------------------


def test_search_retrieves_visual_content_without_explicit_filter(isolated_client):
    pdf_bytes = make_pdf_with_image_bytes(text="Quarterly revenue chart below.")
    isolated_client.post("/api/v1/documents/upload", files=[("files", ("img.pdf", pdf_bytes, "application/pdf"))])

    image_caption_query = "[chart] A bar chart showing quarterly revenue growth."
    response = isolated_client.post("/api/v1/search", json={"query": image_caption_query, "top_k": 5})

    assert response.status_code == status.HTTP_200_OK
    results = response.json()["results"]
    assert any(r["chunk_type"] == "image_caption" for r in results)
    top = results[0]
    assert top["chunk_type"] == "image_caption"
    assert top["similarity_score"] == pytest.approx(1.0, abs=1e-3)


def test_search_chunk_types_filter_restricts_to_visual_only(isolated_client):
    pdf_bytes = make_pdf_with_image_bytes(text="Quarterly revenue chart below.")
    isolated_client.post("/api/v1/documents/upload", files=[("files", ("img.pdf", pdf_bytes, "application/pdf"))])

    response = isolated_client.post(
        "/api/v1/search",
        json={"query": "revenue chart", "top_k": 10, "chunk_types": ["image_caption", "table"]},
    )
    assert response.status_code == status.HTTP_200_OK
    results = response.json()["results"]
    assert all(r["chunk_type"] in ("image_caption", "table") for r in results)


def test_search_chunk_types_filter_restricts_to_text_only(isolated_client):
    pdf_bytes = make_pdf_with_image_bytes(text="Quarterly revenue chart below.")
    isolated_client.post("/api/v1/documents/upload", files=[("files", ("img.pdf", pdf_bytes, "application/pdf"))])

    response = isolated_client.post(
        "/api/v1/search",
        json={"query": "Quarterly revenue chart below.", "top_k": 10, "chunk_types": ["text"]},
    )
    assert response.status_code == status.HTTP_200_OK
    results = response.json()["results"]
    assert len(results) >= 1
    assert all(r["chunk_type"] == "text" for r in results)


# ---------------------------------------------------------------------------
# LangGraph Vision Agent integration (Module 3 + Module 4)
# ---------------------------------------------------------------------------


def test_orchestrate_endpoint_invokes_vision_agent_and_preserves_visual_citation(isolated_orchestrator_client):
    pdf_bytes = make_pdf_with_image_bytes(text="Quarterly revenue chart below.")
    upload = isolated_orchestrator_client.post(
        "/api/v1/documents/upload", files=[("files", ("img.pdf", pdf_bytes, "application/pdf"))]
    )
    document_id = upload.json()["results"][0]["document_id"]

    response = isolated_orchestrator_client.post(
        "/api/v1/orchestrate",
        json={"query": "Describe the chart in this document.", "document_id": document_id},
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "vision" in data["agents_invoked"]
    assert "vision_agent" in [step["agent"] for step in data["execution_trace"]]

    vision_step = next(s for s in data["execution_trace"] if s["agent"] == "vision_agent")
    assert vision_step["status"] == "success"
