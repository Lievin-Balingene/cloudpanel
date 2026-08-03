"""Tests domaines et SSL."""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import AdminFactory, UserFactory
from apps.domains.models import Domain, SslCertificate
from apps.domains.services import create_domain
from apps.domains.ssl_services import install_custom_certificate, issue_letsencrypt, issue_self_signed


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.mark.integration
@pytest.mark.django_db
def test_create_domain_creates_dns_zone(api: APIClient):
    admin = AdminFactory(password="TestPassword123!")
    api.force_authenticate(user=admin)
    response = api.post(
        reverse("domain-list"),
        {
            "name": "site-demo.test",
            "domain_type": "primary",
            "ipv4_address": "203.0.113.10",
        },
        format="json",
    )
    assert response.status_code == 201
    data = response.json()["data"]
    assert data["name"] == "site-demo.test"
    assert data["dns_zone_name"] == "site-demo.test"
    domain = Domain.objects.get(pk=data["id"])
    assert domain.dns_zone is not None
    assert domain.dns_zone.records.filter(record_type="A", name="@").exists()


@pytest.mark.integration
@pytest.mark.django_db
def test_subdomain_and_redirect(api: APIClient):
    admin = AdminFactory(password="TestPassword123!")
    api.force_authenticate(user=admin)
    parent = create_domain(
        name="parent-demo.test",
        owner=admin,
        ipv4_address="203.0.113.20",
    )
    sub = api.post(
        reverse("domain-subdomain-create"),
        {"label": "blog", "parent_id": parent.pk},
        format="json",
    )
    assert sub.status_code == 201
    assert sub.json()["data"]["name"] == "blog.parent-demo.test"
    assert sub.json()["data"]["domain_type"] == "subdomain"

    redirect = api.post(
        reverse("domain-redirect-list", kwargs={"domain_id": parent.pk}),
        {
            "source_path": "/old",
            "destination_url": "https://example.com/new",
            "redirect_type": "301",
        },
        format="json",
    )
    assert redirect.status_code == 201
    assert redirect.json()["data"]["source_path"] == "/old"


@pytest.mark.integration
@pytest.mark.django_db
def test_letsencrypt_issue(api: APIClient):
    admin = AdminFactory(password="TestPassword123!")
    api.force_authenticate(user=admin)
    domain = create_domain(name="ssl-demo.test", owner=admin, ipv4_address="203.0.113.30")
    response = api.post(
        reverse("domain-ssl-letsencrypt", kwargs={"domain_id": domain.pk}),
        {},
        format="json",
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "active"
    assert data["provider"] == "letsencrypt"
    assert data["has_private_key"] is True
    domain.refresh_from_db()
    assert domain.ssl.status == SslCertificate.Status.ACTIVE


@pytest.mark.integration
@pytest.mark.django_db
def test_custom_ssl_install():
    admin = AdminFactory()
    domain = create_domain(name="custom-ssl.test", owner=admin)
    material = issue_self_signed("custom-ssl.test")
    ssl = install_custom_certificate(
        domain,
        certificate_pem=material.certificate_pem,
        private_key_pem=material.private_key_pem,
        chain_pem=material.chain_pem,
    )
    assert ssl.status == SslCertificate.Status.ACTIVE
    assert ssl.provider == SslCertificate.Provider.CUSTOM


@pytest.mark.unit
@pytest.mark.django_db
def test_parked_domain_requires_parent():
    owner = UserFactory()
    parent = create_domain(name="main-park.test", owner=owner)
    parked = create_domain(
        name="parked-park.test",
        owner=owner,
        domain_type=Domain.DomainType.PARKED,
        parent=parent,
    )
    assert parked.parent_id == parent.pk


@pytest.mark.unit
@pytest.mark.django_db
def test_issue_letsencrypt_service():
    owner = UserFactory()
    domain = create_domain(name="le-service.test", owner=owner)
    ssl = issue_letsencrypt(domain)
    assert ssl.status == SslCertificate.Status.ACTIVE
    assert "BEGIN CERTIFICATE" in ssl.certificate_pem
