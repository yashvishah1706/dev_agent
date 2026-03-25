from enum import Enum
from datetime import datetime
from typing import Dict, Optional, Any
from pydantic import BaseModel


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentStatus(BaseModel):
    name: str
    status: str = "pending"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    output: Optional[Any] = None
    error: Optional[str] = None
    retries: int = 0


class PerformanceMetrics(BaseModel):
    total_duration_seconds: Optional[float] = None
    clone_duration_seconds: Optional[float] = None
    agent_durations: Dict[str, float] = {}
    token_usage: Optional[int] = None
    estimated_cost_usd: Optional[float] = None
    repo_size_files: Optional[int] = None
    repo_size_loc: Optional[int] = None
    concurrent_agents: int = 0


class Job(BaseModel):
    id: str
    repo_url: str
    status: JobStatus
    created_at: datetime
    completed_at: Optional[datetime] = None
    agents: Dict[str, AgentStatus] = {}
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metrics: Optional[PerformanceMetrics] = None


class AnalyzeRequest(BaseModel):
    repo_url: str
    branch: Optional[str] = "main"

    model_config = {
        "json_schema_extra": {
            "example": {
                "repo_url": "https://github.com/tiangolo/fastapi",
                "branch": "master"
            }
        }
    }


class AnalyzeResponse(BaseModel):
    job_id: str
    status: JobStatus
    message: str


class JobDetailResponse(BaseModel):
    job: Job


class ExportFormat(str, Enum):
    JSON = "json"
    MARKDOWN = "markdown"
