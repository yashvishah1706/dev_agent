from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentStatus(BaseModel):
    name: str
    status: str = "pending"
    started_at: datetime | None = None
    completed_at: datetime | None = None
    last_heartbeat: datetime | None = None
    duration_seconds: float | None = None
    output: Any | None = None
    error: str | None = None
    retries: int = 0


class PerformanceMetrics(BaseModel):
    total_duration_seconds: float | None = None
    clone_duration_seconds: float | None = None
    agent_durations: dict[str, float] = {}
    token_usage: int | None = None
    estimated_cost_usd: float | None = None
    repo_size_files: int | None = None
    repo_size_loc: int | None = None
    concurrent_agents: int = 0


class Job(BaseModel):
    id: str
    repo_url: str
    status: JobStatus
    created_at: datetime
    completed_at: datetime | None = None
    agents: dict[str, AgentStatus] = {}
    result: dict[str, Any] | None = None
    error: str | None = None
    metrics: PerformanceMetrics | None = None


class AnalyzeRequest(BaseModel):
    repo_url: str
    branch: str | None = "main"

    model_config = {
        "json_schema_extra": {
            "example": {"repo_url": "https://github.com/tiangolo/fastapi", "branch": "master"}
        }
    }


class AnalyzeResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str


class JobDetailResponse(BaseModel):
    job: Job


class ExportFormat(StrEnum):
    JSON = "json"
    MARKDOWN = "markdown"
