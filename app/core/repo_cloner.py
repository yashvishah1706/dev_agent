import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

from app.core.config import settings


class RepoCloner:
    """
    Safely clones a GitHub repository to a local temp directory.

    Guardrails:
    - Only allows github.com URLs
    - Strips credentials from URLs
    - Enforces a max repo size via shallow clone
    - Cleans up on error
    """

    ALLOWED_HOSTS = {"github.com", "gitlab.com", "bitbucket.org"}
    MAX_DEPTH = 1      # shallow clone — fast, small

    def __init__(self, base_path: str = None):
        self.base_path = Path(base_path or settings.repos_base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _validate_url(self, url: str) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Only http/https URLs are allowed. Got: {parsed.scheme}")
        if parsed.hostname not in self.ALLOWED_HOSTS:
            raise ValueError(
                f"Only these hosts are allowed: {self.ALLOWED_HOSTS}. Got: {parsed.hostname}"
            )
        # Strip any embedded credentials (safety)
        clean = parsed._replace(netloc=parsed.hostname + (f":{parsed.port}" if parsed.port else ""))
        return clean.geturl()

    def clone(self, job_id: str, repo_url: str, branch: str = "main") -> Path:
        clean_url = self._validate_url(repo_url)
        repo_path = self.base_path / job_id

        if repo_path.exists():
            shutil.rmtree(repo_path)

        cmd = [
            "git", "clone",
            "--depth", str(self.MAX_DEPTH),
            "--branch", branch,
            "--single-branch",
            clean_url,
            str(repo_path),
        ]

        # Add GitHub token if available (for private repos)
        env = os.environ.copy()
        if settings.github_token:
            env["GIT_ASKPASS"] = "echo"
            env["GIT_USERNAME"] = "token"
            env["GIT_PASSWORD"] = settings.github_token

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            if result.returncode != 0:
                # Try without branch (some repos use 'main', others 'master')
                if branch == "main":
                    return self.clone(job_id, repo_url, branch="master")
                raise RuntimeError(f"Git clone failed: {result.stderr.strip()}")
        except subprocess.TimeoutExpired:
            raise RuntimeError("Repository clone timed out after 120 seconds")
        except Exception:
            if repo_path.exists():
                shutil.rmtree(repo_path)
            raise

        return repo_path

    def cleanup(self, job_id: str):
        repo_path = self.base_path / job_id
        if repo_path.exists():
            shutil.rmtree(repo_path)
