from unittest.mock import AsyncMock, patch

import pytest

# ── Repo Scanner tests ─────────────────────────────────────────────────────


class TestRepoScannerAgent:
    @pytest.mark.asyncio
    async def test_scans_python_project(self, tmp_path):
        """Scanner detects Python files and requirements.txt"""
        from app.agents.repo_scanner import RepoScannerAgent

        # Create a fake Python project
        (tmp_path / "main.py").write_text("print('hello')\n" * 10)
        (tmp_path / "utils.py").write_text("def foo(): pass\n" * 5)
        (tmp_path / "requirements.txt").write_text("fastapi==0.115.0\n")
        (tmp_path / "README.md").write_text("# My Project")

        agent = RepoScannerAgent(job_id="test-job", repo_path=tmp_path)

        with (
            patch.object(agent, "_set_status", new_callable=AsyncMock),
            patch.object(agent, "_heartbeat_loop", new_callable=AsyncMock),
        ):
            result = await agent.run()

        assert result["total_files"] == 4
        assert "Python" in result["languages"]
        assert "Markdown" in result["languages"]
        assert "requirements.txt" in result["config_files"]
        assert "Python (pip)" in result["detected_stack"]
        assert "main.py" in " ".join(result["entry_points"])

    @pytest.mark.asyncio
    async def test_skips_node_modules(self, tmp_path):
        """Scanner must skip node_modules entirely"""
        from app.agents.repo_scanner import RepoScannerAgent

        (tmp_path / "index.js").write_text("console.log('hi')")
        node_mods = tmp_path / "node_modules" / "some-pkg"
        node_mods.mkdir(parents=True)
        (node_mods / "index.js").write_text("// vendor")

        agent = RepoScannerAgent(job_id="test-job", repo_path=tmp_path)

        with (
            patch.object(agent, "_set_status", new_callable=AsyncMock),
            patch.object(agent, "_heartbeat_loop", new_callable=AsyncMock),
        ):
            result = await agent.run()

        # Should only find the root index.js
        assert result["total_files"] == 1

    @pytest.mark.asyncio
    async def test_detects_node_stack(self, tmp_path):
        """Scanner detects Node.js stack from package.json"""
        from app.agents.repo_scanner import RepoScannerAgent

        (tmp_path / "package.json").write_text('{"name": "my-app"}')
        (tmp_path / "index.js").write_text("module.exports = {}")

        agent = RepoScannerAgent(job_id="test-job", repo_path=tmp_path)

        with (
            patch.object(agent, "_set_status", new_callable=AsyncMock),
            patch.object(agent, "_heartbeat_loop", new_callable=AsyncMock),
        ):
            result = await agent.run()

        assert "Node.js" in result["detected_stack"]


# ── Dependency Analyzer tests ──────────────────────────────────────────────


class TestDependencyAnalyzerAgent:
    @pytest.mark.asyncio
    async def test_parses_requirements_txt(self, tmp_path):
        from app.agents.dependency_analyzer import DependencyAnalyzerAgent

        (tmp_path / "requirements.txt").write_text(
            "fastapi==0.115.0\n"
            "uvicorn>=0.30.0\n"
            "pydantic~=2.9\n"
            "# this is a comment\n"
            "\n"
            "httpx\n"
        )

        agent = DependencyAnalyzerAgent(job_id="test-job", repo_path=tmp_path)

        with (
            patch.object(agent, "_set_status", new_callable=AsyncMock),
            patch.object(agent, "_heartbeat_loop", new_callable=AsyncMock),
        ):
            result = await agent.run()

        assert "fastapi" in result["dependencies"]
        assert result["dependencies"]["fastapi"] == "==0.115.0"
        assert "uvicorn" in result["dependencies"]
        assert "pydantic" in result["dependencies"]
        assert "httpx" in result["dependencies"]
        assert "requirements.txt" in result["manifests_found"]

    @pytest.mark.asyncio
    async def test_parses_package_json(self, tmp_path):
        import json

        from app.agents.dependency_analyzer import DependencyAnalyzerAgent

        pkg = {
            "name": "my-app",
            "dependencies": {"react": "^18.0.0", "axios": "^1.6.0"},
            "devDependencies": {"jest": "^29.0.0", "typescript": "^5.0.0"},
        }
        (tmp_path / "package.json").write_text(json.dumps(pkg))

        agent = DependencyAnalyzerAgent(job_id="test-job", repo_path=tmp_path)

        with (
            patch.object(agent, "_set_status", new_callable=AsyncMock),
            patch.object(agent, "_heartbeat_loop", new_callable=AsyncMock),
        ):
            result = await agent.run()

        assert "react" in result["dependencies"]
        assert "jest" in result["dev_dependencies"]
        assert "package.json" in result["manifests_found"]

    @pytest.mark.asyncio
    async def test_empty_repo_no_crash(self, tmp_path):
        from app.agents.dependency_analyzer import DependencyAnalyzerAgent

        agent = DependencyAnalyzerAgent(job_id="test-job", repo_path=tmp_path)

        with (
            patch.object(agent, "_set_status", new_callable=AsyncMock),
            patch.object(agent, "_heartbeat_loop", new_callable=AsyncMock),
        ):
            result = await agent.run()

        assert result["manifests_found"] == []
        assert result["dependencies"] == {}


# ── Repo Cloner tests ──────────────────────────────────────────────────────


class TestRepoCloner:
    def test_rejects_non_github_urls(self, tmp_path):
        from app.core.repo_cloner import RepoCloner

        cloner = RepoCloner(base_path=str(tmp_path))

        with pytest.raises(ValueError, match="Only these hosts"):
            cloner._validate_url("https://evil.com/user/repo")

    def test_rejects_non_https(self, tmp_path):
        from app.core.repo_cloner import RepoCloner

        cloner = RepoCloner(base_path=str(tmp_path))

        with pytest.raises(ValueError, match="Only http/https"):
            cloner._validate_url("ftp://github.com/user/repo")

    def test_accepts_valid_github_url(self, tmp_path):
        from app.core.repo_cloner import RepoCloner

        cloner = RepoCloner(base_path=str(tmp_path))

        url = cloner._validate_url("https://github.com/tiangolo/fastapi")
        assert "github.com" in url

    def test_strips_credentials_from_url(self, tmp_path):
        from app.core.repo_cloner import RepoCloner

        cloner = RepoCloner(base_path=str(tmp_path))

        url = cloner._validate_url("https://user:password@github.com/user/repo")
        assert "password" not in url
        assert "user:" not in url


# ── Job Store tests ────────────────────────────────────────────────────────


class TestJobStore:
    @pytest.mark.asyncio
    async def test_create_and_get_job(self):
        from app.core.job_store import JobStore
        from app.schemas.job import JobStatus

        store = JobStore()
        job = await store.create("job-1", "https://github.com/user/repo")

        assert job.id == "job-1"
        assert job.status == JobStatus.PENDING

        fetched = await store.get("job-1")
        assert fetched is not None
        assert fetched.id == "job-1"

    @pytest.mark.asyncio
    async def test_update_status(self):
        from app.core.job_store import JobStore
        from app.schemas.job import JobStatus

        store = JobStore()
        await store.create("job-2", "https://github.com/user/repo")
        await store.update_status("job-2", JobStatus.RUNNING)

        job = await store.get("job-2")
        assert job.status == JobStatus.RUNNING

    @pytest.mark.asyncio
    async def test_returns_none_for_missing_job(self):
        from app.core.job_store import JobStore

        store = JobStore()
        result = await store.get("nonexistent")
        assert result is None
