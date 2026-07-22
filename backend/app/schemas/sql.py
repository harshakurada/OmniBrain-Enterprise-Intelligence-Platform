from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ColumnInfo(BaseModel):
    """Metadata for a single database column."""

    name: str
    type: str
    nullable: bool
    primary_key: bool


class TableSchemaInfo(BaseModel):
    """Metadata for a single database table: its name and columns."""

    table_name: str
    columns: List[ColumnInfo]


class TableListResponse(BaseModel):
    """Response for the table-listing endpoint."""

    tables: List[str]


class SchemaResponse(BaseModel):
    """Response for the schema-inspection endpoint."""

    tables: List[TableSchemaInfo]


class SQLExecuteRequest(BaseModel):
    """Request payload to execute a raw, caller-supplied SQL statement."""

    sql: str = Field(..., min_length=1, description="A single read-only SQL SELECT statement")


class SQLQueryRequest(BaseModel):
    """Request payload for a natural-language Text-to-SQL question."""

    question: str = Field(..., min_length=1, description="Natural-language question about OmniBrain's structured data")


class SQLResultResponse(BaseModel):
    """Structured result of a SQL Agent run or raw SQL execution."""

    status: str = Field(..., description="'success', 'no_results', 'unanswerable', or 'error'")
    message: str
    sql: Optional[str] = None
    explanation: Optional[str] = None
    columns: List[str] = Field(default_factory=list)
    rows: List[Dict[str, Any]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
