from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase, Session


class Base(DeclarativeBase):
    pass


@lru_cache
def _get_engine() -> Engine:
    from app.core.config import get_settings
    return create_engine(
        get_settings().DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_pre_ping=True,
    )


def SessionLocal() -> Session:
    engine = _get_engine()
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    return factory()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
