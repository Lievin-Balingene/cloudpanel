"""Paramètres de base partagés (tous les environnements)."""
from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

from vzone import __version__

BASE_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = BASE_DIR.parent

for _dotenv_path in (REPO_ROOT / ".env", BASE_DIR / ".env"):
    try:
        load_dotenv(_dotenv_path)
    except OSError:
        # En prod, .env peut être un symlink root:vzone — ignorer si illisible.
        pass


def env(key: str, default: str | None = None) -> str:
    value = os.environ.get(key, default)
    if value is None:
        raise RuntimeError(f"Variable d'environnement manquante: {key}")
    return value


def env_bool(key: str, default: bool = False) -> bool:
    raw = os.environ.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_list(key: str, default: str = "") -> list[str]:
    raw = os.environ.get(key, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


def env_int(key: str, default: int = 0) -> int:
    raw = os.environ.get(key)
    if raw is None or raw == "":
        return default
    return int(raw)

SECRET_KEY = env("VZONE_SECRET_KEY", "dev-insecure-change-me")
DEBUG = env_bool("VZONE_DEBUG", False)
ALLOWED_HOSTS = env_list("VZONE_ALLOWED_HOSTS", "localhost,127.0.0.1")

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "django_filters",
    "drf_spectacular",
    "channels",
    "django_celery_beat",
    # V-zone modules
    "apps.core",
    "apps.accounts",
    "apps.packages",
    "apps.dns",
    "apps.dashboard",
    "apps.domains",
    "apps.files",
    "apps.ftp",
    "apps.cron",
    "apps.email",
    "apps.databases",
    "apps.python_apps",
    "apps.node_apps",
    "apps.php",
    "apps.git_deploy",
    "apps.docker_mgmt",
    "apps.backups",
    "apps.monitoring",
    "apps.firewall",
    "apps.security",
    "apps.wordpress",
    "apps.kubernetes",
    "apps.server_setup",
    "apps.transfer",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    "apps.core.middleware.AuditMiddleware",
    "apps.security.middleware.ForcePasswordChangeMiddleware",
]

ROOT_URLCONF = "vzone.urls"
ASGI_APPLICATION = "vzone.asgi.application"
WSGI_APPLICATION = "vzone.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("VZONE_DB_NAME", "vzone"),
        "USER": env("VZONE_DB_USER", "vzone"),
        "PASSWORD": env("VZONE_DB_PASSWORD", "vzone"),
        "HOST": env("VZONE_DB_HOST", "127.0.0.1"),
        "PORT": env("VZONE_DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
        "OPTIONS": {"connect_timeout": 10},
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(env("VZONE_DATA_ROOT", str(BASE_DIR / "media"))) / "uploads"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REDIS_URL = env("VZONE_REDIS_URL", "redis://127.0.0.1:6379/0")
CELERY_BROKER_URL = env("VZONE_CELERY_BROKER_URL", "redis://127.0.0.1:6379/1")
CELERY_RESULT_BACKEND = CELERY_BROKER_URL
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 30 * 60
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [env("VZONE_CHANNELS_REDIS_URL", "redis://127.0.0.1:6379/2")],
        },
    }
}

CORS_ALLOWED_ORIGINS = env_list(
    "VZONE_CORS_ORIGINS",
    "http://localhost:5173,http://127.0.0.1:5173",
)
CORS_ALLOW_CREDENTIALS = True

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.StandardPagination",
    "PAGE_SIZE": 25,
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/minute",
        "user": "600/minute",
        "auth": "10/minute",
    },
    "EXCEPTION_HANDLER": "apps.core.exceptions.vzone_exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=int(env("VZONE_JWT_ACCESS_MINUTES", "30"))
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(env("VZONE_JWT_REFRESH_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
}

SPECTACULAR_SETTINGS = {
    "TITLE": "V-zone Panel API",
    "DESCRIPTION": "API REST du panneau de contrôle d'hébergement V-zone Panel.",
    "VERSION": __version__,
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[{asctime}] {levelname} {name} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django.request": {"level": "WARNING", "propagate": True},
        "apps": {"level": "INFO", "propagate": True},
        "vzone": {"level": "INFO", "propagate": True},
    },
}

