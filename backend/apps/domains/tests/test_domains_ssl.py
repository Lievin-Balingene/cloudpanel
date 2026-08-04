"""Tests domaines et SSL."""
from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import AdminFactory, UserFactory
from apps.domains.models import Domain, SslCertificate
from apps.domains.services import create_domain
from apps.domains.ssl_services import install_custom_certificate, issue_letsencrypt, issue_self_signed
from apps.domains.vhosts import resolve_domain_backend, render_vhost


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.mark.integration
@pytest.mark.django_db
def test_create_domain_creates_dns_zone(api: APIClient, tmp_path, settings):
    settings.VZONE_HOME_ROOT = tmp_path / "homes"
    settings.VZONE_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_NGINX_DOMAINS_DIR = str(tmp_path / "nginx")
    settings.VZONE_WEB_STACK = "mock"

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
    # Primary → ~/public_html (home admin)
    assert domain.document_root.endswith("public_html")
    assert Path(domain.document_root).is_dir()
    assert (Path(domain.document_root) / "index.html").is_file()


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

    parent.refresh_from_db()
    assert parent.dns_zone_id
    assert parent.dns_zone.records.filter(record_type="A", name="blog", content="203.0.113.20").exists()

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


@pytest.mark.unit
@pytest.mark.django_db
def test_subdomain_dns_without_parent_fk(tmp_path, settings):
    """Même si parent.dns_zone FK est vide, le sous-domaine doit créer l'A."""
    settings.VZONE_DNS_ZONES_DIR = str(tmp_path / "zones")
    settings.VZONE_DNS_ZONES_CONF = str(tmp_path / "zones.conf")
    settings.VZONE_DNS_RELOAD_FLAG = str(tmp_path / "reload.requested")
    settings.VZONE_PUBLIC_IP = "203.0.113.88"
    settings.VZONE_HOME_ROOT = tmp_path / "homes"
    settings.VZONE_NGINX_DOMAINS_DIR = str(tmp_path / "nginx")
    Path(settings.VZONE_NGINX_DOMAINS_DIR).mkdir(parents=True, exist_ok=True)

    admin = AdminFactory(password="TestPassword123!")
    parent = create_domain(name="apex-heal.test", owner=admin, ipv4_address="203.0.113.88")
    parent.dns_zone = None
    parent.save(update_fields=["dns_zone"])

    sub = create_domain(
        name="app.apex-heal.test",
        owner=admin,
        domain_type=Domain.DomainType.SUBDOMAIN,
        parent=parent,
        create_dns_zone=False,
    )
    parent.refresh_from_db()
    assert parent.dns_zone_id
    assert parent.dns_zone.records.filter(record_type="A", name="app").exists()
    assert sub.dns_zone_id == parent.dns_zone_id
    assert "public_html" in sub.document_root.replace("\\", "/")
    assert sub.document_root.replace("\\", "/").endswith("/public_html/app")
    assert Path(sub.document_root).is_dir()
    assert (Path(sub.document_root) / "index.html").is_file()



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


@pytest.mark.unit
@pytest.mark.django_db
def test_addon_docroot_and_app_priority(tmp_path, settings):
    settings.VZONE_HOME_ROOT = tmp_path / "homes"
    settings.VZONE_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_NGINX_DOMAINS_DIR = str(tmp_path / "nginx")
    settings.VZONE_WEB_STACK = "mock"

    owner = UserFactory(username="siteowner")
    primary = create_domain(
        name="primary-app.test", owner=owner, domain_type=Domain.DomainType.PRIMARY
    )
    assert primary.document_root.replace("\\", "/").endswith("/siteowner/public_html")

    addon = create_domain(
        name="addon-app.test", owner=owner, domain_type=Domain.DomainType.ADDON
    )
    assert "domains/addon-app.test/public_html" in addon.document_root.replace("\\", "/")
    assert Path(addon.document_root).is_dir()

    backend = resolve_domain_backend(addon)
    assert backend.mode == "static"
    conf = render_vhost(addon, backend)
    assert "root " in conf
    assert "addon-app.test" in conf

    from apps.python_apps.models import PythonApp

    app = PythonApp.objects.create(
        owner=owner,
        name="django1",
        port=8123,
        status=PythonApp.Status.RUNNING,
        domain_name="addon-app.test",
        is_active=True,
    )
    backend2 = resolve_domain_backend(addon)
    assert backend2.mode == "proxy"
    assert backend2.port == 8123
    conf2 = render_vhost(addon, backend2)
    assert "proxy_pass http://127.0.0.1:8123" in conf2
    assert app.name in backend2.app_label
