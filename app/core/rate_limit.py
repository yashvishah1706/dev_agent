"""
Rate Limiting
-------------
Uses slowapi (Starlette-compatible wrapper around limits).

Limits applied:
  POST /analyze    → 5 requests / minute  per IP  (expensive — clones a repo)
  GET  /jobs/{id}  → 60 requests / minute per IP  (cheap polling)
  GET  /jobs       → 30 requests / minute per IP

Usage in a route:
    @router.post("/analyze")
    @limiter.limit("5/minute")
    async def analyze_repo(request: Request, ...):
        ...

The `request: Request` parameter is REQUIRED by slowapi — it reads the client IP from it.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi import Request
from fastapi.responses import JSONResponse


# Key function: use client IP as the rate limit key
limiter = Limiter(key_func=get_remote_address)


async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    """Custom response when a client exceeds their rate limit."""
    return JSONResponse(
        status_code=429,
        content={
            "error": "rate_limit_exceeded",
            "detail": f"Too many requests. Limit: {exc.limit}",
            "retry_after": "60 seconds",
        },
        headers={"Retry-After": "60"},
    )
