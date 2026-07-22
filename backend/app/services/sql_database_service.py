import logging
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session
from backend.app.config.settings import settings
from backend.app.core.exceptions import ValidationException

logger = logging.getLogger("omnibrain.sql_database")

_ALLOWED_START_KEYWORDS = {"select", "with"}
_FORBIDDEN_KEYWORDS = {
    "insert", "update", "delete", "drop", "alter", "truncate", "replace",
    "create", "attach", "detach", "pragma", "vacuum", "reindex", "grant",
    "revoke", "exec", "execute", "merge", "call",
}


class ColumnSchema(BaseModel):
    """Metadata for a single column, used for schema discovery and LLM prompting."""

    name: str
    type: str
    nullable: bool
    primary_key: bool


class TableSchema(BaseModel):
    """Metadata for a single table: its name and column definitions."""

    table_name: str
    columns: List[ColumnSchema]


class SQLExecutionResult(BaseModel):
    """Structured, citation-ready outcome of a safe SQL execution."""

    sql: str
    columns: List[str]
    rows: List[Dict[str, Any]]
    row_count: int
    truncated: bool

    def to_markdown(self, max_preview_rows: int = 20) -> str:
        """Renders the result as a compact Markdown table for LLM grounding."""
        if not self.rows:
            return "(no rows)"
        preview = self.rows[:max_preview_rows]
        header = "| " + " | ".join(self.columns) + " |"
        separator = "| " + " | ".join(["---"] * len(self.columns)) + " |"
        body = "\n".join("| " + " | ".join(str(row.get(c, "")) for c in self.columns) + " |" for row in preview)
        return "\n".join([header, separator, body])


def validate_readonly_sql(sql: str, max_rows: int) -> str:
    """Validates that `sql` is a single, read-only SELECT/CTE statement and
    caps its result size with a LIMIT clause. Raises `ValidationException`
    for anything else -- multiple statements, non-SELECT statements, or any
    statement containing a data-modifying/DDL keyword.

    This is enforced in addition to (not instead of) the connection-level
    `PRAGMA query_only` safety net applied to the read-only database session
    (see `backend.app.database.connection.readonly_engine`).
    """
    if not sql or not sql.strip():
        raise ValidationException("Generated SQL is empty.")

    statements = [s.strip() for s in sql.strip().split(";") if s.strip()]
    if len(statements) != 1:
        raise ValidationException("Only a single SQL statement is allowed.")
    statement = statements[0]

    first_word_match = re.match(r"^\s*(\w+)", statement)
    first_keyword = first_word_match.group(1).lower() if first_word_match else ""
    if first_keyword not in _ALLOWED_START_KEYWORDS:
        raise ValidationException(
            f"Only read-only SELECT statements are allowed; statement starts with '{first_keyword}'."
        )

    lowered = statement.lower()
    for keyword in _FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", lowered):
            raise ValidationException(f"SQL statement contains a disallowed keyword: '{keyword}'.")

    if not re.search(r"\blimit\b", lowered):
        statement = f"{statement} LIMIT {max_rows}"

    return statement


class SQLDatabaseService:
    """SQLAlchemy-based structured data service: schema discovery and safe,
    read-only SQL execution against the application's own database (the
    same SQLite instance backing Modules 1-4's document/chunk/asset
    metadata). Reads through a dedicated read-only session, so schema
    inspection and query execution automatically follow whatever
    connection that session is bound to (the production read-only engine,
    or a test's isolated transaction).
    """

    def __init__(self, readonly_db: Session, max_rows: Optional[int] = None):
        self.readonly_db = readonly_db
        self.max_rows = max_rows or settings.SQL_MAX_ROWS

    def list_tables(self) -> List[str]:
        """Returns every table name in the database."""
        inspector = inspect(self.readonly_db.get_bind())
        return inspector.get_table_names()

    def get_schema(self) -> List[TableSchema]:
        """Returns full table/column metadata for every table."""
        inspector = inspect(self.readonly_db.get_bind())
        tables: List[TableSchema] = []
        for table_name in inspector.get_table_names():
            pk_columns = set(inspector.get_pk_constraint(table_name).get("constrained_columns", []))
            columns = [
                ColumnSchema(
                    name=col["name"],
                    type=str(col["type"]),
                    nullable=bool(col.get("nullable", True)),
                    primary_key=col["name"] in pk_columns,
                )
                for col in inspector.get_columns(table_name)
            ]
            tables.append(TableSchema(table_name=table_name, columns=columns))
        return tables

    def get_schema_description(self) -> str:
        """Renders the schema as a compact text block for LLM prompting."""
        lines = []
        for table in self.get_schema():
            column_desc = ", ".join(f"{c.name} {c.type}" for c in table.columns)
            lines.append(f"- {table.table_name}({column_desc})")
        return "\n".join(lines)

    def execute_sql(self, sql: str) -> SQLExecutionResult:
        """Validates and safely executes a read-only SQL statement."""
        safe_sql = validate_readonly_sql(sql, max_rows=self.max_rows)
        logger.info(f"Executing read-only SQL: {safe_sql!r}")
        try:
            result = self.readonly_db.execute(text(safe_sql))
            columns = list(result.keys())
            rows = [dict(zip(columns, row)) for row in result.fetchall()]
        except ValidationException:
            raise
        except Exception as exc:
            logger.error(f"SQL execution failed: {exc}")
            raise ValidationException(f"SQL execution failed: {exc}")

        return SQLExecutionResult(
            sql=safe_sql,
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=len(rows) >= self.max_rows,
        )
