"""Paramètres de production."""
from __future__ import annotations

from .base import *  # noqa: F403

DEBUG = False

SECURE_SSL_REDIRECT = env_bool("VZONE_SECURE_SSL_REDIRECT", False)  # noqa: F405
SECURE_HSTS_SECONDS = int(env("VZONE_HSTS_SECONDS", "0"))  # noqa: F405
SECURE_HSTS_INCLUDE_SUBDOMAINS = SECURE_HSTS_SECONDS > 0
SECURE_HSTS_PRELOAD = SECURE_HSTS_SECONDS > 0
# En HTTP (sans TLS), les cookies Secure bloqueraient session/CSRF admin.
_ssl = SECURE_SSL_REDIRECT or env_bool("VZONE_FORCE_SECURE_COOKIES", False)  # noqa: F405
SESSION_COOKIE_SECURE = _ssl
CSRF_COOKIE_SECURE = _ssl
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

CSRF_TRUSTED_ORIGINS = env_list(  # noqa: F405
    "VZONE_CSRF_TRUSTED_ORIGINS",
    ",".join(f"http://{h}" for h in ALLOWED_HOSTS if h not in {"*", "localhost", "127.0.0.1"}),  # noqa: F405
)

EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("VZONE_EMAIL_HOST", "localhost")  # noqa: F405
EMAIL_PORT = int(env("VZONE_EMAIL_PORT", "25"))  # noqa: F405
EMAIL_USE_TLS = env_bool("VZONE_EMAIL_USE_TLS", False)  # noqa: F405
DEFAULT_FROM_EMAIL = env("VZONE_DEFAULT_FROM_EMAIL", "noreply@localhost")  # noqa: F405

if SECRET_KEY.startswith("dev-insecure"):  # noqa: F405
    raise RuntimeError("VZONE_SECRET_KEY invalide en production.")
