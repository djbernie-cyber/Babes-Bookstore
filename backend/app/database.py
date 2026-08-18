from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import settings

Base = declarative_base()

_engine_kwargs = {"echo": settings.DEBUG}
if not settings.DATABASE_URL.startswith("sqlite"):
    _engine_kwargs.update(pool_pre_ping=True, pool_size=10, max_overflow=20)

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)

AsyncSessionLocal = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create tables directly.

    Only intended for local development and tests. In production, schema
    changes must go through Alembic migrations (`alembic upgrade head`),
    because create_all() will not apply changes to existing tables.
    """
    if not settings.DEBUG and not settings.DATABASE_URL.startswith("sqlite"):
        # Production schema is owned by Alembic; verify connectivity only.
        async with engine.begin() as conn:
            await conn.run_sync(lambda c: None)
        return

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)