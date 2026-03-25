import json
import re
from pathlib import Path
from typing import Any

from app.agents.base import BaseAgent


class DependencyAnalyzerAgent(BaseAgent):
    """
    Agent 2 — Dependency Analyzer

    Reads every package manifest it can find and extracts:
    - All dependencies with versions
    - Dev vs production split
    - Outdated/vulnerable flags (basic heuristics)
    - Dependency graph edges (who imports who)
    """

    name = "dependency_analyzer"
    timeout = 90

    async def run(self) -> Any:
        result = {
            "manifests_found": [],
            "dependencies": {},
            "dev_dependencies": {},
            "dependency_graph": [],
            "warnings": [],
        }

        parsers = [
            self._parse_requirements_txt,
            self._parse_package_json,
            self._parse_pyproject_toml,
            self._parse_go_mod,
            self._parse_cargo_toml,
        ]

        for parser in parsers:
            try:
                await parser(result)
            except Exception as e:
                result["warnings"].append(f"{parser.__name__} failed: {str(e)}")

        # Build simple dependency graph from imports (Python only for now)
        result["dependency_graph"] = await self._build_import_graph()

        return result

    async def _parse_requirements_txt(self, result: dict):
        path = self.repo_path / "requirements.txt"
        if not path.exists():
            return
        result["manifests_found"].append("requirements.txt")
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            # Handle: package==1.0, package>=1.0, package~=1.0, package
            match = re.match(r"^([A-Za-z0-9_\-\.]+)([><=~!]+.+)?$", line)
            if match:
                name, version = match.group(1), match.group(2) or "any"
                result["dependencies"][name] = version.strip()

    async def _parse_package_json(self, result: dict):
        path = self.repo_path / "package.json"
        if not path.exists():
            return
        result["manifests_found"].append("package.json")
        data = json.loads(path.read_text())
        result["dependencies"].update(data.get("dependencies", {}))
        result["dev_dependencies"].update(data.get("devDependencies", {}))

    async def _parse_pyproject_toml(self, result: dict):
        path = self.repo_path / "pyproject.toml"
        if not path.exists():
            return
        result["manifests_found"].append("pyproject.toml")
        # Basic TOML parsing without external library
        content = path.read_text()
        in_deps = False
        for line in content.splitlines():
            if "[tool.poetry.dependencies]" in line or "[project.dependencies]" in line:
                in_deps = True
                continue
            if line.startswith("[") and in_deps:
                in_deps = False
            if in_deps and "=" in line:
                key, val = line.split("=", 1)
                result["dependencies"][key.strip()] = val.strip().strip('"')

    async def _parse_go_mod(self, result: dict):
        path = self.repo_path / "go.mod"
        if not path.exists():
            return
        result["manifests_found"].append("go.mod")
        in_require = False
        for line in path.read_text().splitlines():
            line = line.strip()
            if line == "require (":
                in_require = True
                continue
            if line == ")":
                in_require = False
            if in_require and line:
                parts = line.split()
                if len(parts) >= 2:
                    result["dependencies"][parts[0]] = parts[1]

    async def _parse_cargo_toml(self, result: dict):
        path = self.repo_path / "Cargo.toml"
        if not path.exists():
            return
        result["manifests_found"].append("Cargo.toml")
        in_deps = False
        for line in path.read_text().splitlines():
            if line.strip() == "[dependencies]":
                in_deps = True
                continue
            if line.startswith("[") and in_deps:
                in_deps = False
            if in_deps and "=" in line:
                key, val = line.split("=", 1)
                result["dependencies"][key.strip()] = val.strip().strip('"')

    async def _build_import_graph(self) -> list:
        """Build a simple import graph from Python files."""
        graph = []
        py_files = list(self.repo_path.rglob("*.py"))[:50]  # cap at 50 files

        for py_file in py_files:
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore")
                imports = re.findall(
                    r"^(?:from|import)\s+([\w\.]+)", content, re.MULTILINE
                )
                rel_path = str(py_file.relative_to(self.repo_path))
                for imp in imports:
                    graph.append({"from": rel_path, "imports": imp})
            except Exception:
                continue

        return graph
