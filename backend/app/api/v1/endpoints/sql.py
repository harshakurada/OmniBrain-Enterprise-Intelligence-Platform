import logging
from fastapi import APIRouter, Depends, status
from backend.app.agents.sql_agent import SQLAgent
from backend.app.api.deps import get_sql_agent, get_sql_database_service
from backend.app.schemas.sql import (
    ColumnInfo,
    SQLExecuteRequest,
    SQLQueryRequest,
    SQLResultResponse,
    SchemaResponse,
    TableListResponse,
    TableSchemaInfo,
)
from backend.app.services.sql_database_service import SQLDatabaseService

logger = logging.getLogger("omnibrain.api.sql")
router = APIRouter()


@router.get(
    "/sql/tables",
    response_model=TableListResponse,
    status_code=status.HTTP_200_OK,
    summary="List structured database tables",
)
def list_tables(db_service: SQLDatabaseService = Depends(get_sql_database_service)) -> TableListResponse:
    """Returns every table available to the SQL Agent (schema discovery)."""
    return TableListResponse(tables=db_service.list_tables())


@router.get(
    "/sql/schema",
    response_model=SchemaResponse,
    status_code=status.HTTP_200_OK,
    summary="Inspect the structured database schema",
)
def get_schema(db_service: SQLDatabaseService = Depends(get_sql_database_service)) -> SchemaResponse:
    """Returns full table/column metadata, the same schema description used
    to ground the Text-to-SQL generator's prompts.
    """
    tables = db_service.get_schema()
    return SchemaResponse(
        tables=[
            TableSchemaInfo(table_name=t.table_name, columns=[ColumnInfo(**c.model_dump()) for c in t.columns])
            for t in tables
        ]
    )


@router.post(
    "/sql/execute",
    response_model=SQLResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute a raw read-only SQL statement",
)
def execute_sql(
    request: SQLExecuteRequest, db_service: SQLDatabaseService = Depends(get_sql_database_service)
) -> SQLResultResponse:
    """Validates and safely executes caller-supplied SQL. Destructive or
    multi-statement input is rejected with a 400 before anything runs.
    """
    result = db_service.execute_sql(request.sql)
    return SQLResultResponse(
        status="success",
        message=f"Query returned {result.row_count} row(s).",
        sql=result.sql,
        columns=result.columns,
        rows=result.rows,
        row_count=result.row_count,
        truncated=result.truncated,
    )


@router.post(
    "/sql/query",
    response_model=SQLResultResponse,
    status_code=status.HTTP_200_OK,
    summary="Answer a natural-language question via Text-to-SQL",
)
def query_natural_language(
    request: SQLQueryRequest, sql_agent: SQLAgent = Depends(get_sql_agent)
) -> SQLResultResponse:
    """Runs the full SQL Agent pipeline: generate SQL from `question`,
    validate it, execute it safely, and return structured results.
    """
    result = sql_agent.run(query=request.question)
    data = result.data or {}
    return SQLResultResponse(
        status=result.status,
        message=result.message,
        sql=data.get("sql"),
        explanation=data.get("explanation"),
        columns=data.get("columns", []),
        rows=data.get("rows", []),
        row_count=data.get("row_count", 0),
        truncated=data.get("truncated", False),
    )
