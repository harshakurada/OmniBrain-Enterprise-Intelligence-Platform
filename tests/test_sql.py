import pytest
from fastapi import status
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.agents.sql_agent import SQLAgent, SQLAgentResult
from backend.app.core.exceptions import AppException, ExternalAPIException, ValidationException
from backend.app.database.connection import _enable_readonly_mode
from backend.app.database.models import Base, DocumentModel
from backend.app.services.sql_database_service import SQLDatabaseService, validate_readonly_sql
from backend.app.services.text_to_sql_service import GeneratedSQL, TextToSQLService
from tests._test_helpers import (  # noqa: F401
    FakeTextToSQLService,
    isolated_client,
    isolated_orchestrator_client,
    make_pdf_bytes,
)

# ---------------------------------------------------------------------------
# SQL validation / safe execution
# ---------------------------------------------------------------------------


def test_validate_readonly_sql_accepts_select_and_adds_limit():
    result = validate_readonly_sql("SELECT * FROM documents", max_rows=50)
    assert result.strip().upper().startswith("SELECT")
    assert "LIMIT 50" in result


def test_validate_readonly_sql_preserves_existing_limit():
    result = validate_readonly_sql("SELECT * FROM documents LIMIT 10", max_rows=50)
    assert result.count("LIMIT") == 1
    assert "LIMIT 10" in result


def test_validate_readonly_sql_accepts_cte():
    result = validate_readonly_sql("WITH t AS (SELECT * FROM documents) SELECT * FROM t", max_rows=50)
    assert "LIMIT 50" in result


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO documents (filename) VALUES ('x')",
        "UPDATE documents SET filename='x'",
        "DELETE FROM documents",
        "DROP TABLE documents",
        "ALTER TABLE documents ADD COLUMN x TEXT",
        "TRUNCATE TABLE documents",
        "CREATE TABLE evil (id INTEGER)",
        "PRAGMA writable_schema = 1",
        "ATTACH DATABASE 'x' AS y",
    ],
)
def test_validate_readonly_sql_rejects_destructive_statements(sql):
    with pytest.raises(ValidationException):
        validate_readonly_sql(sql, max_rows=50)


def test_validate_readonly_sql_rejects_multiple_statements():
    with pytest.raises(ValidationException):
        validate_readonly_sql("SELECT 1; DROP TABLE documents;", max_rows=50)


def test_validate_readonly_sql_rejects_empty_sql():
    with pytest.raises(ValidationException):
        validate_readonly_sql("", max_rows=50)


def test_validate_readonly_sql_does_not_false_positive_on_column_names():
    """Regression guard: keyword matching must use word boundaries so real
    column names like 'created_at'/'updated_at' don't trip the 'create'/
    'update' denylist (the same substring-match bug class found and fixed
    in Module 3's Supervisor keyword classifier).
    """
    result = validate_readonly_sql("SELECT created_at, updated_at FROM documents", max_rows=50)
    assert "created_at" in result
    assert "updated_at" in result


# ---------------------------------------------------------------------------
# Database Service: schema discovery + safe execution against a real DB
# ---------------------------------------------------------------------------


@pytest.fixture
def sql_session(tmp_path):
    """A real SQLite-backed session with the application's actual schema,
    isolated to a temp file per test.
    """
    db_path = tmp_path / "sql_test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _seed_documents(session, count: int = 3) -> None:
    for i in range(count):
        session.add(
            DocumentModel(
                filename=f"doc{i}.pdf", file_hash=f"hash{i}", file_size=100, file_path=f"/tmp/doc{i}.pdf",
                status="COMPLETED", page_count=1, table_count=0, image_count=0, chunk_count=1,
            )
        )
    session.commit()


def test_sql_database_service_lists_known_tables(sql_session):
    service = SQLDatabaseService(readonly_db=sql_session)
    tables = service.list_tables()
    assert {"documents", "document_chunks", "extracted_assets"}.issubset(set(tables))


def test_sql_database_service_get_schema_reports_columns_and_primary_key(sql_session):
    service = SQLDatabaseService(readonly_db=sql_session)
    schema = service.get_schema()
    documents_table = next(t for t in schema if t.table_name == "documents")
    id_column = next(c for c in documents_table.columns if c.name == "id")
    assert id_column.primary_key is True
    filename_column = next(c for c in documents_table.columns if c.name == "filename")
    assert filename_column.primary_key is False


def test_sql_database_service_schema_description_is_compact_text(sql_session):
    service = SQLDatabaseService(readonly_db=sql_session)
    description = service.get_schema_description()
    assert "documents(" in description
    assert "document_chunks(" in description


