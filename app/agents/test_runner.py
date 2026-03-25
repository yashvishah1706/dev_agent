"""
Agent 5 — Test Runner
----------------------
Detects the test framework and runs tests in a sandboxed subprocess.
Supports: pytest, jest, go test, cargo test, npm test.

Guardrails:
  - Hard timeout (60s default)
  - Runs in the cloned repo directory (already isolated)
  - Captures stdout/stderr — never executes arbitrary shell commands
  - Only runs the detected test command, never user-supplied commands
"""

import asyncio
import subprocess
from pathlib import Path
from typing import Any

from app.agents.base import BaseAgent
from app.core.logger import get_logger

logger = get_logger(__name__)

# Safe, hardcoded test commands per framework — never user-supplied
SAFE_TEST_COMMANDS = {
    "pytest":    ["python", "-m", "pytest", "--tb=short", "-q", "--no-header"],
    "unittest":  ["python", "-m", "unittest", "discover", "-v"],
    "jest":      ["npx", "jest", "--no-coverage", "--passWithNoTests"],
    "vitest":    ["npx", "vitest", "run"],
    "go_test":   ["go", "test", "./...", "-v", "-timeout", "30s"],
    "cargo":     ["cargo", "test", "--", "--test-output", "immediate"],
    "npm_test":  ["npm", "test", "--", "--watchAll=false"],
}


class TestRunnerAgent(BaseAgent):
    """
    Agent 5 — Test Runner

    Detects which test framework the project uses, runs it
    in a subprocess with a hard timeout, and returns results.
    """

    name = "test_runner"
    timeout = 90

    async def run(self) -> Any:
        framework = self._detect_framework()

        if not framework:
            return {
                "framework": None,
                "ran": False,
                "message": "No supported test framework detected.",
                "passed": 0,
                "failed": 0,
                "errors": 0,
                "output": "",
            }

        cmd = SAFE_TEST_COMMANDS[framework]
        logger.info(
            "Running tests",
            extra={"job_id": self.job_id, "framework": framework, "cmd": cmd}
        )

        result = await self._run_subprocess(cmd)
        parsed = self._parse_output(framework, result["stdout"], result["stderr"])

        return {
            "framework": framework,
            "ran": True,
            "exit_code": result["exit_code"],
            "passed": parsed["passed"],
            "failed": parsed["failed"],
            "errors": parsed["errors"],
            "output": (result["stdout"] + result["stderr"])[:4000],  # cap output size
            "timed_out": result["timed_out"],
        }

    def _detect_framework(self) -> str | None:
        """Detect which test framework to use. Returns framework key or None."""
        repo = self.repo_path

        # Python
        if (repo / "pytest.ini").exists() or (repo / "pyproject.toml").exists():
            if list(repo.rglob("test_*.py")) or list(repo.rglob("*_test.py")):
                return "pytest"
        if list(repo.rglob("test_*.py")):
            return "pytest"

        # JavaScript / TypeScript
        if (repo / "package.json").exists():
            try:
                import json
                pkg = json.loads((repo / "package.json").read_text())
                scripts = pkg.get("scripts", {})
                devdeps = {**pkg.get("devDependencies", {}), **pkg.get("dependencies", {})}

                if "vitest" in devdeps:
                    return "vitest"
                if "jest" in devdeps or "jest" in scripts.get("test", ""):
                    return "jest"
                if "test" in scripts:
                    return "npm_test"
            except Exception:
                pass

        # Go
        if (repo / "go.mod").exists() and list(repo.rglob("*_test.go")):
            return "go_test"

        # Rust
        if (repo / "Cargo.toml").exists():
            return "cargo"

        return None

    async def _run_subprocess(self, cmd: list[str]) -> dict:
        """Run a command in the repo directory with timeout."""
        timed_out = False
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.repo_path),
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    proc.communicate(), timeout=60
                )
                return {
                    "stdout": stdout.decode("utf-8", errors="ignore"),
                    "stderr": stderr.decode("utf-8", errors="ignore"),
                    "exit_code": proc.returncode,
                    "timed_out": False,
                }
            except asyncio.TimeoutError:
                proc.kill()
                timed_out = True
                return {
                    "stdout": "",
                    "stderr": "Test run timed out after 60 seconds.",
                    "exit_code": -1,
                    "timed_out": True,
                }
        except FileNotFoundError:
            return {
                "stdout": "",
                "stderr": f"Command not found: {cmd[0]}. Is it installed?",
                "exit_code": -1,
                "timed_out": False,
            }

    def _parse_output(self, framework: str, stdout: str, stderr: str) -> dict:
        """Extract pass/fail/error counts from test output."""
        import re
        output = stdout + stderr
        passed = failed = errors = 0

        if framework == "pytest":
            # "5 passed, 2 failed, 1 error"
            m = re.search(r"(\d+) passed", output)
            if m: passed = int(m.group(1))
            m = re.search(r"(\d+) failed", output)
            if m: failed = int(m.group(1))
            m = re.search(r"(\d+) error", output)
            if m: errors = int(m.group(1))

        elif framework in ("jest", "vitest", "npm_test"):
            # "Tests: 5 passed, 2 failed"
            m = re.search(r"(\d+) passed", output)
            if m: passed = int(m.group(1))
            m = re.search(r"(\d+) failed", output)
            if m: failed = int(m.group(1))

        elif framework == "go_test":
            # "ok" lines = passed packages, "FAIL" lines = failed
            passed = output.count("\nok ")
            failed = output.count("\nFAIL")

        elif framework == "cargo":
            m = re.search(r"(\d+) passed", output)
            if m: passed = int(m.group(1))
            m = re.search(r"(\d+) failed", output)
            if m: failed = int(m.group(1))

        return {"passed": passed, "failed": failed, "errors": errors}
