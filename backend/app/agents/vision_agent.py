import logging
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from backend.app.services.search_service import SemanticSearchService

logger = logging.getLogger("omnibrain.agents.vision")

VISUAL_CHUNK_TYPES = ["image_caption", "table"]


class VisionAgentResult(BaseModel):
    """Structured response contract returned by the Vision Agent."""

    status: str = Field(..., description="'success' if visual content was found, else 'no_visual_content'")
    message: str
    data: Optional[Dict[str, Any]] = None


class VisionAgent:
    """Retrieves visual content (image descriptions and structured tables)
    relevant to the user's query using Module 4's multi-modal search index.

    Images and tables are analyzed once at ingestion time (see
    `VisualAssetService`) and embedded alongside text chunks, so this agent
    is a thin, semantic-search-backed wrapper -- consistent in shape with
    `RetrievalAgent` -- restricted to the visual (`image_caption`, `table`)
    modalities via `SemanticSearchService`'s `chunk_types` filter.
    """

    def __init__(self, search_service: SemanticSearchService):
        self.search_service = search_service

    def run(self, query: str, document_id: Optional[int] = None, top_k: int = 5) -> VisionAgentResult:
        """Searches indexed visual content for `query` and returns matches
        shaped identically to `SemanticSearchResult`, ready to be folded
        into the Response Synthesizer's citation-preserving context.
        """
        logger.info(f"Vision agent executing visual search for query: {query!r} (document_id={document_id})")
        results = self.search_service.search(
            query=query, top_k=top_k, document_id=document_id, chunk_types=VISUAL_CHUNK_TYPES
        )

        if not results:
            return VisionAgentResult(
                status="no_visual_content",
                message="No relevant visual content (images, charts, diagrams, or tables) was found for this query.",
                data=None,
            )

        return VisionAgentResult(
            status="success",
            message=f"Found {len(results)} relevant visual element(s).",
            data={"results": [r.model_dump() for r in results]},
        )
