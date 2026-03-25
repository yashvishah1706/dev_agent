import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.core.config import settings
from app.core.job_store import job_store
from app.core.heartbeat import HeartbeatMonitor
from app.core.rate_limit import limiter, rate_limit_exceeded_handler
from app.core.logger import setup_logging, get_logger
from app.api.routes import router as jobs_router
from app.api.auth_routes import router as auth_router
from app.api.ws_routes import router as ws_router

setup_logging(level="INFO")
logger = get_logger(__name__)

heartbeat_monitor = HeartbeatMonitor(job_store)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Dev Agent Platform starting up")
    asyncio.create_task(heartbeat_monitor.start())
    yield
    heartbeat_monitor.stop()
    logger.info("Dev Agent Platform shut down")


app = FastAPI(
    title="Dev Agent Platform",
    description=(
        "Autonomous Developer Assistant — analyzes any GitHub repo with AI agents.\n\n"
        "**Auth:** POST `/api/v1/auth/token` with `username=admin` & `password=devagent123` "
        "to get a Bearer token, then click **Authorize** above."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ── Middleware ─────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ────────────────────────────────────────────────────────────────
app.include_router(auth_router, prefix="/api/v1")
app.include_router(jobs_router, prefix="/api/v1")
app.include_router(ws_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "version": "1.0.0"}
