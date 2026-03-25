"""
WebSocket Live Streaming
------------------------
Connect to ws://localhost:8000/api/v1/ws/jobs/{job_id}

The server pushes a JSON message every second with the current job state:
  {
    "job_id": "...",
    "status": "running",
    "agents": {
      "repo_scanner":        {"status": "completed", "last_heartbeat": "..."},
      "dependency_analyzer": {"status": "running",   "last_heartbeat": "..."}
    },
    "result": null | {...}   <- populated when status == "completed"
  }

The connection closes automatically when the job reaches "completed" or "failed".

Auth: pass the JWT token as a query param:
  ws://localhost:8000/api/v1/ws/jobs/{job_id}?token=<your_jwt>
"""

import asyncio
import json
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from jose import JWTError, jwt

from app.core.job_store import job_store
from app.core.auth import SECRET_KEY, ALGORITHM
from app.core.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()


def _serialize(obj):
    """JSON-serialize datetime objects."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


async def _authenticate_ws(token: str) -> bool:
    """Validate the JWT token passed as a query param."""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload.get("sub") is not None
    except JWTError:
        return False


@router.websocket("/ws/jobs/{job_id}")
async def job_progress_ws(
    websocket: WebSocket,
    job_id: str,
    token: str = Query(..., description="JWT access token"),
):
    """
    Stream live job progress over WebSocket.
    Pushes updates every second until the job completes or fails.
    """
    # Authenticate before accepting the connection
    if not await _authenticate_ws(token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Check job exists
    job = await job_store.get(job_id)
    if not job:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    logger.info("WebSocket connected", extra={"job_id": job_id})

    try:
        while True:
            job = await job_store.get(job_id)
            if not job:
                break

            payload = {
                "job_id": job.id,
                "status": job.status.value,
                "agents": {
                    name: {
                        "status": agent.status,
                        "last_heartbeat": agent.last_heartbeat,
                        "error": agent.error,
                    }
                    for name, agent in job.agents.items()
                },
                "result": job.result if job.status.value == "completed" else None,
                "error": job.error,
            }

            await websocket.send_text(json.dumps(payload, default=_serialize))

            # Stop streaming once terminal state is reached
            if job.status.value in ("completed", "failed"):
                break

            await asyncio.sleep(1)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected by client", extra={"job_id": job_id})
    except Exception as e:
        logger.error("WebSocket error", extra={"job_id": job_id, "error": str(e)})
    finally:
        try:
            await websocket.close()
        except Exception:
            pass
