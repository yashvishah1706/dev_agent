import asyncio
from datetime import datetime, timedelta

from app.schemas.job import JobStatus


class HeartbeatMonitor:
    """
    Runs every 5 seconds, checks each running agent's last heartbeat.
    If an agent hasn't pinged in 30 seconds, it's marked as 'stalled'.
    """

    INTERVAL = 5  # seconds between checks
    TIMEOUT = 30  # seconds before an agent is considered stalled

    def __init__(self, job_store):
        self.job_store = job_store
        self._running = False

    async def start(self):
        self._running = True
        while self._running:
            await self._check()
            await asyncio.sleep(self.INTERVAL)

    def stop(self):
        self._running = False

    async def _check(self):
        jobs = self.job_store.all_jobs()
        now = datetime.utcnow()
        stale_cutoff = now - timedelta(seconds=self.TIMEOUT)

        for job_id, job in jobs.items():
            if job.status not in (JobStatus.RUNNING,):
                continue
            for agent_name, agent in job.agents.items():
                if agent.status == "running" and agent.last_heartbeat:
                    if agent.last_heartbeat < stale_cutoff:
                        agent.status = "stalled"
                        print(f"[Heartbeat] Agent {agent_name} in job {job_id} is STALLED")
