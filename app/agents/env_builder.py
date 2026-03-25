"""
Agent 3 — Environment Builder
------------------------------
Reads the repo scan output and generates:
  - A working Dockerfile tailored to the detected stack
  - docker-compose.yml if a database is detected
  - Plain-English setup instructions
  - One-liner run command
"""

from pathlib import Path
from typing import Any

from app.agents.base import BaseAgent
from app.core.logger import get_logger

logger = get_logger(__name__)


PYTHON_DOCKERFILE = '''\
FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y git && rm -rf /var/lib/apt/lists/*

{copy_deps}
RUN {install_cmd}

COPY . .

EXPOSE 8000

CMD {run_cmd}
'''

NODE_DOCKERFILE = '''\
FROM node:20-alpine

WORKDIR /app

COPY package*.json ./
RUN npm install --production

COPY . .

EXPOSE 3000

CMD {run_cmd}
'''

GO_DOCKERFILE = '''\
FROM golang:1.22-alpine AS builder

WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN go build -o main .

FROM alpine:latest
WORKDIR /app
COPY --from=builder /app/main .
EXPOSE 8080
CMD ["./main"]
'''

RUST_DOCKERFILE = '''\
FROM rust:1.75-slim AS builder
WORKDIR /app
COPY . .
RUN cargo build --release

FROM debian:bookworm-slim
WORKDIR /app
COPY --from=builder /app/target/release/app .
EXPOSE 8080
CMD ["./app"]
'''