# Chemins système V-zone
VZONE_VERSION = env("VZONE_VERSION", __version__)
VZONE_DATA_ROOT = Path(env("VZONE_DATA_ROOT", str(BASE_DIR / ".data")))
VZONE_LOG_ROOT = Path(env("VZONE_LOG_ROOT", str(BASE_DIR / ".logs")))
VZONE_HOME_ROOT = Path(env("VZONE_HOME_ROOT", str(BASE_DIR / ".homes")))
VZONE_FRONTEND_URL = env("VZONE_FRONTEND_URL", "http://localhost:5173")
VZONE_NGINX_DOMAINS_DIR = env(
    "VZONE_NGINX_DOMAINS_DIR",
    str(VZONE_DATA_ROOT / "nginx" / "domains"),
)
VZONE_DNS_ZONES_DIR = env(
    "VZONE_DNS_ZONES_DIR",
    str(Path("/var/lib/vzone/named/zones")),
)
VZONE_DNS_ZONES_CONF = env(
    "VZONE_DNS_ZONES_CONF",
    str(Path("/var/lib/vzone/named/zones.conf")),
)
VZONE_DNS_RELOAD_FLAG = env(
    "VZONE_DNS_RELOAD_FLAG",
    str(Path("/var/lib/vzone/named/reload.requested")),
)
VZONE_WEB_STACK = env("VZONE_WEB_STACK", "auto")  # auto | live | mock

# OpenLiteSpeed (moteur optionnel derrière Nginx — sites PHP/WordPress)
VZONE_OLS_ENABLED = env_bool("VZONE_OLS_ENABLED", False)
VZONE_OLS_LISTEN = env("VZONE_OLS_LISTEN", "127.0.0.1:8088")
VZONE_OLS_ROOT = env("VZONE_OLS_ROOT", "/usr/local/lsws")
VZONE_OLS_VHOSTS_DIR = env(
    "VZONE_OLS_VHOSTS_DIR",
    str(VZONE_DATA_ROOT / "ols" / "vhosts"),
)
VZONE_OLS_VHCONF_DIR = env(
    "VZONE_OLS_VHCONF_DIR",
    str(VZONE_DATA_ROOT / "ols" / "vhconf"),
)
VZONE_OLS_MAPS_FILE = env(
    "VZONE_OLS_MAPS_FILE",
    str(VZONE_DATA_ROOT / "ols" / "vzone-vhosts.conf"),
)

# Modules activés (extensible à l'installation)
VZONE_ENABLED_MODULES = env_list(
    "VZONE_ENABLED_MODULES",
    "core,accounts,packages,dns,dashboard,domains,files,ftp,cron,email,databases,python_apps,node_apps,php,git_deploy,docker_mgmt,backups,monitoring,firewall,security,wordpress,kubernetes,server_setup,transfer",
)

# Email / webmail
VZONE_WEBMAIL_URL = env("VZONE_WEBMAIL_URL", "/webmail/")
VZONE_MAIL_MAPS_DIR = env("VZONE_MAIL_MAPS_DIR", str(VZONE_DATA_ROOT / "mail" / "maps"))
# Maildirs virtuels (Dovecot vmail) — PAS sous /home (sinon Roundcube refuse le login)
VZONE_MAIL_HOME_ROOT = env("VZONE_MAIL_HOME_ROOT", "cpanel")  # cpanel → ~/mail ; ou chemin absolu
VZONE_MAIL_STACK = env("VZONE_MAIL_STACK", "auto")  # auto | live | mock
VZONE_MAIL_PUBLIC_IP = env("VZONE_MAIL_PUBLIC_IP", "")
VZONE_PUBLIC_IP = env("VZONE_PUBLIC_IP", VZONE_MAIL_PUBLIC_IP)
VZONE_ROUNDCUBE_SSO_DIR = env(
    "VZONE_ROUNDCUBE_SSO_DIR",
    str(VZONE_DATA_ROOT / "roundcube" / "sso"),
)
VZONE_ROUNDCUBE_IMAP_HOST = env("VZONE_ROUNDCUBE_IMAP_HOST", "127.0.0.1:143")
VZONE_ROUNDCUBE_ROOT = env("VZONE_ROUNDCUBE_ROOT", "/opt/vzone/roundcube")


