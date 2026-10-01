import logging
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from src.config.settings import settings
from src.db.models import Base
log = logging.getLogger(__name__)
engine = create_async_engine(settings.database_url, pool_pre_ping=True, pool_size=5, max_overflow=10) if settings.database_url else None
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession) if engine else None
async def init_database() -> None:
    if not engine: raise RuntimeError("DATABASE_URL is required")
    async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all)
async def close_database() -> None:
    if engine: await engine.dispose()
