"""SQLAlchemy database connection and session management."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from operator_copilot.config.settings import Settings, get_settings
from operator_copilot.db.models import Base, SystemState


class DatabaseManager:
    """Manages SQLAlchemy engine, schema initialization, and session lifecycle."""

    def __init__(self, database_url: str) -> None:
        connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, connect_args=connect_args, future=True)

        if database_url.startswith("sqlite"):
            @event.listens_for(self.engine, "connect")
            def _enable_sqlite_fk(dbapi_connection, connection_record) -> None:  # noqa: ANN001
                cursor = dbapi_connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.close()

        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        self.init_db()

    def init_db(self) -> None:
        """Create tables if they do not exist and ensure initial corpus_version."""
        Base.metadata.create_all(bind=self.engine)
        with self.session() as db:
            state = db.get(SystemState, "corpus_version")
            if state is None:
                db.add(SystemState(key="corpus_version", value="v0"))
                db.commit()

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a database session with automatic rollback on errors."""
        db = self.SessionLocal()
        try:
            yield db
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def get_corpus_version(self) -> str:
        """Return the current active corpus version string."""
        with self.session() as db:
            state = db.get(SystemState, "corpus_version")
            return state.value if state else "v0"

    def set_state(self, key: str, value: str) -> None:
        """Upsert a system state key-value pair."""
        with self.session() as db:
            state = db.get(SystemState, key)
            if state is None:
                db.add(SystemState(key=key, value=value))
            else:
                state.value = value
            db.commit()

    def get_state(self, key: str, default: str = "") -> str:
        """Read a system state value by key."""
        with self.session() as db:
            state = db.get(SystemState, key)
            return state.value if state else default


_db_manager_cache: dict[str, DatabaseManager] = {}


def get_db_manager(settings: Settings | None = None) -> DatabaseManager:
    """Return a cached DatabaseManager for the configured database URL."""
    cfg = settings or get_settings()
    cfg.ensure_directories()
    if cfg.database_url not in _db_manager_cache:
        _db_manager_cache[cfg.database_url] = DatabaseManager(cfg.database_url)
    return _db_manager_cache[cfg.database_url]
