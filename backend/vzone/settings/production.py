"""Paramètres de production."""
from __future__ import annotations

from .base import *  # noqa: F403

DEBUG = False

SECURE_SSL_REDIRECT = env_bool("VZONE_SECURE_SSL_REDIRECT", True)  # noqa: F405
SECURE_HSTS_SECONDS = int(env("VZONE_HSTS_SECONDS", "31536000"))  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("VZONE_EMAIL_HOST", "localhost")  # noqa: F405
EMAIL_PORT = int(env("VZONE_EMAIL_PORT", "25"))  # noqa: F405
EMAIL_USE_TLS = env_bool("VZONE_EMAIL_USE_TLS", False)  # noqa: F405
DEFAULT_FROM_EMAIL = env("VZONE_DEFAULT_FROM_EMAIL", "noreply@localhost")  # noqa: F405

if SECRET_KEY.startswith("dev-insecure"):  # noqa: F405
    raise RuntimeError("VZONE_SECRET_KEY invalide en production.")
