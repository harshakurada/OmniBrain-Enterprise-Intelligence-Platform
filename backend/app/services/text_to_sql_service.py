import logging
from typing import Optional
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field
from backend.app.config.settings import settings
from backend.app.core.exceptions import ExternalAPIException

logger = logging.getLogger("omnibrain.text_to_sql")

_SYSTEM_PROMPT_TEMPLATE = (
    "You are a Text-to-SQL assistant for the OmniBrain application's own SQLite database "
    "(document ingestion metadata -- not the documents' textual content). Given the schema "
    "below and a natural-language question, generate a single, valid, read-only SQL SELECT "
    "statement (SQLite dialect) that answers it.\n\n"
    "Rules:\n"
    "- Only use SELECT or WITH (CTE) statements. Never INSERT, UPDATE, DELETE, DROP, ALTER, "
    "or any other data-modifying or schema-altering statement.\n"
    "- Only reference tables and columns that exist in the schema below.\n"
    "- If the question cannot be answered with a read-only query over this schema, leave "
    "`sql` empty and explain why in `explanation`.\n\n"
    "Schema:\n{schema}"
)


class GeneratedSQL(BaseModel):
    """Structured output produced by the Text-to-SQL generator."""

    sql: str = Field(..., description="A single read-only SQL SELECT statement, or empty if not answerable")
    explanation: str = Field(
        ..., description="Brief explanation of what the query does, or why it can't be generated"
    )


class TextToSQLService:
    """Translates natural-language questions into read-only SQL statements
    using an OpenAI chat model, grounded in the application's actual
    database schema (see `SQLDatabaseService.get_schema_description`).
    """

    def __init__(self, llm: Optional[BaseChatModel] = None):
        base_llm = llm or ChatOpenAI(
            model=settings.OPENAI_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0,
            timeout=settings.LLM_REQUEST_TIMEOUT_SECONDS, max_retries=settings.LLM_MAX_RETRIES,
        )
        self._structured_llm = base_llm.with_structured_output(GeneratedSQL)

    def generate_sql(self, question: str, schema_description: str) -> GeneratedSQL:
        """Generates a `GeneratedSQL` (sql + explanation) for `question`."""
        prompt = _SYSTEM_PROMPT_TEMPLATE.format(schema=schema_description)
        try:
            return self._structured_llm.invoke(
                [SystemMessage(content=prompt), HumanMessage(content=question)]
            )
        except Exception as exc:
            logger.error(f"SQL generation failed: {exc}")
            raise ExternalAPIException(message="Failed to generate SQL via OpenAI.", details=str(exc))
