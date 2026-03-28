import logging
import os
import sys

import django
from dotenv import load_dotenv
from fastapi import FastAPI

_backend_dir = os.path.normpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "../..")
)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")
django.setup()

# Routers import Django models transitively, so they must come after django.setup()
from compliance_agent.api.routers import alerts, health  # noqa: E402


def create_app() -> FastAPI:
    app = FastAPI(
        title="Compliance AI API",
        description="Multi-agent fraud alert processing system",
        version="1.0.0",
    )
    app.include_router(health.router)
    app.include_router(alerts.router)
    return app


app = create_app()
