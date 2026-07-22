"""Shared test-only helpers for Module 2 ingestion/search tests.

Not a test module itself (hence the leading underscore, which keeps
pytest's `test_*.py` collection rule from picking it up). Fixtures
defined here are imported directly into test modules that need
end-to-end API coverage without depending on a real OpenAI key or a
running Qdrant instance.
"""
import hashlib
import io
from typing import Any, List, Optional
import fitz
import pytest
from PIL import Image
from backend.app.agents.supervisor_agent import KeywordIntentClassifier, SupervisorAgent
from backend.app.agents.synthesizer_agent import ResponseSynthesizer
from backend.app.api.deps import (
    get_active_vector_store,
    get_embedding_service,
    get_response_synthesizer,
    get_supervisor_agent,
    get_text_to_sql_service,
    get_vision_analysis_service,
)
from backend.app.config.settings import settings
from backend.app.main import app
from backend.app.services.text_to_sql_service import GeneratedSQL
from backend.app.services.vector_store_service import FaissVectorStore
from backend.app.services.vision_analysis_service import VisionDescription

FAKE_VECTOR_DIM = 8


class FakeEmbeddingService:
    """Deterministic, offline stand-in for `EmbeddingService`.

    Produces a stable pseudo-vector per exact input string (via an MD5
    digest), so re-embedding identical text always yields an identical
    vector -- enough to exercise the ingestion/search plumbing without
    calling the real OpenAI API.
    """

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        return [self._vector_for(text) for text in texts]

    @staticmethod
    def _vector_for(text: str, dim: int = FAKE_VECTOR_DIM) -> List[float]:
        digest = hashlib.md5(text.encode("utf-8")).digest()
        return [(digest[i % len(digest)] - 128) / 128.0 for i in range(dim)]


def make_pdf_bytes(text: str, pages: int = 1) -> bytes:
    """Builds an in-memory single/multi-page PDF containing `text` on each page."""
    doc = fitz.open()
    for _ in range(pages):
        page = doc.new_page()
        page.insert_text((72, 72), text)
    data = doc.tobytes()
    doc.close()
    return data


def make_pdf_with_image_bytes(
    text: str = "Quarterly revenue chart below.", image_size: tuple = (100, 80), color: tuple = (200, 30, 30)
) -> bytes:
    """Builds a single-page PDF containing both text and a real embedded
    raster image, so Module 2's PyMuPDF-based image extraction (and
    Module 4's Vision Agent analysis on top of it) has real content to find.
    """
    image = Image.new("RGB", image_size, color=color)
    buf = io.BytesIO()
    image.save(buf, format="PNG")

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    rect = fitz.Rect(72, 100, 72 + image_size[0], 100 + image_size[1])
    page.insert_image(rect, stream=buf.getvalue())
    data = doc.tobytes()
    doc.close()
    return data


def make_pdf_with_table_bytes(text: str = "Revenue table below.") -> bytes:
    """Builds a single-page PDF containing text plus a real ruled grid table,
    detectable by Module 2's pdfplumber-based table extraction.
    """
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)

    x0, y0 = 72, 100
    col_w, row_h = 60, 20
    cols, rows = 3, 2
    for r in range(rows + 1):
        page.draw_line((x0, y0 + r * row_h), (x0 + cols * col_w, y0 + r * row_h))
    for c in range(cols + 1):
        page.draw_line((x0 + c * col_w, y0), (x0 + c * col_w, y0 + rows * row_h))

    cell_text = [["Segment", "Q1", "Q2"], ["Cloud", "10", "12"]]
    for r in range(rows):
        for c in range(cols):
            page.insert_text((x0 + c * col_w + 5, y0 + r * row_h + 14), cell_text[r][c], fontsize=8)

    data = doc.tobytes()
    doc.close()
    return data


class FakeVisionAnalysisService:
    """Deterministic, offline stand-in for `VisionAnalysisService` -- returns
    a canned `VisionDescription` without ever calling the OpenAI Vision API.
    """

    def __init__(self, description: str = "A bar chart showing quarterly revenue growth.", visual_type: str = "chart"):
        self.description = description
        self.visual_type = visual_type

    def analyze_image_bytes(self, image_bytes: bytes, image_format: str = "png") -> VisionDescription:
        return VisionDescription(description=self.description, visual_type=self.visual_type)

    def analyze_image_path(self, image_path: str) -> VisionDescription:
        return VisionDescription(description=self.description, visual_type=self.visual_type)


@pytest.fixture
def isolated_client(client, tmp_path, monkeypatch):
    """A TestClient with the embedding service, vector store, and vision
    analyzer swapped for offline, isolated fakes -- no network calls, no
    shared on-disk FAISS index between test runs -- and uploaded files /
    extracted assets redirected to a temp directory so tests never write
    into the real `storage/uploads` or `storage/assets`.
    """
    fake_store = FaissVectorStore(vector_dim=FAKE_VECTOR_DIM, storage_path=str(tmp_path / "faiss_index"))
    fake_embedder = FakeEmbeddingService()
    fake_vision = FakeVisionAnalysisService()

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "ASSETS_DIR", str(tmp_path / "assets"))
    app.dependency_overrides[get_embedding_service] = lambda: fake_embedder
    app.dependency_overrides[get_active_vector_store] = lambda: fake_store
    app.dependency_overrides[get_vision_analysis_service] = lambda: fake_vision

    yield client


class FakeChatResult:
    """Deterministic, offline stand-in for a LangChain `AIMessage` -- just
    needs a `.content` attribute for `ResponseSynthesizer` to read.
    """

    def __init__(self, content: str):
        self.content = content


class FakeSynthesizerLLM:
    """Deterministic, offline stand-in for the `ChatOpenAI` model used by
    `ResponseSynthesizer`, so tests never make a real OpenAI call.
    """

    def invoke(self, messages: List[Any]) -> FakeChatResult:
        return FakeChatResult(content="Fake grounded answer based on retrieved context.")


class FakeTextToSQLService:
    """Deterministic, offline stand-in for `TextToSQLService` -- returns a
    canned `GeneratedSQL` without ever calling the OpenAI API.
    """

    def __init__(
        self,
        sql: str = "SELECT COUNT(*) AS total FROM documents",
        explanation: str = "Counts all ingested documents.",
    ):
        self.sql = sql
        self.explanation = explanation

    def generate_sql(self, question: str, schema_description: str) -> GeneratedSQL:
        return GeneratedSQL(sql=self.sql, explanation=self.explanation)


@pytest.fixture
def isolated_orchestrator_client(isolated_client):
    """Extends `isolated_client` with Module 3's Supervisor, Response
    Synthesizer, and Module 5's Text-to-SQL generator swapped for offline
    fakes (keyword-based routing, canned LLM/SQL output) so orchestration
    tests never require network access or a real OpenAI API key. The SQL
    Agent's database layer is left real (it just reflects/queries the
    test database through the already-overridden `get_readonly_db`).
    """
    app.dependency_overrides[get_supervisor_agent] = lambda: SupervisorAgent(classifier=KeywordIntentClassifier())
    app.dependency_overrides[get_response_synthesizer] = lambda: ResponseSynthesizer(llm=FakeSynthesizerLLM())
    app.dependency_overrides[get_text_to_sql_service] = lambda: FakeTextToSQLService()

    yield isolated_client
