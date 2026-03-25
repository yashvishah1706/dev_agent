"""
Tests for Phase 1 upgrades:
  - JWT authentication
  - Rate limiting (logic layer)
  - WebSocket streaming
  - Structured logging
  - PgJobStore schema compatibility
"""

import pytest
import json
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import timedelta


# ── Auth tests ─────────────────────────────────────────────────────────────

class TestAuth:
    def test_create_and_decode_token(self):
        from app.core.auth import create_access_token, SECRET_KEY, ALGORITHM
        from jose import jwt

        token = create_access_token({"sub": "admin", "role": "admin"})
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        assert payload["sub"] == "admin"
        assert payload["role"] == "admin"
        assert "exp" in payload

    def test_token_expires(self):
        from app.core.auth import create_access_token, SECRET_KEY, ALGORITHM
        from jose import jwt, JWTError

        # Token that expired 1 second ago
        token = create_access_token(
            {"sub": "admin"},
            expires_delta=timedelta(seconds=-1)
        )
        with pytest.raises(JWTError):
            jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

    def test_authenticate_valid_user(self):
        from app.core.auth import authenticate_user

        user = authenticate_user("admin", "devagent123")
        assert user is not None
        assert user.username == "admin"
        assert user.role == "admin"

    def test_authenticate_wrong_password(self):
        from app.core.auth import authenticate_user

        user = authenticate_user("admin", "wrongpassword")
        assert user is None

    def test_authenticate_nonexistent_user(self):
        from app.core.auth import authenticate_user

        user = authenticate_user("nobody", "password")
        assert user is None

    @pytest.mark.asyncio
    async def test_get_current_user_valid_token(self):
        from app.core.auth import create_access_token, get_current_user

        token = create_access_token({"sub": "admin", "role": "admin"})
        user = await get_current_user(token)
        assert user.username == "admin"

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self):
        from app.core.auth import get_current_user
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user("not-a-valid-token")
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_current_user_missing_sub(self):
        from app.core.auth import create_access_token, get_current_user, SECRET_KEY, ALGORITHM
        from jose import jwt
        from fastapi import HTTPException

        # Token with no 'sub' field
        token = create_access_token({"role": "admin"})
        # Manually strip the sub
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        del payload["sub"]
        bad_token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(bad_token)
        assert exc_info.value.status_code == 401


# ── Structured logging tests ───────────────────────────────────────────────

class TestStructuredLogging:
    def test_json_formatter_produces_valid_json(self):
        import logging
        import io
        from app.core.logger import JSONFormatter

        handler = logging.StreamHandler(io.StringIO())
        handler.setFormatter(JSONFormatter())

        logger = logging.getLogger("test_logger")
        logger.handlers = [handler]
        logger.setLevel(logging.DEBUG)
        logger.info("test message")

        output = handler.stream.getvalue()
        parsed = json.loads(output.strip())

        assert parsed["level"] == "INFO"
        assert parsed["message"] == "test message"
        assert "timestamp" in parsed
        assert "logger" in parsed

    def test_extra_fields_included_in_log(self):
        import logging
        import io
        from app.core.logger import JSONFormatter

        handler = logging.StreamHandler(io.StringIO())
        handler.setFormatter(JSONFormatter())

        logger = logging.getLogger("test_extra")
        logger.handlers = [handler]
        logger.setLevel(logging.DEBUG)
        logger.info("job started", extra={"job_id": "abc-123", "agent": "repo_scanner"})

        output = handler.stream.getvalue()
        parsed = json.loads(output.strip())

        assert parsed["job_id"] == "abc-123"
        assert parsed["agent"] == "repo_scanner"

    def test_get_logger_returns_named_logger(self):
        from app.core.logger import get_logger
        import logging

        logger = get_logger("my.module")
        assert isinstance(logger, logging.Logger)
        assert logger.name == "my.module"


# ── Rate limiter tests ─────────────────────────────────────────────────────

class TestRateLimiter:
    def test_limiter_is_configured(self):
        from app.core.rate_limit import limiter
        assert limiter is not None

    def test_rate_limit_exceeded_handler_returns_429(self):
        """Verify the custom handler sets the right status code."""
        from app.core.rate_limit import rate_limit_exceeded_handler
        from slowapi.errors import RateLimitExceeded
        from unittest.mock import MagicMock
        import asyncio

        mock_request = MagicMock()
        mock_exc = MagicMock(spec=RateLimitExceeded)
        mock_exc.limit = "5/minute"

        response = asyncio.get_event_loop().run_until_complete(
            rate_limit_exceeded_handler(mock_request, mock_exc)
        )
        assert response.status_code == 429


