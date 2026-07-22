import logging
from typing import Generator
from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from backend.app.config.settings import settings
from backend.app.database.models import Base

logger = logging.getLogger("omnibrain.database")

# Setup SQLAlchemy engine
# SQLite-specific arguments (connect_args) are needed for multi-threaded SQLite usage in FastAPI
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=settings.DEBUG,
)

# Enable SQLite foreign key support
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if settings.DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# Setup SessionLocal factory
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    class_=Session,
)


def get_db() -> Generator[Session, None, None]:
    """Dependency injection generator to retrieve a database session.

    Ensures the session is closed after the request completes.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initializes the database schema and creates all tables."""
    try:
        logger.info("Initializing database schema...")
        Base.metadata.create_all(bind=engine)
        logger.info("Database schema initialized successfully.")
    except Exception as e:
        logger.exception("Failed to initialize database schema.")
        raise


def _enable_readonly_mode(dbapi_connection, connection_record) -> None:
    """SQLite connect-event handler that puts a connection into query-only
    mode, rejecting any write statement at the database engine level --
    defense-in-depth alongside the SQL Agent's SQL string validation
    (Module 5), applied only to the dedicated read-only engine below.
    """
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA query_only = ON;")
    cursor.close()


# Dedicated read-only engine/session used exclusively by the SQL Agent
# (Module 5) for safe, structured natural-language querying against the
# same database Modules 1-4 already write to.
readonly_engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=settings.DEBUG,
)
if settings.DATABASE_URL.startswith("sqlite"):
    event.listen(readonly_engine, "connect", _enable_readonly_mode)

ReadOnlySessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=readonly_engine,
    class_=Session,
)


def get_readonly_db() -> Generator[Session, None, None]:
    """Dependency injection generator for the SQL Agent's read-only session."""
    db = ReadOnlySessionLocal()
    try:
        yield db
    finally:
        db.close()
