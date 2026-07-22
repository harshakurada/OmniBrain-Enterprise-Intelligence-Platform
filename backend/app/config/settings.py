import os
from typing import List, Union
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General Settings
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    PROJECT_NAME: str = "OmniBrain – Agentic Multi-Modal RAG Orchestrator"

    # Backend Settings
    BACKEND_HOST: str = "0.0.0.0"
    BACKEND_PORT: int = 8000
    API_V1_PREFIX: str = "/api/v1"
    CORS_ORIGINS: Union[str, List[str]] = ["*"]

    # Database Settings
    DATABASE_URL: str = "sqlite:///./omnibrain.db"

    # Logging Settings
    LOG_LEVEL: str = "INFO"
    LOG_FILE_PATH: str = "logs/omnibrain.log"
    LOG_ROTATION: str = "10 MB"
    LOG_BACKUP_COUNT: int = 5

    # Storage Paths
    UPLOAD_DIR: str = "storage/uploads"
    ASSETS_DIR: str = "storage/assets"
    FAISS_STORAGE_PATH: str = "storage/faiss_index"

    # Processing Limits
    MAX_FILE_SIZE_MB: int = 50  # 50 MB limit
    DEFAULT_CHUNK_SIZE: int = 500
    DEFAULT_CHUNK_OVERLAP: int = 50

    # Embedding Pipeline Settings
    EMBEDDING_BATCH_SIZE: int = 64
    EMBEDDING_MAX_RETRIES: int = 3

    # Semantic Search Settings
    SEARCH_DEFAULT_TOP_K: int = 5

    # Vector Database Settings
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_COLLECTION_NAME: str = "omnibrain_vectors"
    VECTOR_DIMENSION: int = 1536  # Matches OpenAI text-embedding-3-small

    # OpenAI Settings
    OPENAI_API_KEY: str = "mock-key"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    OPENAI_MODEL: str = "gpt-4o"

    # Vision Analysis Settings (Module 4)
    VISION_MODEL: str = "gpt-4o"
    VISION_MIN_IMAGE_DIMENSION: int = 32  # skip decorative icons/spacers smaller than this (px)
    VISION_MAX_IMAGES_PER_DOCUMENT: int = 30  # cap Vision API calls per document ingestion

    # SQL Intelligence Settings (Module 5)
    SQL_MAX_ROWS: int = 200  # caps rows returned by any SQL Agent / raw SQL execution

    # Reliability Settings (Module 6)
    LLM_REQUEST_TIMEOUT_SECONDS: float = 30.0  # per-call timeout for any ChatOpenAI invocation
    LLM_MAX_RETRIES: int = 2  # transient-failure retries for ChatOpenAI invocations

    # Guardrail Settings (Module 6)
    GUARDRAILS_ENABLED: bool = True
    GUARDRAIL_MAX_INPUT_LENGTH: int = 4000  # characters; longer input is flagged as unsafe

    # Observability Settings (Module 6)
    METRICS_HISTORY_SIZE: int = 500  # capped in-memory history of API requests / agent executions
    EVALUATION_HISTORY_SIZE: int = 200  # capped in-memory history of evaluation reports

    # Observability Settings
    LANGFUSE_PUBLIC_KEY: str = "mock-key"
    LANGFUSE_SECRET_KEY: str = "mock-key"
    LANGFUSE_HOST: str = "https://cloud.langfuse.com"

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str) and not v.startswith("["):
            return [i.strip() for i in v.split(",")]
        elif isinstance(v, str) and v.startswith("["):
            import json
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
        return v  # type: ignore


# Instantiate settings singleton
settings = Settings()
