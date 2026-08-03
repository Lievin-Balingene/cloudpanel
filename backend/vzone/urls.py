"""URL racine de l'API V-zone Panel."""
from __future__ import annotations

from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from apps.core.views import HealthCheckView, VersionView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", HealthCheckView.as_view(), name="health"),
    path("api/v1/version/", VersionView.as_view(), name="version"),
    path("api/v1/core/", include("apps.core.urls")),
    path("api/v1/auth/", include("apps.accounts.urls")),
    path("api/v1/packages/", include("apps.packages.urls")),
    path("api/v1/dns/", include("apps.dns.urls")),
    path("api/v1/dashboard/", include("apps.dashboard.urls")),
    path("api/v1/domains/", include("apps.domains.urls")),
    path("api/v1/files/", include("apps.files.urls")),
    path("api/v1/ftp/", include("apps.ftp.urls")),
    path("api/v1/email/", include("apps.email.urls")),
    path("api/v1/databases/", include("apps.databases.urls")),
    path("api/v1/python/", include("apps.python_apps.urls")),
    path("api/v1/node/", include("apps.node_apps.urls")),
    path("api/v1/php/", include("apps.php.urls")),
    path("api/v1/git/", include("apps.git_deploy.urls")),
    path("api/v1/docker/", include("apps.docker_mgmt.urls")),
    path("api/v1/backups/", include("apps.backups.urls")),
    path("api/v1/monitoring/", include("apps.monitoring.urls")),
    path("api/v1/firewall/", include("apps.firewall.urls")),
    path("api/v1/security/", include("apps.security.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path(
        "api/docs/",
        SpectacularSwaggerView.as_view(url_name="schema"),
        name="swagger-ui",
    ),
    path(
        "api/redoc/",
        SpectacularRedocView.as_view(url_name="schema"),
        name="redoc",
    ),
]