# Bases de données hébergées (provisionnement)
VZONE_DB_PROVISION_MODE = env("VZONE_DB_PROVISION_MODE", "auto")  # auto | live | mock
VZONE_DB_MAPS_DIR = env("VZONE_DB_MAPS_DIR", str(VZONE_DATA_ROOT / "databases"))
VZONE_PHPMYADMIN_URL = env("VZONE_PHPMYADMIN_URL", "/phpmyadmin/")
VZONE_PGADMIN_URL = env("VZONE_PGADMIN_URL", "/pgadmin/")
VZONE_PHPMYADMIN_SSO_DIR = env(
    "VZONE_PHPMYADMIN_SSO_DIR",
    str(VZONE_DATA_ROOT / "phpmyadmin" / "sso"),
)
VZONE_MYSQL_HOST = env("VZONE_MYSQL_HOST", "")
VZONE_MYSQL_PORT = env_int("VZONE_MYSQL_PORT", 3306)
VZONE_MYSQL_ADMIN_USER = env("VZONE_MYSQL_ADMIN_USER", "")
VZONE_MYSQL_ADMIN_PASSWORD = env("VZONE_MYSQL_ADMIN_PASSWORD", "")
VZONE_PG_HOST = env("VZONE_PG_HOST", "")
VZONE_PG_PORT = env_int("VZONE_PG_PORT", 5432)
VZONE_PG_ADMIN_USER = env("VZONE_PG_ADMIN_USER", "")
VZONE_PG_ADMIN_PASSWORD = env("VZONE_PG_ADMIN_PASSWORD", "")
VZONE_PG_ADMIN_DB = env("VZONE_PG_ADMIN_DB", "postgres")

# Applications Python
VZONE_PYTHON_PROVISION_MODE = env("VZONE_PYTHON_PROVISION_MODE", "auto")  # auto | live | mock
VZONE_PYTHON_CONFIG_DIR = env("VZONE_PYTHON_CONFIG_DIR", str(VZONE_DATA_ROOT / "python_apps"))
VZONE_PYTHON_PORT_BASE = env_int("VZONE_PYTHON_PORT_BASE", 8100)
VZONE_PYTHON_BIN = env("VZONE_PYTHON_BIN", "")

# Applications Node.js
VZONE_NODE_PROVISION_MODE = env("VZONE_NODE_PROVISION_MODE", "auto")  # auto | live | mock
VZONE_NODE_CONFIG_DIR = env("VZONE_NODE_CONFIG_DIR", str(VZONE_DATA_ROOT / "node_apps"))
VZONE_NODE_PORT_BASE = env_int("VZONE_NODE_PORT_BASE", 9100)
VZONE_NODE_BIN = env("VZONE_NODE_BIN", "")
VZONE_NPM_BIN = env("VZONE_NPM_BIN", "")

# PHP multi-version
VZONE_PHP_PROVISION_MODE = env("VZONE_PHP_PROVISION_MODE", "auto")  # auto | live | mock
VZONE_PHP_CONFIG_DIR = env("VZONE_PHP_CONFIG_DIR", str(VZONE_DATA_ROOT / "php"))

# WordPress (wp-cli)
VZONE_WORDPRESS_PROVISION_MODE = env("VZONE_WORDPRESS_PROVISION_MODE", "auto")  # auto | live | mock
VZONE_WP_CLI = env("VZONE_WP_CLI", "/usr/local/bin/wp")

# Kubernetes
VZONE_K8S_PROVISION_MODE = env("VZONE_K8S_PROVISION_MODE", "auto")  # auto | live | mock
VZONE_KUBECTL_BIN = env("VZONE_KUBECTL_BIN", "kubectl")

# Git Deploy
VZONE_GIT_PROVISION_MODE = env("VZONE_GIT_PROVISION_MODE", "auto")  # auto | live | mock
VZONE_GIT_CONFIG_DIR = env("VZONE_GIT_CONFIG_DIR", str(VZONE_DATA_ROOT / "git"))
VZONE_GIT_BIN = env("VZONE_GIT_BIN", "")
VZONE_GIT_MAX_REPOS = env_int("VZONE_GIT_MAX_REPOS", 20)

