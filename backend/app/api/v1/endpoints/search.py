import logging
from fastapi import APIRouter, Depends, status
from backend.app.api.deps import get_semantic_search_service
from backend.app.schemas.search import SearchQueryRequest, SearchResponse, SearchResultItem
from backend.app.services.search_service import SemanticSearchService

logger = logging.getLogger("omnibrain.api.search")
router = APIRouter()


@router.post(
    "/search",
    response_model=SearchResponse,
    status_code=status.HTTP_200_OK,
    summary="Run a semantic search query over ingested documents",
    response_description="Top-k most relevant chunks with similarity scores and citation metadata.",
)
def semantic_search(
    request: SearchQueryRequest,
    search_service: SemanticSearchService = Depends(get_semantic_search_service),
) -> SearchResponse:
    """Embeds the user's query and retrieves the top-k most semantically
    similar chunks across all ingested documents (or a single document,
    if `document_id` is provided), returning each match's similarity
    score, page number, and source filename for citation display.
    """
    results = search_service.search(
        query=request.query,
        top_k=request.top_k,
        document_id=request.document_id,
        chunk_types=request.chunk_types,
    )

    return SearchResponse(
        query=request.query,
        total_results=len(results),
        vector_backend=search_service.vector_store.backend_name,
        results=[
            SearchResultItem(
                document_id=r.document_id,
                filename=r.filename,
                page_number=r.page_number,
                chunk_index=r.chunk_index,
                content=r.content,
                similarity_score=r.score,
                chunk_type=r.chunk_type,
            )
            for r in results
        ],
    )
