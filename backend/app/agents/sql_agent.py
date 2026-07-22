import logging
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field
from backend.app.core.exceptions import AppException
from backend.app.services.sql_database_service import SQLDatabaseService
from backend.app.services.text_to_sql_service import TextToSQLService

logger = logging.getLogger("omnibrain.agents.sql")


class SQLAgentResult(BaseModel):
    """Structured response contract returned by the SQL Agent."""

    status: str = Field(..., description="'success', 'no_results', 'unanswerable', or 'error'")
    message: str
    data: Optional[Dict[str, Any]] = None


class SQLAgent:
    """Text-to-SQL Agent: translates a natural-language question into a
    read-only SQL query over OmniBrain's own structured database (via
    `TextToSQLService`), validates and executes it safely (via
    `SQLDatabaseService`), and returns structured, citation-ready results.
    """

    def __init__(self, text_to_sql: TextToSQLService, database_service: SQLDatabaseService):
        self.text_to_sql = text_to_sql
        self.database_service = database_service

    def run(self, query: str, document_id: Optional[int] = None) -> SQLAgentResult:
        """Generates, validates, and executes SQL for `query`. Never raises
        -- every failure mode is captured in the returned `status`/`message`
        so the orchestrator graph always gets a well-formed result.
        """
        logger.info(f"SQL agent executing for query: {query!r}")
        schema_description = self.database_service.get_schema_description()

        try:
            generated = self.text_to_sql.generate_sql(question=query, schema_description=schema_description)
        except AppException as exc:
            return SQLAgentResult(status="error", message=f"Could not generate SQL: {exc.message}", data=None)

        if not generated.sql.strip():
            return SQLAgentResult(
                status="unanswerable",
                message=generated.explanation or "This question cannot be answered from the structured database.",
                data=None,
            )

        try:
            result = self.database_service.execute_sql(generated.sql)
        except AppException as exc:
            return SQLAgentResult(
                status="error",
                message=f"Generated SQL could not be executed safely: {exc.message}",
                data={"sql": generated.sql, "explanation": generated.explanation},
            )

        if result.row_count == 0:
            return SQLAgentResult(
                status="no_results",
                message="The query ran successfully but returned no rows.",
                data={
                    "sql": result.sql,
                    "columns": result.columns,
                    "rows": [],
                    "row_count": 0,
                    "explanation": generated.explanation,
                },
            )

        return SQLAgentResult(
            status="success",
            message=f"Query returned {result.row_count} row(s).",
            data={
                "sql": result.sql,
                "columns": result.columns,
                "rows": result.rows,
                "row_count": result.row_count,
                "truncated": result.truncated,
                "explanation": generated.explanation,
            },
        )
