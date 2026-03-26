from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"})


@router.get("/readiness")
async def readiness() -> JSONResponse:
    try:
        from django.db import connection

        connection.ensure_connection()
        return JSONResponse({"status": "ready", "db": "connected"})
    except Exception as e:
        return JSONResponse(
            {"status": "not_ready", "db": str(e)}, status_code=503
        )
