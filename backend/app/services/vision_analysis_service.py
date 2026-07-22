import base64
import logging
import os
from typing import Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from backend.app.config.settings import settings
from backend.app.core.exceptions import ExternalAPIException

logger = logging.getLogger("omnibrain.vision_analysis")

VISUAL_TYPES = ["chart", "graph", "table", "diagram", "screenshot", "photo", "other"]

_ANALYSIS_SYSTEM_PROMPT = (
    "You are a document vision analyst. Given an image extracted from a PDF page, write a "
    "concise, factual 1-3 sentence description of what it shows -- do not speculate beyond "
    "what is visibly present. Then classify it as exactly one of: "
    "chart, graph, table, diagram, screenshot, photo, other."
)


class VisionDescription(BaseModel):
    """Structured output produced by the Vision Analysis service for a single image."""

    description: str = Field(..., description="Concise factual description of the image")
    visual_type: str = Field(..., description="One of: chart, graph, table, diagram, screenshot, photo, other")


class VisionAnalysisService:
    """Generates structured, citation-ready descriptions of extracted document
    images using an OpenAI vision-capable chat model (e.g. GPT-4o).

    Mirrors `EmbeddingService`'s DI shape: an optional pre-built client can be
    injected (for tests/fakes), otherwise a default `ChatOpenAI` is built from
    the shared application settings.
    """

    def __init__(self, llm: Optional[BaseChatModel] = None, model: Optional[str] = None):
        base_llm = llm or ChatOpenAI(
            model=model or settings.VISION_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0,
            timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS, max_retries=settings.LLM_MAX_RETRIES,
        )
        self._structured_llm = base_llm.with_structured_output(VisionDescription)

    def analyze_image_bytes(self, image_bytes: bytes, image_format: str = "png") -> VisionDescription:
        """Analyzes raw image bytes and returns a structured description."""
        b64_data = base64.b64encode(image_bytes).decode("utf-8")
        data_url = f"data:image/{image_format};base64,{b64_data}"
        message = HumanMessage(
            content=[
                {"type": "text", "text": _ANALYSIS_SYSTEM_PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]
        )
        try:
            return self._structured_llm.invoke([message])
        except Exception as exc:
            logger.error(f"Vision analysis failed: {exc}")
            raise ExternalAPIException(
                message="Failed to analyze image via the OpenAI Vision API.", details=str(exc)
            )

    def analyze_image_path(self, image_path: str) -> VisionDescription:
        """Analyzes an image already saved to disk (e.g. by `PDFParserService`)."""
        if not os.path.exists(image_path):
            raise ExternalAPIException(message=f"Image file not found for analysis: {image_path}")

        image_format = os.path.splitext(image_path)[1].lstrip(".").lower() or "png"
        with open(image_path, "rb") as f:
            image_bytes = f.read()
        return self.analyze_image_bytes(image_bytes, image_format=image_format)
