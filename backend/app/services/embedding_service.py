import logging
from typing import List, Optional
from openai import (
    OpenAI,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
    before_sleep_log,
)
from backend.app.config.settings import settings
from backend.app.core.exceptions import ExternalAPIException

logger = logging.getLogger("omnibrain.embedding")

# Only retry genuinely transient failures. Permanent client errors (bad API
# key, malformed request, etc.) subclass APIError too, but retrying those
# just delays the inevitable failure -- so they are deliberately excluded.
RETRYABLE_EXCEPTIONS = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


class EmbeddingService:
    """Generates text embeddings via the OpenAI Embeddings API.

    Supports batch processing and automatically retries transient failures
    (rate limits, timeouts, connection errors) with exponential backoff.
    Any batch that exhausts its retries is logged and raised as an
    `ExternalAPIException` so the caller can mark the enclosing document
    as failed without crashing the whole ingestion pipeline.
    """

    def __init__(
        self,
        client: Optional[OpenAI] = None,
        model: Optional[str] = None,
        batch_size: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        self.client = client or OpenAI(api_key=settings.OPENAI_API_KEY)
        self.model = model or settings.EMBEDDING_MODEL
        self.batch_size = batch_size or settings.EMBEDDING_BATCH_SIZE
        self.max_retries = max_retries or settings.EMBEDDING_MAX_RETRIES

    def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Generates embeddings for a list of texts, batching requests and
        preserving input order in the returned list.
        """
        if not texts:
            return []

        embeddings: List[List[float]] = []
        for start in range(0, len(texts), self.batch_size):
            batch = texts[start : start + self.batch_size]
            logger.info(
                f"Embedding batch {start // self.batch_size + 1} "
                f"({len(batch)} item(s), model={self.model})."
            )
            batch_embeddings = self._embed_batch_with_retry(batch)
            embeddings.extend(batch_embeddings)

        return embeddings

    def _embed_batch_with_retry(self, batch: List[str]) -> List[List[float]]:
        retrying_call = retry(
            reraise=True,
            stop=stop_after_attempt(self.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(RETRYABLE_EXCEPTIONS),
            before_sleep=before_sleep_log(logger, logging.WARNING),
        )(self._call_openai_embeddings)

        try:
            return retrying_call(batch)
        except RETRYABLE_EXCEPTIONS as exc:
            logger.error(f"Embedding batch failed after {self.max_retries} attempt(s): {exc}")
            raise ExternalAPIException(
                message="Failed to generate embeddings via OpenAI after multiple retries.",
                details=str(exc),
            )
        except Exception as exc:
            logger.error(f"Unexpected error while generating embeddings: {exc}")
            raise ExternalAPIException(
                message="Unexpected error while generating embeddings.",
                details=str(exc),
            )

    def _call_openai_embeddings(self, batch: List[str]) -> List[List[float]]:
        response = self.client.embeddings.create(model=self.model, input=batch)
        return [item.embedding for item in response.data]
