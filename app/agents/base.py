import asyncio
import time
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any

from app.core.job_store import job_store
from app.core.logger import get_logger
from app.schemas.job import AgentStatus

logger = get_logger(__name__)

MAX_RETRIES = 2
RETRY_DELAY = 3  # seconds


class BaseAgent(ABC):
    """
    Base class for all agents. Provides:
    - Automatic retry (up to MAX_RETRIES times on failure)
    - Per-agent execution timing
    - Heartbeat pinging every 5s
    - Timeout enforcement
    - Structured error capture and logging
    """

    name: str = "base_agent"
    timeout: int = 120
    retryable: bool = True  # set False on agents where retry makes no sense

    def __init__(self, job_id: str, repo_path: Path):
        self.job_id = job_id
        self.repo_path = repo_path
        self._heartbeat_task = None

    async def execute(self) -> Any:
        attempt = 0
        last_error = None

        while attempt <= (MAX_RETRIES if self.retryable else 0):
            attempt += 1
            start = time.perf_counter()

            await self._set_status("running", retries=attempt - 1)
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            try:
                result = await asyncio.wait_for(self.run(), timeout=self.timeout)
                duration = round(time.perf_counter() - start, 3)

                await self._set_status("completed", output=result, duration=duration)
                await job_store.record_agent_duration(self.job_id, self.name, duration)

                logger.info(
                    "Agent completed",
                    extra={"job_id": self.job_id, "agent": self.name,
                           "duration_s": duration, "attempt": attempt}
                )
                return result

            except asyncio.TimeoutError:
                duration = round(time.perf_counter() - start, 3)
                last_error = f"Timed out after {self.timeout}s"
                logger.warning("Agent timed out",
                    extra={"job_id": self.job_id, "agent": self.name, "attempt": attempt})

            except Exception as e:
                duration = round(time.perf_counter() - start, 3)
                last_error = str(e)
                logger.error("Agent error",
                    extra={"job_id": self.job_id, "agent": self.name,
                           "error": last_error, "attempt": attempt})

            finally:
                if self._heartbeat_task:
                    self._heartbeat_task.cancel()

            # Retry logic
            if attempt <= MAX_RETRIES and self.retryable:
                logger.info("Retrying agent",
                    extra={"job_id": self.job_id, "agent": self.name,
                           "attempt": attempt, "delay": RETRY_DELAY})
                await asyncio.sleep(RETRY_DELAY)
            else:
                break

        await self._set_status("failed", error=last_error, retries=attempt - 1)
        raise RuntimeError(f"Agent {self.name} failed after {attempt} attempt(s): {last_error}")

    @abstractmethod
    async def run(self) -> Any:
        ...

    async def _set_status(self, status: str, output: Any = None,
                           error: str = None, duration: float = None, retries: int = 0):
        agent_status = AgentStatus(
            name=self.name,
            status=status,
            started_at=datetime.utcnow() if status == "running" else None,
            completed_at=datetime.utcnow() if status in ("completed", "failed") else None,
            last_heartbeat=datetime.utcnow() if status == "running" else None,
            duration_seconds=duration,
            output=output,
            error=error,
            retries=retries,
        )
        await job_store.update_agent(self.job_id, self.name, agent_status)

    async def _heartbeat_loop(self):
        while True:
            await asyncio.sleep(5)
            await job_store.heartbeat(self.job_id, self.name)