# ── WebSocket authentication tests ────────────────────────────────────────

class TestWebSocketAuth:
    @pytest.mark.asyncio
    async def test_valid_token_authenticates(self):
        from app.api.ws_routes import _authenticate_ws
        from app.core.auth import create_access_token

        token = create_access_token({"sub": "admin", "role": "admin"})
        result = await _authenticate_ws(token)
        assert result is True

    @pytest.mark.asyncio
    async def test_invalid_token_rejected(self):
        from app.api.ws_routes import _authenticate_ws

        result = await _authenticate_ws("totally-fake-token")
        assert result is False

    @pytest.mark.asyncio
    async def test_expired_token_rejected(self):
        from app.api.ws_routes import _authenticate_ws
        from app.core.auth import create_access_token

        expired = create_access_token(
            {"sub": "admin"},
            expires_delta=timedelta(seconds=-10)
        )
        result = await _authenticate_ws(expired)
        assert result is False


# ── Job store tests ────────────────────────────────────────────────────────

class TestJobStoreIntegration:
    @pytest.mark.asyncio
    async def test_full_job_lifecycle(self):
        from app.core.job_store import JobStore
        from app.schemas.job import JobStatus, AgentStatus

        store = JobStore()

        # Create
        job = await store.create("lifecycle-test", "https://github.com/user/repo")
        assert job.status == JobStatus.PENDING

        # Move to running
        await store.update_status("lifecycle-test", JobStatus.RUNNING)
        job = await store.get("lifecycle-test")
        assert job.status == JobStatus.RUNNING

        # Agent update
        agent = AgentStatus(name="repo_scanner", status="running")
        await store.update_agent("lifecycle-test", "repo_scanner", agent)
        job = await store.get("lifecycle-test")
        assert "repo_scanner" in job.agents

        # Heartbeat
        await store.heartbeat("lifecycle-test", "repo_scanner")
        job = await store.get("lifecycle-test")
        assert job.agents["repo_scanner"].last_heartbeat is not None

        # Set result
        await store.set_result("lifecycle-test", {"summary": {"primary_language": "Python"}})

        # Complete
        await store.update_status("lifecycle-test", JobStatus.COMPLETED)
        job = await store.get("lifecycle-test")
        assert job.status == JobStatus.COMPLETED
        assert job.result["summary"]["primary_language"] == "Python"

    @pytest.mark.asyncio
    async def test_failed_job_stores_error(self):
        from app.core.job_store import JobStore
        from app.schemas.job import JobStatus

        store = JobStore()
        await store.create("fail-test", "https://github.com/user/repo")
        await store.update_status("fail-test", JobStatus.FAILED, error="Clone timed out")

        job = await store.get("fail-test")
        assert job.status == JobStatus.FAILED
        assert job.error == "Clone timed out"


# ── Repo cloner guardrail tests ────────────────────────────────────────────

class TestRepoCloner:
    def test_allows_github(self, tmp_path):
        from app.core.repo_cloner import RepoCloner
        c = RepoCloner(base_path=str(tmp_path))
        url = c._validate_url("https://github.com/user/repo")
        assert "github.com" in url

    def test_allows_gitlab(self, tmp_path):
        from app.core.repo_cloner import RepoCloner
        c = RepoCloner(base_path=str(tmp_path))
        url = c._validate_url("https://gitlab.com/user/repo")
        assert "gitlab.com" in url

    def test_allows_bitbucket(self, tmp_path):
        from app.core.repo_cloner import RepoCloner
        c = RepoCloner(base_path=str(tmp_path))
        url = c._validate_url("https://bitbucket.org/user/repo")
        assert "bitbucket.org" in url

    def test_blocks_arbitrary_domain(self, tmp_path):
        from app.core.repo_cloner import RepoCloner
        c = RepoCloner(base_path=str(tmp_path))
        with pytest.raises(ValueError, match="Only these hosts"):
            c._validate_url("https://evil.com/steal/data")

    def test_blocks_ftp(self, tmp_path):
        from app.core.repo_cloner import RepoCloner
        c = RepoCloner(base_path=str(tmp_path))
        with pytest.raises(ValueError, match="Only http/https"):
            c._validate_url("ftp://github.com/user/repo")

    def test_strips_embedded_credentials(self, tmp_path):
        from app.core.repo_cloner import RepoCloner
        c = RepoCloner(base_path=str(tmp_path))
        url = c._validate_url("https://user:s3cr3t@github.com/user/repo")
        assert "s3cr3t" not in url
        assert "user:" not in url
