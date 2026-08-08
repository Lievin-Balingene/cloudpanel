"""Tests sans nginx : pas d'en-tête X-Vzone-Portal obligatoire."""
from __future__ import annotations

from .base import *  # noqa: F403

DEBUG = True

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

VZONE_PORTAL_REQUIRE_HEADER = False

# Channels en mémoire si Redis indisponible en dev unitaire
if env_bool("VZONE_CHANNELS_INMEMORY", False):  # noqa: F405
    CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
    }
