import pytest
from backend.app.services.vector_store_service import (
    FaissVectorStore,
    VectorRecord,
    generate_vector_id,
)


def test_faiss_upsert_and_search_returns_nearest_match(tmp_path):
    store = FaissVectorStore(vector_dim=4, storage_path=str(tmp_path / "faiss_index"))

    records = [
        VectorRecord(
            id=generate_vector_id(),
            vector=[1.0, 0.0, 0.0, 0.0],
            payload={"document_id": 1, "filename": "a.pdf", "page_number": 1, "chunk_index": 0, "content": "alpha"},
        ),
        VectorRecord(
            id=generate_vector_id(),
            vector=[0.0, 1.0, 0.0, 0.0],
            payload={"document_id": 2, "filename": "b.pdf", "page_number": 3, "chunk_index": 1, "content": "beta"},
        ),
    ]
    store.upsert(records)

    results = store.search(query_vector=[1.0, 0.0, 0.0, 0.0], top_k=1)

    assert len(results) == 1
    assert results[0].payload["content"] == "alpha"
    assert results[0].payload["filename"] == "a.pdf"
    assert results[0].score == pytest.approx(1.0, abs=1e-4)


def test_faiss_search_filters_by_document_id(tmp_path):
    store = FaissVectorStore(vector_dim=4, storage_path=str(tmp_path / "faiss_index"))

    store.upsert(
        [
            VectorRecord(
                id=generate_vector_id(),
                vector=[1.0, 0.0, 0.0, 0.0],
                payload={"document_id": 1, "filename": "a.pdf", "page_number": 1, "chunk_index": 0, "content": "doc-1-chunk"},
            ),
            VectorRecord(
                id=generate_vector_id(),
                vector=[0.99, 0.01, 0.0, 0.0],
                payload={"document_id": 2, "filename": "b.pdf", "page_number": 1, "chunk_index": 0, "content": "doc-2-chunk"},
            ),
        ]
    )

    results = store.search(query_vector=[1.0, 0.0, 0.0, 0.0], top_k=5, document_id=2)

    assert len(results) == 1
    assert results[0].payload["document_id"] == 2


def test_faiss_search_on_empty_index_returns_empty_list(tmp_path):
    store = FaissVectorStore(vector_dim=4, storage_path=str(tmp_path / "faiss_index"))

    assert store.search(query_vector=[1.0, 0.0, 0.0, 0.0], top_k=5) == []


def test_faiss_index_persists_across_instances(tmp_path):
    storage_path = str(tmp_path / "faiss_index")
    store = FaissVectorStore(vector_dim=4, storage_path=storage_path)
    store.upsert(
        [
            VectorRecord(
                id=generate_vector_id(),
                vector=[0.0, 0.0, 1.0, 0.0],
                payload={"document_id": 9, "filename": "persisted.pdf", "page_number": 1, "chunk_index": 0, "content": "persisted-chunk"},
            )
        ]
    )

    reloaded_store = FaissVectorStore(vector_dim=4, storage_path=storage_path)
    results = reloaded_store.search(query_vector=[0.0, 0.0, 1.0, 0.0], top_k=1)

    assert len(results) == 1
    assert results[0].payload["content"] == "persisted-chunk"
