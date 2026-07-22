import httpx
import pytest
from openai import APIConnectionError
from backend.app.core.exceptions import ExternalAPIException
from backend.app.services.embedding_service import EmbeddingService


class _FakeEmbeddingItem:
    def __init__(self, embedding):
        self.embedding = embedding


class _FakeEmbeddingResponse:
    def __init__(self, embeddings):
        self.data = [_FakeEmbeddingItem(e) for e in embeddings]


class _FakeEmbeddingsAPI:
    """Stand-in for `client.embeddings`, recording every call it receives."""

    def __init__(self, fail_times: int = 0, dim: int = 4):
        self.fail_times = fail_times
        self.dim = dim
        self.calls = []
        self._attempt = 0

    def create(self, model: str, input: list):
        self.calls.append(list(input))
        if self._attempt < self.fail_times:
            self._attempt += 1
            request = httpx.Request("POST", "https://api.openai.com/v1/embeddings")
            raise APIConnectionError(request=request)
        return _FakeEmbeddingResponse([[float(len(text))] * self.dim for text in input])


class _FakeOpenAIClient:
    def __init__(self, fail_times: int = 0, dim: int = 4):
        self.embeddings = _FakeEmbeddingsAPI(fail_times=fail_times, dim=dim)


def test_generate_embeddings_returns_vector_per_text():
    client = _FakeOpenAIClient()
    service = EmbeddingService(client=client, model="test-model", batch_size=10, max_retries=2)

    result = service.generate_embeddings(["hello", "world"])

    assert len(result) == 2
    assert all(len(vec) == 4 for vec in result)


def test_generate_embeddings_batches_requests():
    client = _FakeOpenAIClient()
    service = EmbeddingService(client=client, model="test-model", batch_size=2, max_retries=2)

    texts = ["a", "bb", "ccc", "dddd", "e"]
    result = service.generate_embeddings(texts)

    assert len(result) == 5
    # 5 texts with batch_size=2 -> 3 API calls (2, 2, 1)
    assert len(client.embeddings.calls) == 3
    assert [len(c) for c in client.embeddings.calls] == [2, 2, 1]


def test_generate_embeddings_retries_transient_failures():
    client = _FakeOpenAIClient(fail_times=1)
    service = EmbeddingService(client=client, model="test-model", batch_size=10, max_retries=3)

    result = service.generate_embeddings(["hello"])

    assert len(result) == 1
    # First call failed, second call (retry) succeeded.
    assert len(client.embeddings.calls) == 2


def test_generate_embeddings_raises_after_exhausting_retries():
    client = _FakeOpenAIClient(fail_times=5)
    service = EmbeddingService(client=client, model="test-model", batch_size=10, max_retries=2)

    with pytest.raises(ExternalAPIException):
        service.generate_embeddings(["hello"])

    assert len(client.embeddings.calls) == 2


def test_generate_embeddings_empty_input_returns_empty_list():
    client = _FakeOpenAIClient()
    service = EmbeddingService(client=client, model="test-model")

    assert service.generate_embeddings([]) == []
