"""SQLAlchemy async session factory for Celery worker tasks.

Celery (prefork) runs each task under its own event loop via ``asyncio.run``.
A module-level engine with a shared connection pool cannot be reused across
those loops: asyncpg binds every pooled connection to the loop it was created
on, so the next task (a brand-new loop) fails on check-out with
``Future attached to a different loop`` / ``Event loop is closed``.

Workers therefore use a ``NullPool`` engine — every task check-out opens a
fresh connection tied to its own loop — while the FastAPI app keeps the
pooled engine in ``database.py`` for its single long-lived uvicorn loop.
"""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from .config import settings

_engine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DEBUG,
    poolclass=NullPool,
)

SessionLocal = sessionmaker(
    _engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)