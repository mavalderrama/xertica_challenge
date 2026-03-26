import os

from .base import *  # noqa: F401, F403

DEBUG = True

# In Docker Compose, POSTGRES_HOST=db. Locally, fall back to localhost.
DATABASES["default"]["HOST"] = os.environ.get("POSTGRES_HOST", "localhost")  # noqa: F405
