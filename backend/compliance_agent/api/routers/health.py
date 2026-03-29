import logging

from asgiref.sync import sync_to_async
from fastapi import APIRouter
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


def _check_db() -> None:
    """Check DB connectivity using a throwaway connection (thread-safe)."""
    from django.db import connections

    conn = connections["default"]
    conn.ensure_connection()
    conn.close()


@router.get("/readiness")
async def readiness() -> JSONResponse:
    try:
        await sync_to_async(_check_db)()
        return JSONResponse({"status": "ready", "db": "connected"})
    except Exception as e:
        logger.error("Readiness check failed: %s", e, exc_info=True)
        return JSONResponse({"status": "not_ready", "db": str(e)}, status_code=503)
