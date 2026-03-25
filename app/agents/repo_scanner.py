import os
from pathlib import Path
from collections import defaultdict
from typing import Any

from app.agents.base import BaseAgent


# File extensions → language mapping
LANG_MAP = {
    ".py": "Python", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".jsx": "JavaScript", ".java": "Java",
    ".go": "Go", ".rs": "Rust", ".rb": "Ruby", ".php": "PHP",
    ".cs": "C#", ".cpp": "C++", ".c": "C", ".swift": "Swift",
    ".kt": "Kotlin", ".scala": "Scala", ".vue": "Vue",
    ".html": "HTML", ".css": "CSS", ".scss": "SCSS",
    ".sh": "Shell", ".yaml": "YAML", ".yml": "YAML",
    ".json": "JSON", ".md": "Markdown", ".sql": "SQL",
}

# Dirs to skip always
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv",
    "env", "dist", "build", ".next", ".nuxt", "coverage",
    ".pytest_cache", ".mypy_cache", "vendor",
}

# Config files that tell us about the stack
STACK_SIGNALS = {
    "requirements.txt": "Python (pip)",
    "Pipfile": "Python (pipenv)",
    "pyproject.toml": "Python (pyproject)",
    "package.json": "Node.js",
    "go.mod": "Go",
    "Cargo.toml": "Rust",
    "pom.xml": "Java (Maven)",
    "build.gradle": "Java (Gradle)",
    "Gemfile": "Ruby",
    "composer.json": "PHP",
    "Dockerfile": "Docker",
    "docker-compose.yml": "Docker Compose",
    "docker-compose.yaml": "Docker Compose",
    ".env.example": "Env config",
    "Makefile": "Make",
    "terraform.tf": "Terraform",
    "kubernetes.yaml": "Kubernetes",
}


class RepoScannerAgent(BaseAgent):
    """
    Agent 1 — Repo Scanner

    Walks the repository and produces:
    - File tree (top 2 levels)
    - Language breakdown
    - Stack detection (what tech does this project use?)
    - Entry point detection
    - Total stats (files, lines of code)
    """

    name = "repo_scanner"
    timeout = 60

    async def run(self) -> Any:
        stats = {
            "total_files": 0,
            "total_lines": 0,
            "languages": defaultdict(int),
            "detected_stack": [],
            "config_files": [],
            "entry_points": [],
            "file_tree": [],
            "top_level_dirs": [],
        }

        # Detect stack from known config files
        for fname, label in STACK_SIGNALS.items():
            if (self.repo_path / fname).exists():
                stats["detected_stack"].append(label)
                stats["config_files"].append(fname)

        # Walk the repo
        for root, dirs, files in os.walk(self.repo_path):
            # Prune skip dirs in-place (affects os.walk)
            dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

            rel_root = Path(root).relative_to(self.repo_path)
            depth = len(rel_root.parts)

            # Build top-2-level tree
            if depth <= 2:
                for fname in files:
                    stats["file_tree"].append(str(rel_root / fname))

            if depth == 1:
                stats["top_level_dirs"] = list(dirs)

            for fname in files:
                fpath = Path(root) / fname
                ext = Path(fname).suffix.lower()
                lang = LANG_MAP.get(ext)

                stats["total_files"] += 1

                if lang:
                    stats["languages"][lang] += 1

                # Count lines for code files
                if lang and lang not in ("JSON", "YAML", "Markdown"):
                    try:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            lines = sum(1 for _ in f)
                            stats["total_lines"] += lines
                    except Exception:
                        pass

                # Detect common entry points
                if fname in ("main.py", "app.py", "server.py", "index.js",
                              "index.ts", "main.go", "main.rs", "app.js"):
                    stats["entry_points"].append(str(rel_root / fname))

        # Convert defaultdict to regular dict for JSON serialization
        stats["languages"] = dict(stats["languages"])

        # Sort languages by file count
        stats["languages"] = dict(
            sorted(stats["languages"].items(), key=lambda x: x[1], reverse=True)
        )

        # Deduplicate detected stack
        stats["detected_stack"] = list(dict.fromkeys(stats["detected_stack"]))

        return stats
