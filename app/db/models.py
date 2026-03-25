"""
PostgreSQL Database Layer
-------------------------
Uses SQLAlchemy 2.0 async engine with asyncpg driver.

To activate:
  1. Set DATABASE_URL in .env:
       DATABASE_URL=postgresql+asyncpg://devagent:devagent@localhost:5432/devagent
  2. Run migrations:
       python -m app.db.models  (creates tables)
  3. In job_store.py, swap JobStore for PgJobStore

Tables:
  jobs       — one row per analysis job
  job_agents — one row per agent per job
"""

import os
from datetime import datetime

from sqlalchemy import JSON, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql+asyncpg://devagent:devagent@localhost:5432/devagent"
)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


class JobModel(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True)
    repo_url = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)

    agents = relationship("JobAgentModel", back_populates="job", cascade="all, delete-orphan")


class JobAgentModel(Base):
    __tablename__ = "job_agents"

    id = Column(String, primary_key=True)  # "{job_id}:{agent_name}"
    job_id = Column(String, ForeignKey("jobs.id"), nullable=False)
    name = Column(String, nullable=False)
    status = Column(String, nullable=False, default="pending")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    last_heartbeat = Column(DateTime, nullable=True)
    output = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)

    job = relationship("JobModel", back_populates="agents")


async def create_tables():
    """Create all tables. Call once at startup or use Alembic for migrations."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db() -> AsyncSession:
    """FastAPI dependency — yields a DB session."""
    async with AsyncSessionLocal() as session:
        yield session


# ── Run directly to create tables ─────────────────────────────────────────
if __name__ == "__main__":
    import asyncio

    asyncio.run(create_tables())
    print("Tables created.")
