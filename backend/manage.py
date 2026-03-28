#!/usr/bin/env python
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.local")

if __name__ == "__main__":
    from django.core import management

    management.execute_from_command_line()
