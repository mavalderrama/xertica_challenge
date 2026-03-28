import os

import django


def bootstrap_django(settings_module: str | None = None) -> None:
    module = settings_module or os.environ.get(
        "DJANGO_SETTINGS_MODULE", "config.settings.local"
    )
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", module)
    django.setup()
