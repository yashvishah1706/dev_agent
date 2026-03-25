import uuid
import json
from datetime import datetime
from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Request
from fastapi.responses import PlainTextResponse, JSONResponse

from app.core.job_store import job_store
from app.core.auth import get_current_user, User
from app.core.rate_limit import limiter
from app.core.logger import get_logger
from app.schemas.job import AnalyzeRequest, AnalyzeResponse, JobDetailResponse, JobStatus
from app.agents.pipeline import AgentPipeline

logger = get_logger(__name__)
router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse, status_code=202)
@limiter.limit("5/minute")
async def analyze_repo(
    request: Request,
    body: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """Start analysis. Rate limited: 5/min per IP. Returns job_id immediately."""
    job_id = str(uuid.uuid4())
    await job_store.create(job_id, body.repo_url)
    logger.info("Analysis job created",
        extra={"job_id": job_id, "repo_url": body.repo_url, "user": current_user.username})
    pipeline = AgentPipeline(job_id, body.repo_url, body.branch or "main")
    background_tasks.add_task(pipeline.run)
    return AnalyzeResponse(
        job_id=job_id,
        status=JobStatus.PENDING,
        message=f"Analysis started. Poll /api/v1/jobs/{job_id} for status.",
    )


@router.get("/jobs/{job_id}", response_model=JobDetailResponse)
@limiter.limit("60/minute")
async def get_job(request: Request, job_id: str,
                  current_user: User = Depends(get_current_user)):
    """Get current job status, agent states, results, and performance metrics."""
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    return JobDetailResponse(job=job)


@router.get("/jobs")
@limiter.limit("30/minute")
async def list_jobs(request: Request, current_user: User = Depends(get_current_user)):
    """List all jobs with summary info."""
    jobs = job_store.all_jobs()
    return {
        "total": len(jobs),
        "jobs": [
            {
                "id": j.id,
                "repo_url": j.repo_url,
                "status": j.status,
                "created_at": j.created_at,
                "completed_at": j.completed_at,
                "total_duration_seconds": j.metrics.total_duration_seconds if j.metrics else None,
            }
            for j in jobs.values()
        ],
    }


@router.get("/jobs/{job_id}/metrics")
async def get_metrics(job_id: str, current_user: User = Depends(get_current_user)):
    """
    Returns detailed performance metrics for a completed job:
    - Total pipeline duration
    - Per-agent timing
    - Clone duration
    - Token usage + estimated cost
    - Repo size (files + LOC)
    """
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if not job.metrics:
        return {"message": "No metrics available yet"}

    m = job.metrics
    agent_durations = m.agent_durations or {}

    return {
        "job_id": job_id,
        "status": job.status,
        "timing": {
            "total_seconds": m.total_duration_seconds,
            "clone_seconds": m.clone_duration_seconds,
            "agents": agent_durations,
            "slowest_agent": max(agent_durations, key=agent_durations.get) if agent_durations else None,
        },
        "repo": {
            "files": m.repo_size_files,
            "lines_of_code": m.repo_size_loc,
        },
        "ai": {
            "tokens_used": m.token_usage,
            "estimated_cost_usd": m.estimated_cost_usd,
            "model": "claude-sonnet-4-20250514",
        },
        "concurrency": {
            "max_parallel_agents": m.concurrent_agents,
            "note": "Stage 1 and Stage 3 ran agents in parallel",
        },
    }


@router.get("/jobs/{job_id}/export")
async def export_job(
    job_id: str,
    format: str = "json",
    current_user: User = Depends(get_current_user),
):
    """
    Export analysis results.
    - format=json  → full JSON download
    - format=markdown → human-readable Markdown report
    """
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    if job.status != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job not completed yet")

    if format == "markdown":
        md = _build_markdown_report(job)
        return PlainTextResponse(
            content=md,
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="dev-agent-{job_id[:8]}.md"'},
        )

    # Default: JSON
    return JSONResponse(
        content=_serialize_job(job),
        headers={"Content-Disposition": f'attachment; filename="dev-agent-{job_id[:8]}.json"'},
    )


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, current_user: User = Depends(get_current_user)):
    """Delete a job from the store."""
    job = await job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    job_store._jobs.pop(job_id, None)
    logger.info("Job deleted", extra={"job_id": job_id, "user": current_user.username})
    return {"message": f"Job {job_id} deleted"}


