import os

from .base import *  # noqa: F401, F403

DEBUG = False

DATABASES["default"].update(  # noqa: F405
    {
        "OPTIONS": {
            "sslmode": "require",
        }
    }
)

ALLOWED_HOSTS = os.environ.get("ALLOWED_HOSTS", "").split(",")
