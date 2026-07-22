import logging
import os
import pickle
import threading
import uuid
from abc import ABC, abstractmethod
from functools import lru_cache
from typing import Any, Dict, List, Optional
import numpy as np
from pydantic import BaseModel
from backend.app.config.settings import settings

logger = logging.getLogger("omnibrain.vector_store")


class VectorRecord(BaseModel):
    """A single vector plus its associated retrieval metadata (payload)."""

    id: str
    vector: List[float]
    payload: Dict[str, Any]


class VectorSearchResult(BaseModel):
    """A single scored match returned by a vector store search."""

    id: str
    score: float
    payload: Dict[str, Any]


class VectorStoreBase(ABC):
    """Abstract interface implemented by every vector store backend.

    Keeping ingestion/search code against this interface means the rest
    of the application never needs to know whether Qdrant or FAISS is
    actually serving requests.
    """

    @abstractmethod
    def upsert(self, records: List[VectorRecord]) -> None:
        ...

    @abstractmethod
    def search(
        self,
        query_vector: List[float],
        top_k: int,
        document_id: Optional[int] = None,
        chunk_types: Optional[List[str]] = None,
    ) -> List[VectorSearchResult]:
        ...

    @property
    @abstractmethod
    def backend_name(self) -> str:
        ...


class QdrantVectorStore(VectorStoreBase):
    """Vector store backend backed by a running Qdrant instance."""

    def __init__(self, host: str, port: int, collection_name: str, vector_dim: int):
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, VectorParams

        self._client = QdrantClient(host=host, port=port, timeout=5)
        self._collection_name = collection_name

        if not self._client.collection_exists(collection_name):
            logger.info(f"Creating Qdrant collection '{collection_name}' (dim={vector_dim}).")
            self._client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=vector_dim, distance=Distance.COSINE),
            )

    @property
    def backend_name(self) -> str:
        return "qdrant"

    def upsert(self, records: List[VectorRecord]) -> None:
        from qdrant_client.models import PointStruct

        if not records:
            return
        points = [PointStruct(id=r.id, vector=r.vector, payload=r.payload) for r in records]
        self._client.upsert(collection_name=self._collection_name, points=points)
        logger.info(f"Upserted {len(points)} vector(s) into Qdrant collection '{self._collection_name}'.")

    def search(
        self,
        query_vector: List[float],
        top_k: int,
        document_id: Optional[int] = None,
        chunk_types: Optional[List[str]] = None,
    ) -> List[VectorSearchResult]:
        from qdrant_client.models import FieldCondition, Filter, MatchAny, MatchValue

        must_conditions = []
        if document_id is not None:
            must_conditions.append(FieldCondition(key="document_id", match=MatchValue(value=document_id)))
        if chunk_types:
            must_conditions.append(FieldCondition(key="chunk_type", match=MatchAny(any=chunk_types)))
        query_filter = Filter(must=must_conditions) if must_conditions else None

        response = self._client.query_points(
            collection_name=self._collection_name,
            query=query_vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        return [
            VectorSearchResult(id=str(point.id), score=point.score, payload=point.payload or {})
            for point in response.points
        ]


class FaissVectorStore(VectorStoreBase):
    """Local, on-disk vector store backend used when Qdrant is unavailable.

    FAISS only stores raw vectors, so ids and payloads are tracked
    in parallel Python lists that are persisted alongside the index
    (pickled) so the store survives process restarts.
    """

    def __init__(self, vector_dim: int, storage_path: str):
        import faiss

        self._faiss = faiss
        self._vector_dim = vector_dim
        self._storage_path = storage_path
        self._index_file = os.path.join(storage_path, "index.faiss")
        self._meta_file = os.path.join(storage_path, "metadata.pkl")
        self._lock = threading.Lock()

        os.makedirs(storage_path, exist_ok=True)

        self._ids: List[str] = []
        self._payloads: List[Dict[str, Any]] = []
        self._index = faiss.IndexFlatIP(vector_dim)

        self._load()

    @property
    def backend_name(self) -> str:
        return "faiss"

    def _load(self) -> None:
        if os.path.exists(self._index_file) and os.path.exists(self._meta_file):
            try:
                self._index = self._faiss.read_index(self._index_file)
                with open(self._meta_file, "rb") as f:
                    meta = pickle.load(f)
                    self._ids = meta["ids"]
                    self._payloads = meta["payloads"]
                logger.info(f"Loaded FAISS index with {self._index.ntotal} vector(s) from disk.")
            except Exception as e:
                logger.warning(f"Failed to load existing FAISS index, starting fresh: {e}")
                self._index = self._faiss.IndexFlatIP(self._vector_dim)
                self._ids = []
                self._payloads = []

    def _persist(self) -> None:
        self._faiss.write_index(self._index, self._index_file)
        with open(self._meta_file, "wb") as f:
            pickle.dump({"ids": self._ids, "payloads": self._payloads}, f)

    @staticmethod
    def _normalize(vectors: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0] = 1e-12
        return vectors / norms

    def upsert(self, records: List[VectorRecord]) -> None:
        if not records:
            return
        with self._lock:
            matrix = np.array([r.vector for r in records], dtype="float32")
            matrix = self._normalize(matrix)
            self._index.add(matrix)
            self._ids.extend(r.id for r in records)
            self._payloads.extend(r.payload for r in records)
            self._persist()
        logger.info(f"Upserted {len(records)} vector(s) into local FAISS index.")

    def search(
        self,
        query_vector: List[float],
        top_k: int,
        document_id: Optional[int] = None,
        chunk_types: Optional[List[str]] = None,
    ) -> List[VectorSearchResult]:
        with self._lock:
            if self._index.ntotal == 0:
                return []

            query = np.array([query_vector], dtype="float32")
            query = self._normalize(query)

            # Over-fetch when filtering by document_id/chunk_type since FAISS has
            # no native metadata filter; we filter the candidates afterwards.
            has_filter = document_id is not None or bool(chunk_types)
            fetch_k = self._index.ntotal if has_filter else min(top_k, self._index.ntotal)
            scores, indices = self._index.search(query, fetch_k)

            results: List[VectorSearchResult] = []
            for score, idx in zip(scores[0], indices[0]):
                if idx < 0 or idx >= len(self._ids):
                    continue
                payload = self._payloads[idx]
                if document_id is not None and payload.get("document_id") != document_id:
                    continue
                if chunk_types and payload.get("chunk_type") not in chunk_types:
                    continue
                results.append(
                    VectorSearchResult(id=self._ids[idx], score=float(score), payload=payload)
                )
                if len(results) >= top_k:
                    break

            return results


@lru_cache(maxsize=1)
def get_vector_store() -> VectorStoreBase:
    """Factory returning a process-wide singleton vector store.

    Attempts to connect to Qdrant first; if the server is unreachable
    or misconfigured, transparently falls back to a local FAISS index
    so semantic search keeps working without any external dependency.
    """
    try:
        store = QdrantVectorStore(
            host=settings.QDRANT_HOST,
            port=settings.QDRANT_PORT,
            collection_name=settings.QDRANT_COLLECTION_NAME,
            vector_dim=settings.VECTOR_DIMENSION,
        )
        logger.info(f"Connected to Qdrant at {settings.QDRANT_HOST}:{settings.QDRANT_PORT}.")
        return store
    except Exception as e:
        logger.warning(
            f"Qdrant unavailable ({e}). Falling back to local FAISS vector store at "
            f"'{settings.FAISS_STORAGE_PATH}'."
        )
        return FaissVectorStore(
            vector_dim=settings.VECTOR_DIMENSION,
            storage_path=settings.FAISS_STORAGE_PATH,
        )


def generate_vector_id() -> str:
    """Generates a unique vector id compatible with both Qdrant and FAISS."""
    return str(uuid.uuid4())
