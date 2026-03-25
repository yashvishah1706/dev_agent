import asyncio
from datetime import datetime
from typing import Dict, Optional
from app.schemas.job import Job, JobStatus, AgentStatus, PerformanceMetrics


class JobStore:
    """
    In-memory job store with performance metrics tracking.
    Swap for PgJobStore in production.
    """

    def __init__(self):
        self._jobs: Dict[str, Job] = {}
        self._lock = asyncio.Lock()

    async def create(self, job_id: str, repo_url: str) -> Job:
        async with self._lock:
            job = Job(
                id=job_id,
                repo_url=repo_url,
                status=JobStatus.PENDING,
                created_at=datetime.utcnow(),
                agents={},
                metrics=PerformanceMetrics(),
            )
            self._jobs[job_id] = job
            return job

    async def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    async def update_status(self, job_id: str, status: JobStatus, error: Optional[str] = None):
        async with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.status = status
                if error:
                    job.error = error
                if status == JobStatus.COMPLETED:
                    job.completed_at = datetime.utcnow()
                    if job.metrics and job.created_at:
                        job.metrics.total_duration_seconds = round(
                            (job.completed_at - job.created_at).total_seconds(), 3
                        )

    async def update_agent(self, job_id: str, agent_name: str, agent_status: AgentStatus):
        async with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.agents[agent_name] = agent_status

    async def set_result(self, job_id: str, result: dict):
        async with self._lock:
            job = self._jobs.get(job_id)
            if job:
                job.result = result
                # Update repo size metrics from scan result
                if "repo_scan" in result and job.metrics:
                    scan = result["repo_scan"]
                    job.metrics.repo_size_files = scan.get("total_files")
                    job.metrics.repo_size_loc = scan.get("total_lines")

    async def heartbeat(self, job_id: str, agent_name: str):
        async with self._lock:
            job = self._jobs.get(job_id)
            if job and agent_name in job.agents:
                job.agents[agent_name].last_heartbeat = datetime.utcnow()

    async def record_agent_duration(self, job_id: str, agent_name: str, duration: float):
        async with self._lock:
            job = self._jobs.get(job_id)
            if job and job.metrics:
                job.metrics.agent_durations[agent_name] = duration

    async def record_clone_duration(self, job_id: str, duration: float):
        async with self._lock:
            job = self._jobs.get(job_id)
            if job and job.metrics:
                job.metrics.clone_duration_seconds = duration

    async def record_token_usage(self, job_id: str, tokens: int, cost_usd: float):
        async with self._lock:
            job = self._jobs.get(job_id)
            if job and job.metrics:
                job.metrics.token_usage = tokens
                job.metrics.estimated_cost_usd = round(cost_usd, 6)

    async def record_concurrent_agents(self, job_id: str, count: int):
        async with self._lock:
            job = self._jobs.get(job_id)
            if job and job.metrics:
                job.metrics.concurrent_agents = count

    def all_jobs(self) -> Dict[str, Job]:
        return dict(self._jobs)


job_store = JobStore()
