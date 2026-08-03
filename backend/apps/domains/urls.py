from __future__ import annotations

from django.urls import path

from apps.domains.views import (
    DomainDetailView,
    DomainListCreateView,
    DomainRedirectDetailView,
    DomainRedirectListCreateView,
    SslInstallCustomView,
    SslIssueLetsEncryptView,
    SslStatusView,
    SubdomainCreateView,
)

urlpatterns = [
    path("", DomainListCreateView.as_view(), name="domain-list"),
    path("subdomains/", SubdomainCreateView.as_view(), name="domain-subdomain-create"),
    path("<int:pk>/", DomainDetailView.as_view(), name="domain-detail"),
    path(
        "<int:domain_id>/redirects/",
        DomainRedirectListCreateView.as_view(),
        name="domain-redirect-list",
    ),
    path(
        "<int:domain_id>/redirects/<int:pk>/",
        DomainRedirectDetailView.as_view(),
        name="domain-redirect-detail",
    ),
    path(
        "<int:domain_id>/ssl/",
        SslStatusView.as_view(),
        name="domain-ssl-status",
    ),
    path(
        "<int:domain_id>/ssl/letsencrypt/",
        SslIssueLetsEncryptView.as_view(),
        name="domain-ssl-letsencrypt",
    ),
    path(
        "<int:domain_id>/ssl/custom/",
        SslInstallCustomView.as_view(),
        name="domain-ssl-custom",
    ),
]
