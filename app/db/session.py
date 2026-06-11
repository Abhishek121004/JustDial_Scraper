from collections.abc import Generator
import logging
from pathlib import Path
import shutil
import sqlite3

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings
from app.db.base import Base

logger = logging.getLogger(__name__)


def _sqlite_path_from_url(database_url: str) -> Path | None:
    if database_url.startswith("sqlite:///"):
        db_path = database_url.replace("sqlite:///", "", 1)
        if db_path != ":memory:":
            return Path(db_path)
    return None


def _sqlite_url_from_path(path: Path) -> str:
    return f"sqlite:///{path.as_posix()}"


def _can_write_sqlite(path: Path) -> bool:
    if not path.exists():
        return True
    try:
        with path.open("r+b"):
            pass
        con = sqlite3.connect(path)
        try:
            con.execute("PRAGMA user_version")
        finally:
            con.close()
        return True
    except OSError:
        return False
    except sqlite3.Error:
        return False


def _prepare_sqlite_database_url(database_url: str) -> str:
    db_path = _sqlite_path_from_url(database_url)
    if db_path is None:
        return database_url

    db_path.parent.mkdir(parents=True, exist_ok=True)
    if _can_write_sqlite(db_path):
        return database_url

    fallback_path = db_path.with_name(f"{db_path.stem}_runtime{db_path.suffix}")
    if not fallback_path.exists():
        try:
            shutil.copy2(db_path, fallback_path)
        except OSError as exc:
            logger.warning("Could not copy read-only SQLite DB %s: %s", db_path, exc)

    logger.warning(
        "SQLite DB %s is not writable; using writable runtime DB %s",
        db_path,
        fallback_path,
    )
    return _sqlite_url_from_path(fallback_path)


database_url = _prepare_sqlite_database_url(settings.database_url)

engine = create_engine(
    database_url,
    connect_args={"check_same_thread": False} if database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