class EnvironmentBuilderAgent(BaseAgent):
    """
    Agent 3 — Environment Builder

    Input:  repo_scan result from RepoScannerAgent
    Output: Dockerfile, setup instructions, run command
    """

    name = "environment_builder"
    timeout = 30

    async def run(self) -> Any:
        # Read scan results from the job store to inform generation
        from app.core.job_store import job_store
        job = await job_store.get(self.job_id)
        scan = {}
        if job and job.result and "repo_scan" in job.result:
            scan = job.result["repo_scan"]

        stack = scan.get("detected_stack", [])
        config_files = scan.get("config_files", [])
        languages = scan.get("languages", {})
        entry_points = scan.get("entry_points", [])

        primary_lang = next(iter(languages), "").lower()

        result = {
            "dockerfile": None,
            "docker_compose": None,
            "setup_instructions": [],
            "run_command": None,
            "detected_stack": stack,
            "notes": [],
        }

        # ── Python ────────────────────────────────────────────────────────
        if "Python" in languages or any("Python" in s for s in stack):
            install_cmd, copy_deps = self._python_install(config_files)
            run_cmd = self._python_run_cmd(entry_points, config_files)
            result["dockerfile"] = PYTHON_DOCKERFILE.format(
                copy_deps=copy_deps,
                install_cmd=install_cmd,
                run_cmd=run_cmd,
            )
            result["run_command"] = f"docker build -t my-app . && docker run -p 8000:8000 my-app"
            result["setup_instructions"] = [
                "1. Install Python 3.12+",
                f"2. Run: {install_cmd.replace('pip install', 'pip install')}",
                f"3. Run: {self._python_run_cmd(entry_points, config_files, docker=False)}",
            ]

        # ── Node.js ───────────────────────────────────────────────────────
        elif "Node.js" in stack or "JavaScript" in languages or "TypeScript" in languages:
            run_cmd = self._node_run_cmd(self.repo_path)
            result["dockerfile"] = NODE_DOCKERFILE.format(run_cmd=run_cmd)
            result["run_command"] = "docker build -t my-app . && docker run -p 3000:3000 my-app"
            result["setup_instructions"] = [
                "1. Install Node.js 20+",
                "2. Run: npm install",
                "3. Run: npm start",
            ]

        # ── Go ────────────────────────────────────────────────────────────
        elif "Go" in stack or "Go" in languages:
            result["dockerfile"] = GO_DOCKERFILE
            result["run_command"] = "docker build -t my-app . && docker run -p 8080:8080 my-app"
            result["setup_instructions"] = [
                "1. Install Go 1.22+",
                "2. Run: go mod download",
                "3. Run: go run main.go",
            ]

        # ── Rust ──────────────────────────────────────────────────────────
        elif "Rust" in stack or "Rust" in languages:
            result["dockerfile"] = RUST_DOCKERFILE
            result["run_command"] = "docker build -t my-app . && docker run -p 8080:8080 my-app"
            result["setup_instructions"] = [
                "1. Install Rust via rustup.rs",
                "2. Run: cargo build --release",
                "3. Run: cargo run",
            ]

        else:
            result["notes"].append(
                "Could not detect a supported stack. Dockerfile generation requires "
                "Python, Node.js, Go, or Rust."
            )

        # ── docker-compose if DB detected ─────────────────────────────────
        if self._needs_database(config_files, self.repo_path):
            result["docker_compose"] = self._generate_compose(primary_lang)
            result["notes"].append(
                "Database dependency detected — docker-compose.yml generated with PostgreSQL."
            )

        return result

    # ── Helpers ───────────────────────────────────────────────────────────

    def _python_install(self, config_files: list) -> tuple[str, str]:
        if "requirements.txt" in config_files:
            return "pip install -r requirements.txt", "COPY requirements.txt ."
        if "pyproject.toml" in config_files:
            return "pip install .", "COPY pyproject.toml ."
        if "Pipfile" in config_files:
            return "pip install pipenv && pipenv install", "COPY Pipfile ."
        return "pip install .", "COPY . ."

    def _python_run_cmd(self, entry_points: list, config_files: list, docker: bool = True) -> str:
        # Detect FastAPI / uvicorn
        if any("main.py" in ep or "app.py" in ep for ep in entry_points):
            ep = next((ep for ep in entry_points if "main.py" in ep or "app.py" in ep), "main.py")
            module = ep.replace("/", ".").replace(".py", "")
            return f'["uvicorn", "{module}:app", "--host", "0.0.0.0", "--port", "8000"]' if docker \
                   else f"uvicorn {module}:app --reload"
        if entry_points:
            ep = entry_points[0].replace("/", ".").replace(".py", "")
            return f'["python", "-m", "{ep}"]' if docker else f"python -m {ep}"
        return '["python", "main.py"]' if docker else "python main.py"

    def _node_run_cmd(self, repo_path: Path) -> str:
        pkg = repo_path / "package.json"
        if pkg.exists():
            import json
            try:
                data = json.loads(pkg.read_text())
                scripts = data.get("scripts", {})
                if "start" in scripts:
                    return '["npm", "start"]'
                if "serve" in scripts:
                    return '["npm", "run", "serve"]'
            except Exception:
                pass
        return '["node", "index.js"]'

    def _needs_database(self, config_files: list, repo_path: Path) -> bool:
        """Detect if the project uses a database."""
        db_signals = ["sqlalchemy", "psycopg2", "asyncpg", "mongoose",
                      "prisma", "sequelize", "typeorm", "django"]
        try:
            for fname in ["requirements.txt", "package.json"]:
                fpath = repo_path / fname
                if fpath.exists():
                    content = fpath.read_text().lower()
                    if any(sig in content for sig in db_signals):
                        return True
        except Exception:
            pass
        return False

    def _generate_compose(self, lang: str) -> str:
        app_port = "8000" if lang == "python" else "3000"
        return f'''\
version: "3.9"
services:
  app:
    build: .
    ports:
      - "{app_port}:{app_port}"
    environment:
      - DATABASE_URL=postgresql://user:password@postgres:5432/appdb
    depends_on:
      postgres:
        condition: service_healthy

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: appdb
      POSTGRES_USER: user
      POSTGRES_PASSWORD: password
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user"]
      interval: 5s
      timeout: 5s
      retries: 5
'''
