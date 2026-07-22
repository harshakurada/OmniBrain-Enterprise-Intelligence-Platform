import logging
from typing import List, Optional
from pydantic import BaseModel, Field
from backend.app.services.embedding_service import EmbeddingService
from backend.app.services.vector_store_service import VectorStoreBase

logger = logging.getLogger("omnibrain.search_service")


class SemanticSearchResult(BaseModel):
    """A single retrieved chunk returned by semantic search, ready for
    citation display (filename + page number + similarity score).
    """

    document_id: int
    filename: str
    page_number: int
    chunk_index: int
    content: str
    score: float
    chunk_type: str = Field("text", description="'text', 'image_caption', or 'table'")


class SemanticSearchService:
    """Executes semantic search queries: embeds the query text and
    retrieves the top-k most similar chunks from the active vector
    store backend (Qdrant or FAISS), enriched with citation metadata.
    """

    def __init__(self, embedder: EmbeddingService, vector_store: VectorStoreBase):
        self.embedder = embedder
        self.vector_store = vector_store

    def search(
        self,
        query: str,
        top_k: int = 5,
        document_id: Optional[int] = None,
        chunk_types: Optional[List[str]] = None,
    ) -> List[SemanticSearchResult]:
        """Returns the top-k chunks most semantically similar to `query`.

        By default this searches across every indexed modality (text, image
        captions, and tables) -- i.e. multi-modal retrieval is the default
        behavior. Pass `chunk_types` (e.g. `["image_caption", "table"]`) to
        restrict results to visual content only.
        """
        if not query or not query.strip():
            return []

        logger.info(
            f"Executing semantic search (top_k={top_k}, document_id={document_id}, "
            f"chunk_types={chunk_types}) for query: {query!r}"
        )

        query_vector = self.embedder.generate_embeddings([query])[0]
        raw_results = self.vector_store.search(
            query_vector, top_k=top_k, document_id=document_id, chunk_types=chunk_types
        )

        results = [
            SemanticSearchResult(
                document_id=r.payload.get("document_id"),
                filename=r.payload.get("filename", "unknown"),
                page_number=r.payload.get("page_number", -1),
                chunk_index=r.payload.get("chunk_index", -1),
                content=r.payload.get("content", ""),
                score=r.score,
                chunk_type=r.payload.get("chunk_type", "text"),
            )
            for r in raw_results
        ]

        logger.info(f"Semantic search returned {len(results)} result(s).")
        return results