def test_sql_database_service_executes_real_select(sql_session):
    _seed_documents(sql_session, count=3)
    service = SQLDatabaseService(readonly_db=sql_session)
    result = service.execute_sql("SELECT COUNT(*) AS total FROM documents")
    assert result.row_count == 1
    assert result.rows[0]["total"] == 3
    assert result.truncated is False


def test_sql_database_service_rejects_destructive_sql(sql_session):
    service = SQLDatabaseService(readonly_db=sql_session)
    with pytest.raises(ValidationException):
        service.execute_sql("DELETE FROM documents")


def test_sql_database_service_truncates_at_max_rows(sql_session):
    _seed_documents(sql_session, count=5)
    service = SQLDatabaseService(readonly_db=sql_session, max_rows=2)
    result = service.execute_sql("SELECT * FROM documents")
    assert result.row_count == 2
    assert result.truncated is True


def test_sql_execution_result_to_markdown(sql_session):
    _seed_documents(sql_session, count=2)
    service = SQLDatabaseService(readonly_db=sql_session)
    result = service.execute_sql("SELECT filename FROM documents ORDER BY filename")
    markdown = result.to_markdown()
    assert "filename" in markdown
    assert "doc0.pdf" in markdown


# ---------------------------------------------------------------------------
# Connection-level read-only enforcement (defense-in-depth, PRAGMA query_only)
# ---------------------------------------------------------------------------


def test_readonly_engine_pragma_rejects_writes_even_if_validation_bypassed(tmp_path):
    """Proves the connection-level safety net works independently of SQL
    string validation: a write attempted directly through a PRAGMA
    query_only connection must fail at the SQLite engine level.
    """
    db_path = tmp_path / "pragma_test.db"
    write_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=write_engine)

    readonly_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    from sqlalchemy import event

    event.listen(readonly_engine, "connect", _enable_readonly_mode)

    with pytest.raises(Exception):
        with readonly_engine.connect() as conn:
            conn.exec_driver_sql(
                "INSERT INTO documents (filename, file_hash, file_size, file_path, status, page_count, "
                "table_count, image_count, chunk_count, created_at, updated_at) "
                "VALUES ('x', 'h', 1, '/tmp/x', 'COMPLETED', 1, 0, 0, 1, datetime('now'), datetime('now'))"
            )


# ---------------------------------------------------------------------------
# Text-to-SQL generation
# ---------------------------------------------------------------------------


def test_text_to_sql_service_wraps_llm_failure():
    class BrokenStructuredLLM:
        def invoke(self, messages):
            raise RuntimeError("upstream failure")

    class BrokenLLM:
        def with_structured_output(self, schema):
            return BrokenStructuredLLM()

    service = TextToSQLService(llm=BrokenLLM())
    with pytest.raises(ExternalAPIException):
        service.generate_sql(question="How many documents are there?", schema_description="- documents(id INTEGER)")


def test_text_to_sql_service_returns_generated_sql():
    class FakeStructuredLLM:
        def invoke(self, messages):
            return GeneratedSQL(sql="SELECT COUNT(*) FROM documents", explanation="Counts documents.")

    class FakeLLM:
        def with_structured_output(self, schema):
            return FakeStructuredLLM()

    service = TextToSQLService(llm=FakeLLM())
    result = service.generate_sql(question="How many documents?", schema_description="- documents(id INTEGER)")
    assert result.sql == "SELECT COUNT(*) FROM documents"


# ---------------------------------------------------------------------------
# SQL Agent
# ---------------------------------------------------------------------------


def test_sql_agent_success_path(sql_session):
    _seed_documents(sql_session, count=4)
    agent = SQLAgent(
        text_to_sql=FakeTextToSQLService(sql="SELECT COUNT(*) AS total FROM documents"),
        database_service=SQLDatabaseService(readonly_db=sql_session),
    )
    result = agent.run(query="How many documents are there?")
    assert isinstance(result, SQLAgentResult)
    assert result.status == "success"
    assert result.data["rows"][0]["total"] == 4


def test_sql_agent_unanswerable_when_generation_returns_empty_sql(sql_session):
    agent = SQLAgent(
        text_to_sql=FakeTextToSQLService(sql="", explanation="This isn't a structured-data question."),
        database_service=SQLDatabaseService(readonly_db=sql_session),
    )
    result = agent.run(query="What color is the sky?")
    assert result.status == "unanswerable"
    assert result.data is None


def test_sql_agent_no_results_when_query_returns_zero_rows(sql_session):
    agent = SQLAgent(
        text_to_sql=FakeTextToSQLService(sql="SELECT * FROM documents WHERE filename = 'nonexistent.pdf'"),
        database_service=SQLDatabaseService(readonly_db=sql_session),
    )
    result = agent.run(query="Find nonexistent.pdf")
    assert result.status == "no_results"


