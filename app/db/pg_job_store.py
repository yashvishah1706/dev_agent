"""
PgJobStore — PostgreSQL-backed drop-in replacement for JobStore.
---------------------------------------------------------------
Swap in main.py:
    from app.db.pg_job_store import PgJobStore
    job_store = PgJobStore()

Identical interface to the in-memory JobStore so nothing else changes.
"""

import uuid
from datetime import datetime
from typing import Dict, Optional

from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.db.models import AsyncSessionLocal, JobModel, JobAgentModel
from app.schemas.job import Job, JobStatus, AgentStatus


class PgJobStore:
    """Persists all jobs and agent states in PostgreSQL."""

    async def create(self, job_id: str, repo_url: str) -> Job:
        async with AsyncSessionLocal() as session:
            job = JobModel(
                id=job_id,
                repo_url=repo_url,
                status="pending",
                created_at=datetime.utcnow(),
            )
            session.add(job)
            await session.commit()
        return Job(
            id=job_id,
            repo_url=repo_url,
            status=JobStatus.PENDING,
            created_at=datetime.utcnow(),
        )

    async def get(self, job_id: str) -> Optional[Job]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(JobModel)
                .options(selectinload(JobModel.agents))
                .where(JobModel.id == job_id)
            )
            row = result.scalar_one_or_none()
            if not row:
                return None
            return self._to_schema(row)

    async def update_status(self, job_id: str, status: JobStatus, error: Optional[str] = None):
        async with AsyncSessionLocal() as session:
            values = {"status": status.value}
            if error:
                values["error"] = error
            if status == JobStatus.COMPLETED:
                values["completed_at"] = datetime.utcnow()
            await session.execute(
                update(JobModel).where(JobModel.id == job_id).values(**values)
            )
            await session.commit()

    async def update_agent(self, job_id: str, agent_name: str, agent_status: AgentStatus):
        async with AsyncSessionLocal() as session:
            pk = f"{job_id}:{agent_name}"
            result = await session.execute(
                select(JobAgentModel).where(JobAgentModel.id == pk)
            )
            row = result.scalar_one_or_none()
            if row:
                row.status = agent_status.status
                row.started_at = agent_status.started_at
                row.completed_at = agent_status.completed_at
                row.last_heartbeat = agent_status.last_heartbeat
                row.output = agent_status.output
                row.error = agent_status.error
            else:
                session.add(JobAgentModel(
                    id=pk,
                    job_id=job_id,
                    name=agent_name,
                    status=agent_status.status,
                    started_at=agent_status.started_at,
                    completed_at=agent_status.completed_at,
                    last_heartbeat=agent_status.last_heartbeat,
                    output=agent_status.output,
                    error=agent_status.error,
                ))
            await session.commit()

    async def set_result(self, job_id: str, result: dict):
        async with AsyncSessionLocal() as session:
            await session.execute(
                update(JobModel).where(JobModel.id == job_id).values(result=result)
            )
            await session.commit()

    async def heartbeat(self, job_id: str, agent_name: str):
        async with AsyncSessionLocal() as session:
            pk = f"{job_id}:{agent_name}"
            await session.execute(
                update(JobAgentModel)
                .where(JobAgentModel.id == pk)
                .values(last_heartbeat=datetime.utcnow())
            )
            await session.commit()

    def all_jobs(self) -> Dict[str, Job]:
        """Sync wrapper — for heartbeat monitor compatibility."""
        import asyncio
        return asyncio.get_event_loop().run_until_complete(self._all_jobs_async())

    async def _all_jobs_async(self) -> Dict[str, Job]:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(JobModel).options(selectinload(JobModel.agents))
            )
            rows = result.scalars().all()
            return {row.id: self._to_schema(row) for row in rows}

    def _to_schema(self, row: JobModel) -> Job:
        return Job(
            id=row.id,
            repo_url=row.repo_url,
            status=JobStatus(row.status),
            created_at=row.created_at,
            completed_at=row.completed_at,
            result=row.result,
            error=row.error,
            agents={
                a.name: AgentStatus(
                    name=a.name,
                    status=a.status,
                    started_at=a.started_at,
                    completed_at=a.completed_at,
                    last_heartbeat=a.last_heartbeat,
                    output=a.output,
                    error=a.error,
                )
                for a in (row.agents or [])
            },
        )
