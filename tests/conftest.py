import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.app.main import app
from backend.app.database.connection import get_db, get_readonly_db
from backend.app.database.models import Base

# Setup an in-memory database for testing
TEST_DATABASE_URL = "sqlite:///./test.db"

engine = create_engine(TEST_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Fixture to initialize database tables before tests and clear them after."""
    # Create the tables
    Base.metadata.create_all(bind=engine)
    yield
    # Drop tables after test session ends
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db_session():
    """Provides a clean transactional database session for each test case."""
    connection = engine.connect()
    transaction = connection.begin()
    session = TestingSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def client(db_session):
    """Provides a FastAPI test client with database dependency override."""

    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    # Apply override. The SQL Agent (Module 5) reads through the same
    # session/transaction as everything else, so it sees data created
    # earlier in the same test without needing a separately committed DB.
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_readonly_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    # Clear override
    app.dependency_overrides.clear()