def test_sql_agent_error_when_generation_fails(sql_session):
    class BrokenTextToSQL:
        def generate_sql(self, question, schema_description):
            raise ExternalAPIException(message="OpenAI unavailable")

    agent = SQLAgent(text_to_sql=BrokenTextToSQL(), database_service=SQLDatabaseService(readonly_db=sql_session))
    result = agent.run(query="How many documents?")
    assert result.status == "error"


def test_sql_agent_error_when_generated_sql_is_destructive(sql_session):
    agent = SQLAgent(
        text_to_sql=FakeTextToSQLService(sql="DROP TABLE documents"),
        database_service=SQLDatabaseService(readonly_db=sql_session),
    )
    result = agent.run(query="Delete everything")
    assert result.status == "error"
    assert result.data["sql"] == "DROP TABLE documents"


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------


def test_sql_tables_endpoint(isolated_client):
    response = isolated_client.get("/api/v1/sql/tables")
    assert response.status_code == status.HTTP_200_OK
    tables = response.json()["tables"]
    assert "documents" in tables


def test_sql_schema_endpoint(isolated_client):
    response = isolated_client.get("/api/v1/sql/schema")
    assert response.status_code == status.HTTP_200_OK
    tables = {t["table_name"]: t for t in response.json()["tables"]}
    assert "documents" in tables
    id_col = next(c for c in tables["documents"]["columns"] if c["name"] == "id")
    assert id_col["primary_key"] is True


def test_sql_execute_endpoint_runs_valid_select(isolated_client):
    pdf_bytes = make_pdf_bytes("Some content for SQL execution test.")
    isolated_client.post("/api/v1/documents/upload", files=[("files", ("a.pdf", pdf_bytes, "application/pdf"))])

    response = isolated_client.post("/api/v1/sql/execute", json={"sql": "SELECT COUNT(*) AS total FROM documents"})
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "success"
    assert data["rows"][0]["total"] >= 1


def test_sql_execute_endpoint_rejects_destructive_sql(isolated_client):
    response = isolated_client.post("/api/v1/sql/execute", json={"sql": "DROP TABLE documents"})
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_sql_execute_endpoint_rejects_multiple_statements(isolated_client):
    response = isolated_client.post(
        "/api/v1/sql/execute", json={"sql": "SELECT 1; DELETE FROM documents;"}
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST


def test_sql_query_endpoint_answers_natural_language_question(isolated_orchestrator_client):
    pdf_bytes = make_pdf_bytes("Doc for NL query test.")
    isolated_orchestrator_client.post(
        "/api/v1/documents/upload", files=[("files", ("a.pdf", pdf_bytes, "application/pdf"))]
    )

    response = isolated_orchestrator_client.post(
        "/api/v1/sql/query", json={"question": "How many documents have been uploaded?"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["status"] == "success"
    assert data["rows"][0]["total"] >= 1


# ---------------------------------------------------------------------------
# LangGraph integration + citations
# ---------------------------------------------------------------------------


def test_orchestrate_endpoint_invokes_sql_agent_and_preserves_database_citation(isolated_orchestrator_client):
    pdf_bytes = make_pdf_bytes("A document for the orchestrated SQL test.")
    isolated_orchestrator_client.post(
        "/api/v1/documents/upload", files=[("files", ("a.pdf", pdf_bytes, "application/pdf"))]
    )

    response = isolated_orchestrator_client.post(
        "/api/v1/orchestrate", json={"query": "How many documents are in the database?"}
    )

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "sql" in data["agents_invoked"]
    assert "sql_agent" in [step["agent"] for step in data["execution_trace"]]

    sql_step = next(s for s in data["execution_trace"] if s["agent"] == "sql_agent")
    assert sql_step["status"] == "success"

    database_citations = [c for c in data["citations"] if c["chunk_type"] == "database"]
    assert len(database_citations) == 1
    assert database_citations[0]["filename"] == "OmniBrain Database"


def test_orchestrate_endpoint_sql_and_retrieval_combine_when_both_routed(isolated_orchestrator_client):
    pdf_bytes = make_pdf_bytes("Quarterly revenue chart discussion table content.")
    isolated_orchestrator_client.post(
        "/api/v1/documents/upload", files=[("files", ("a.pdf", pdf_bytes, "application/pdf"))]
    )

    # "table" + "how many" keywords route to both retrieval and sql.
    response = isolated_orchestrator_client.post(
        "/api/v1/orchestrate", json={"query": "How many rows are in the revenue table?"}
    )
    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert "retrieval" in data["agents_invoked"]
    assert "sql" in data["agents_invoked"]
    chunk_types = {c["chunk_type"] for c in data["citations"]}
    assert "database" in chunk_types
