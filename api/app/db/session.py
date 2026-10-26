from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    return create_engine(get_settings().database_url, pool_pre_ping=True)


@lru_cache
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    """Request-scoped session.

    Routes commit explicitly when their work is complete. Anything not committed
    (e.g. on an exception) is rolled back when the session closes. Commits are kept
    explicit so that a commit can never happen after an error response is chosen.
    """
    db = get_sessionmaker()()
    try:
        yield db
    finally:
        db.close()
