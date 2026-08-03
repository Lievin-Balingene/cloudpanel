"""Package racine V-zone Panel."""

from __future__ import annotations

from pathlib import Path

VERSION_FILE = Path(__file__).resolve().parents[2] / "VERSION"


def get_version() -> str:
    """Lit la version depuis le fichier VERSION à la racine du dépôt."""
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "0.0.0-dev"


__version__ = get_version()

# Charge l'app Celery dès l'import Django
from .celery import app as celery_app

__all__ = ("celery_app", "__version__", "get_version")
