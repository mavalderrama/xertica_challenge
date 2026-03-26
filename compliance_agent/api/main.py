from contextlib import asynccontextmanager

from fastapi import FastAPI

from compliance_agent.api.routers import alerts, health


@asynccontextmanager
async def lifespan(app: FastAPI):
    from compliance_agent.bootstrap import bootstrap_django

    bootstrap_django()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="Compliance AI API",
        description="Multi-agent fraud alert processing system",
        version="1.0.0",
        lifespan=lifespan,
    )
    app.include_router(health.router)
    app.include_router(alerts.router)
    return app


app = create_app()
