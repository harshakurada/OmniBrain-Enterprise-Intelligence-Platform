import logging
from typing import List, Optional
from backend.app.services.search_service import SemanticSearchResult, SemanticSearchService

logger = logging.getLogger("omnibrain.agents.retrieval")


class RetrievalAgent:
    """Orchestrator-facing wrapper around Module 2's `SemanticSearchService`.

    Keeps the graph node code agent-shaped (a `run(...)` call) rather than
    coupling it directly to the retrieval service's own interface, so the
    graph wiring stays agnostic of how retrieval is actually implemented.
    """

    def __init__(self, search_service: SemanticSearchService):
        self.search_service = search_service

    def run(self, query: str, top_k: int, document_id: Optional[int] = None) -> List[SemanticSearchResult]:
        """Fetches the top-k most relevant document chunks for `query`."""
        logger.info(f"Retrieval agent executing semantic search for query: {query!r}")
        return self.search_service.search(query=query, top_k=top_k, document_id=document_id)