# Docker
VZONE_DOCKER_PROVISION_MODE = env("VZONE_DOCKER_PROVISION_MODE", "auto")  # auto | live | mock
VZONE_DOCKER_CONFIG_DIR = env("VZONE_DOCKER_CONFIG_DIR", str(VZONE_DATA_ROOT / "docker"))
VZONE_DOCKER_BIN = env("VZONE_DOCKER_BIN", "")

# Backups
VZONE_BACKUP_PROVISION_MODE = env("VZONE_BACKUP_PROVISION_MODE", "auto")  # auto | live | mock
VZONE_BACKUP_DIR = env("VZONE_BACKUP_DIR", str(VZONE_DATA_ROOT / "backups"))
VZONE_BACKUP_MAX = env_int("VZONE_BACKUP_MAX", 10)

# Monitoring & alertes
VZONE_ALERT_COOLDOWN_MINUTES = env_int("VZONE_ALERT_COOLDOWN_MINUTES", 30)
VZONE_ALERT_DEFAULT_RECIPIENTS = env("VZONE_ALERT_DEFAULT_RECIPIENTS", "")

# Firewall / Fail2Ban
VZONE_FIREWALL_PROVISION_MODE = env("VZONE_FIREWALL_PROVISION_MODE", "auto")  # auto | live | mock
VZONE_FIREWALL_CONFIG_DIR = env("VZONE_FIREWALL_CONFIG_DIR", str(VZONE_DATA_ROOT / "firewall"))
VZONE_IPTABLES_BIN = env("VZONE_IPTABLES_BIN", "")
VZONE_FAIL2BAN_BIN = env("VZONE_FAIL2BAN_BIN", "")

# Sécurité avancée (panel)
VZONE_SECURITY_LOCKOUT_MAX_ATTEMPTS = env_int("VZONE_SECURITY_LOCKOUT_MAX_ATTEMPTS", 5)
VZONE_SECURITY_LOCKOUT_WINDOW_MINUTES = env_int("VZONE_SECURITY_LOCKOUT_WINDOW_MINUTES", 15)
VZONE_SECURITY_LOCKOUT_DURATION_MINUTES = env_int("VZONE_SECURITY_LOCKOUT_DURATION_MINUTES", 30)

# SSL: auto (certbot si dispo, sinon self-signed en DEBUG), certbot, selfsigned
VZONE_SSL_BACKEND = env("VZONE_SSL_BACKEND", "auto")
VZONE_ACME_WEBROOT = env("VZONE_ACME_WEBROOT", str(VZONE_DATA_ROOT / "acme"))
# Hostnames qui doivent servir le panel (SPA) plutôt que public_html
VZONE_PANEL_HOSTNAMES = env("VZONE_PANEL_HOSTNAMES", "")
VZONE_ROOT = env("VZONE_ROOT", "/opt/vzone")

# FTP
VZONE_FTP_VIRTUAL_USERS_FILE = env(
    "VZONE_FTP_VIRTUAL_USERS_FILE",
    str(VZONE_DATA_ROOT / "ftp" / "virtual_users"),
)
VZONE_FTP_AUTH_SECRET = env("VZONE_FTP_AUTH_SECRET", "")
VZONE_CRON_JOBS_DIR = env("VZONE_CRON_JOBS_DIR", str(VZONE_DATA_ROOT / "cron" / "jobs"))
VZONE_CRON_PROVISION_MODE = env("VZONE_CRON_PROVISION_MODE", "auto")  # auto|live|mock
VZONE_CRON_RUN_USER = env("VZONE_CRON_RUN_USER", "vzone")


# Uploads File Manager (multipart + chunks)
VZONE_MAX_UPLOAD_BYTES = env_int("VZONE_MAX_UPLOAD_BYTES", 5 * 1024 * 1024 * 1024)
DATA_UPLOAD_MAX_MEMORY_SIZE = env_int("VZONE_DATA_UPLOAD_MAX_MEMORY", 10 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = env_int("VZONE_FILE_UPLOAD_MAX_MEMORY", 10 * 1024 * 1024)
DATA_UPLOAD_MAX_NUMBER_FIELDS = env_int("VZONE_DATA_UPLOAD_MAX_FIELDS", 2000)
FILE_UPLOAD_TEMP_DIR = env("VZONE_FILE_UPLOAD_TEMP_DIR", "") or None

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True
