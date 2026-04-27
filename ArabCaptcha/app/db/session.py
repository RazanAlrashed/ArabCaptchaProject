"""
db/session.py

Sets up the SQLAlchemy engine and session factory.
Import `get_db` in routers to get a database session per request.
"""
'''
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings

# The engine is the core interface to the database.
# check_same_thread=False is required for SQLite to work with FastAPI.
engine = create_engine(
    settings.DATABASE_URL,
    connect_args={"check_same_thread": False} if "sqlite" in settings.DATABASE_URL else {},
)

# Each request gets its own session, which is closed when the request ends.
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """Base class that all database models will inherit from."""
    pass


def get_db():
    """
    FastAPI dependency that provides a database session per request.
    Usage in a router:
        db: Session = Depends(get_db)
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
'''


"""
db/session.py

Database engine and session factory.

SQLite-specific fixes applied here:
  • check_same_thread=False  — FastAPI runs handlers in a thread pool
  • WAL journal mode         — allows concurrent reads + one writer
  • busy_timeout = 5000 ms  — wait up to 5 s instead of failing instantly
  • StaticPool (single conn) — eliminates "database is locked" on SQLite
    because all threads share one underlying connection

Switch to MySQL/PostgreSQL for production: change DATABASE_URL in .env
and remove the connect_args / poolclass overrides.
"""

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from sqlalchemy.pool import StaticPool

from app.core.config import settings


# ── Engine ────────────────────────────────────────────────────────────────
_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

if _is_sqlite:
    engine = create_engine(
        settings.DATABASE_URL,
        connect_args={
            "check_same_thread": False,   # allow multi-threaded access
            "timeout": 15,                # seconds to wait on a lock
        },
        # StaticPool = one real connection reused across all sessions.
        # This is the simplest fix for "database is locked" during dev.
        poolclass=StaticPool,
        echo=False,
    )

    # Enable WAL mode and set a generous busy timeout once on connect.
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_conn, _connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")   # ms — wait before raising OperationalError
        cursor.execute("PRAGMA synchronous=NORMAL")  # safer than OFF, faster than FULL
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

else:
    # MySQL / PostgreSQL — use a normal connection pool
    engine = create_engine(
        settings.DATABASE_URL,
        pool_pre_ping=True,   # recycle stale connections automatically
        echo=False,
    )


# ── Session factory ───────────────────────────────────────────────────────
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


# ── Base model ────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


# ── FastAPI dependency ────────────────────────────────────────────────────
def get_db():
    """Yield a DB session; always close it after the request finishes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()