# ── Helpers ────────────────────────────────────────────────────────────────

def _serialize_job(job) -> dict:
    """Convert job to JSON-serializable dict."""
    def default(o):
        if isinstance(o, datetime):
            return o.isoformat()
        return str(o)
    import json
    return json.loads(json.dumps(job.model_dump(), default=default))


def _build_markdown_report(job) -> str:
    r = job.result or {}
    summary = r.get("summary", {})
    scan = r.get("repo_scan", {})
    deps = r.get("dependencies", {})
    env = r.get("environment", {})
    explanation = r.get("explanation", {})
    tests = r.get("tests", {})
    metrics = job.metrics

    lines = [
        f"# Dev Agent Analysis Report",
        f"",
        f"**Repository:** {job.repo_url}  ",
        f"**Analyzed:** {job.completed_at.strftime('%Y-%m-%d %H:%M UTC') if job.completed_at else 'N/A'}  ",
        f"**Status:** {job.status}",
        f"",
        f"---",
        f"",
        f"## Summary",
        f"",
        f"| Metric | Value |",
        f"|--------|-------|",
        f"| Primary Language | {summary.get('primary_language', 'N/A')} |",
        f"| Total Files | {summary.get('total_files', 'N/A')} |",
        f"| Lines of Code | {summary.get('total_lines', 'N/A')} |",
        f"| Dependencies | {summary.get('total_dependencies', 'N/A')} |",
        f"| Test Framework | {summary.get('test_framework', 'None detected')} |",
        f"| Tests Passed | {summary.get('tests_passed', 0)} |",
        f"| Tests Failed | {summary.get('tests_failed', 0)} |",
        f"",
        f"## Detected Stack",
        f"",
    ]

    for s in summary.get("stack", []):
        lines.append(f"- {s}")

    lines += [
        f"",
        f"## Languages",
        f"",
    ]
    for lang, count in list(scan.get("languages", {}).items())[:10]:
        lines.append(f"- **{lang}**: {count} files")

    lines += [f"", f"## Dependencies", f""]
    dep_list = list(deps.get("dependencies", {}).items())[:20]
    if dep_list:
        lines.append("| Package | Version |")
        lines.append("|---------|---------|")
        for pkg, ver in dep_list:
            lines.append(f"| `{pkg}` | `{ver}` |")
    else:
        lines.append("No dependencies found.")

    if env.get("dockerfile"):
        lines += [f"", f"## Generated Dockerfile", f"", f"```dockerfile", env["dockerfile"].strip(), f"```"]

    if env.get("run_command"):
        lines += [f"", f"## Run Command", f"", f"```bash", env["run_command"], f"```"]

    if explanation.get("architecture_explanation"):
        lines += [f"", f"## AI Architecture Explanation", f"", explanation["architecture_explanation"]]

    if metrics:
        lines += [
            f"",
            f"## Performance Metrics",
            f"",
            f"| Metric | Value |",
            f"|--------|-------|",
            f"| Total Duration | {metrics.total_duration_seconds}s |",
            f"| Clone Duration | {metrics.clone_duration_seconds}s |",
            f"| Token Usage | {metrics.token_usage or 'N/A'} |",
            f"| Estimated Cost | ${metrics.estimated_cost_usd or 'N/A'} |",
        ]
        for agent, dur in (metrics.agent_durations or {}).items():
            lines.append(f"| {agent} | {dur}s |")

    lines += [f"", f"---", f"*Generated by Dev Agent Platform*"]
    return "\n".join(lines)
