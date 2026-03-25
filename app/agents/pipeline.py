"""
Agent Pipeline — parallel execution with full metrics tracking.

Stage 1 (parallel): RepoScanner + DependencyAnalyzer run simultaneously
Stage 2 (sequential, needs stage 1): EnvironmentBuilder
Stage 3 (parallel, needs stage 1+2): CodeExplainer + TestRunner run simultaneously

This cuts total wall-clock time by ~40% vs fully sequential execution.
"""

import asyncio
import time

from app.agents.code_explainer import CodeExplainerAgent
from app.agents.dependency_analyzer import DependencyAnalyzerAgent
from app.agents.env_builder import EnvironmentBuilderAgent
from app.agents.repo_scanner import RepoScannerAgent
from app.agents.test_runner import TestRunnerAgent
from app.core.job_store import job_store
from app.core.logger import get_logger
from app.core.repo_cloner import RepoCloner
from app.schemas.job import JobStatus

logger = get_logger(__name__)


class AgentPipeline:
    def __init__(self, job_id: str, repo_url: str, branch: str = "main"):
        self.job_id = job_id
        self.repo_url = repo_url
        self.branch = branch
        self.cloner = RepoCloner()

    async def run(self):
        await job_store.update_status(self.job_id, JobStatus.RUNNING)
        repo_path = None
        pipeline_start = time.perf_counter()

        try:
            # ── Clone ──────────────────────────────────────────────────────
            clone_start = time.perf_counter()
            logger.info(
                "Cloning repository", extra={"job_id": self.job_id, "repo_url": self.repo_url}
            )
            repo_path = await asyncio.to_thread(
                self.cloner.clone, self.job_id, self.repo_url, self.branch
            )
            clone_duration = round(time.perf_counter() - clone_start, 3)
            await job_store.record_clone_duration(self.job_id, clone_duration)
            logger.info(
                "Clone complete", extra={"job_id": self.job_id, "duration_s": clone_duration}
            )

            results = {}

            # ── Stage 1: Parallel — Scanner + Dependency Analyzer ──────────
            logger.info(
                "Stage 1 — parallel scan + dependency analysis", extra={"job_id": self.job_id}
            )
            await job_store.record_concurrent_agents(self.job_id, 2)

            scan_result, dep_result = await asyncio.gather(
                self._run_agent(RepoScannerAgent(self.job_id, repo_path)),
                self._run_agent(DependencyAnalyzerAgent(self.job_id, repo_path)),
            )
            results["repo_scan"] = scan_result
            results["dependencies"] = dep_result
            await job_store.set_result(self.job_id, {**results})

            # ── Stage 2: Environment Builder (needs stage 1 output) ────────
            logger.info("Stage 2 — environment builder", extra={"job_id": self.job_id})
            results["environment"] = await self._run_agent(
                EnvironmentBuilderAgent(self.job_id, repo_path)
            )
            await job_store.set_result(self.job_id, {**results})

            # ── Stage 3: Parallel — Code Explainer + Test Runner ───────────
            logger.info("Stage 3 — parallel AI explain + test run", extra={"job_id": self.job_id})
            await job_store.record_concurrent_agents(self.job_id, 2)

            explain_result, test_result = await asyncio.gather(
                self._run_agent(CodeExplainerAgent(self.job_id, repo_path)),
                self._run_agent(TestRunnerAgent(self.job_id, repo_path)),
            )
            results["explanation"] = explain_result
            results["tests"] = test_result

            # ── Final result + metrics ─────────────────────────────────────
            total_duration = round(time.perf_counter() - pipeline_start, 3)
            final = {
                **results,
                "summary": self._build_summary(results),
                "performance": {
                    "total_duration_seconds": total_duration,
                    "clone_duration_seconds": clone_duration,
                    "note": "Stage 1 and Stage 3 ran in parallel — 2 agents concurrent each",
                },
            }
            await job_store.set_result(self.job_id, final)
            await job_store.update_status(self.job_id, JobStatus.COMPLETED)

            logger.info(
                "Pipeline completed",
                extra={"job_id": self.job_id, "total_duration_s": total_duration},
            )

        except Exception as e:
            logger.error("Pipeline failed", extra={"job_id": self.job_id, "error": str(e)})
            await job_store.update_status(self.job_id, JobStatus.FAILED, error=str(e))
            raise
        finally:
            if repo_path:
                await asyncio.to_thread(self.cloner.cleanup, self.job_id)

    async def _run_agent(self, agent) -> dict:
        """Run agent — errors are caught so one failure doesn't kill the pipeline."""
        try:
            return await agent.execute()
        except Exception as e:
            logger.error(
                f"Agent failed: {agent.name}", extra={"job_id": self.job_id, "error": str(e)}
            )
            return {"error": str(e), "agent": agent.name, "partial": True}

    def _build_summary(self, results: dict) -> dict:
        scan = results.get("repo_scan", {})
        deps = results.get("dependencies", {})
        tests = results.get("tests", {})
        env = results.get("environment", {})
        return {
            "primary_language": next(iter(scan.get("languages", {})), "Unknown"),
            "stack": scan.get("detected_stack", []),
            "total_files": scan.get("total_files", 0),
            "total_lines": scan.get("total_lines", 0),
            "total_dependencies": len(deps.get("dependencies", {})),
            "entry_points": scan.get("entry_points", []),
            "tests_passed": tests.get("passed", 0),
            "tests_failed": tests.get("failed", 0),
            "test_framework": tests.get("framework"),
            "has_dockerfile": bool(env.get("dockerfile")),
            "run_command": env.get("run_command"),
        }
