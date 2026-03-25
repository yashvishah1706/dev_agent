"""
Agent 4 — Code Explainer (AI-powered)
Calls Claude API with structured prompts.
Tracks token usage and estimated cost.
"""

import os
from pathlib import Path
from typing import Any

from app.agents.base import BaseAgent
from app.core.config import settings
from app.core.logger import get_logger

logger = get_logger(__name__)

MAX_FILE_CHARS = 3000
MAX_FILES = 8

# Claude Sonnet pricing (per million tokens, as of 2025)
COST_PER_INPUT_TOKEN = 3.00 / 1_000_000
COST_PER_OUTPUT_TOKEN = 15.00 / 1_000_000


class CodeExplainerAgent(BaseAgent):
    name = "code_explainer"
    timeout = 120
    retryable = True

    async def run(self) -> Any:
        if not settings.anthropic_api_key:
            return {
                "error": "ANTHROPIC_API_KEY not set. Add it to your .env file.",
                "architecture_explanation": None,
                "token_usage": None,
            }

        from app.core.job_store import job_store
        job = await job_store.get(self.job_id)
        scan, deps = {}, {}
        if job and job.result:
            scan = job.result.get("repo_scan", {})
            deps = job.result.get("dependencies", {})

        file_samples = self._sample_files()
        prompt = self._build_prompt(scan, deps, file_samples)
        response, usage = await self._call_claude(prompt)

        # Record cost metrics
        if usage:
            input_tokens = usage.input_tokens
            output_tokens = usage.output_tokens
            total_tokens = input_tokens + output_tokens
            cost = (input_tokens * COST_PER_INPUT_TOKEN) + (output_tokens * COST_PER_OUTPUT_TOKEN)
            await job_store.record_token_usage(self.job_id, total_tokens, cost)
            logger.info("Token usage recorded",
                extra={"job_id": self.job_id, "tokens": total_tokens,
                       "cost_usd": round(cost, 6)})

        return {
            "architecture_explanation": response,
            "files_analyzed": list(file_samples.keys()),
            "model_used": settings.llm_model,
            "token_usage": {
                "input": usage.input_tokens if usage else None,
                "output": usage.output_tokens if usage else None,
                "total": (usage.input_tokens + usage.output_tokens) if usage else None,
                "estimated_cost_usd": round(
                    (usage.input_tokens * COST_PER_INPUT_TOKEN) +
                    (usage.output_tokens * COST_PER_OUTPUT_TOKEN), 6
                ) if usage else None,
            },
        }

    def _sample_files(self) -> dict[str, str]:
        priority_names = [
            "main.py", "app.py", "server.py", "index.js", "index.ts",
            "main.go", "main.rs", "manage.py", "settings.py", "config.py",
            "routes.py", "models.py", "schema.py", "database.py",
        ]
        samples = {}
        skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build", ".next"}

        for fname in priority_names:
            for fpath in self.repo_path.rglob(fname):
                if any(skip in fpath.parts for skip in skip_dirs):
                    continue
                rel = str(fpath.relative_to(self.repo_path))
                if rel not in samples:
                    content = self._read_truncated(fpath)
                    if content:
                        samples[rel] = content
                if len(samples) >= MAX_FILES:
                    break

        if len(samples) < MAX_FILES:
            for ext in ("*.py", "*.ts", "*.go", "*.rs", "*.js"):
                for fpath in self.repo_path.rglob(ext):
                    if any(skip in fpath.parts for skip in skip_dirs):
                        continue
                    rel = str(fpath.relative_to(self.repo_path))
                    if rel not in samples:
                        content = self._read_truncated(fpath)
                        if content:
                            samples[rel] = content
                    if len(samples) >= MAX_FILES:
                        break

        return samples

    def _read_truncated(self, path: Path) -> str:
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            if len(content) > MAX_FILE_CHARS:
                content = content[:MAX_FILE_CHARS] + "\n... [truncated]"
            return content
        except Exception:
            return ""

    def _build_prompt(self, scan: dict, deps: dict, files: dict) -> str:
        stack = ", ".join(scan.get("detected_stack", ["unknown"]))
        languages = ", ".join(
            f"{lang} ({count} files)"
            for lang, count in list(scan.get("languages", {}).items())[:5]
        )
        total_files = scan.get("total_files", "?")
        total_lines = scan.get("total_lines", "?")
        dep_count = len(deps.get("dependencies", {}))
        top_deps = ", ".join(list(deps.get("dependencies", {}).keys())[:10])

        files_section = "\n\n".join(
            f"### {path}\n```\n{content}\n```"
            for path, content in files.items()
        )

        return f"""You are a senior software architect reviewing a codebase. Analyze this repository and provide a structured technical explanation.

## Repository Overview
- Stack: {stack}
- Languages: {languages}
- Total files: {total_files} | Total lines: {total_lines}
- Dependencies ({dep_count} total): {top_deps}

## Key Files
{files_section}

## Your Task
Provide a structured analysis with EXACTLY these sections:

**1. Architecture Overview**
3-5 sentences: what does this project do and how is it structured?

**2. Module Breakdown**
For each key file above, 1-2 sentences on its role.

**3. Data Flow**
How data moves from entry point to output.

**4. Identified Issues**
3-5 specific problems, anti-patterns, or risks in the actual code.

**5. Improvement Suggestions**
3-5 concrete, actionable improvements with brief explanations.

**6. Architecture Diagram (ASCII)**
A simple ASCII diagram showing main components and connections.

Be specific. Reference actual file names and function names where relevant."""

    async def _call_claude(self, prompt: str):
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        try:
            message = await client.messages.create(
                model=settings.llm_model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            return message.content[0].text, message.usage
        except anthropic.AuthenticationError:
            return "Error: Invalid ANTHROPIC_API_KEY.", None
        except anthropic.RateLimitError:
            return "Error: Anthropic rate limit hit. Try again shortly.", None
        except Exception as e:
            logger.error("Claude API call failed", extra={"error": str(e)})
            return f"Error calling Claude API: {str(e)}", None
