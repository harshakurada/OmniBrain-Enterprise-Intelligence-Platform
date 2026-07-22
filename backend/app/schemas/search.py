from typing import List, Optional
from pydantic import BaseModel, Field


class SearchQueryRequest(BaseModel):
    """Request payload for the semantic search endpoint."""

    query: str = Field(..., min_length=1, description="Natural language search query")
    top_k: int = Field(5, ge=1, le=50, description="Number of top matching chunks to return")
    document_id: Optional[int] = Field(None, description="Restrict search to a single document, if provided")
    chunk_types: Optional[List[str]] = Field(
        None,
        description="Restrict results to specific modalities, e.g. ['image_caption','table'] for visual-only "
        "search. Omit to search text and visual content together (multi-modal retrieval).",
    )


class SearchResultItem(BaseModel):
    """A single retrieved chunk with similarity score and citation metadata."""

    document_id: int
    filename: str
    page_number: int
    chunk_index: int
    content: str
    similarity_score: float = Field(..., description="Cosine similarity score, higher is more relevant")
    chunk_type: str = Field("text", description="'text', 'image_caption', or 'table'")


class SearchResponse(BaseModel):
    query: str
    total_results: int
    vector_backend: str = Field(..., description="Vector store backend that served the query: 'qdrant' or 'faiss'")
    results: List[SearchResultItem]
