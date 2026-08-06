"""Paramètres pour les tests automatisés."""
from __future__ import annotations

from .base import *  # noqa: F403

DEBUG = False
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
    }
}

CHANNEL_LAYERS = {
    "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"},
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

VZONE_SSL_BACKEND = "selfsigned"
VZONE_DB_PROVISION_MODE = "mock"
VZONE_PYTHON_PROVISION_MODE = "mock"
VZONE_NODE_PROVISION_MODE = "mock"
VZONE_PHP_PROVISION_MODE = "mock"
VZONE_GIT_PROVISION_MODE = "mock"
VZONE_DOCKER_PROVISION_MODE = "mock"
VZONE_BACKUP_PROVISION_MODE = "mock"
VZONE_FIREWALL_PROVISION_MODE = "mock"
VZONE_LINUX_USER_PROVISION = "mock"
VZONE_TERMINAL_FALLBACK_SAME_UID = True
VZONE_FTP_AUTH_SECRET = "test-ftp-secret"

REST_FRAMEWORK["DEFAULT_THROTTLE_CLASSES"] = ()  # noqa: F405
