"""Tests journaux compte / domaine."""
from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.account_logs import list_account_logs, tail_account_log
from apps.accounts.factories import AdminFactory, UserFactory
from apps.domains.models import Domain


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.mark.django_db
def test_list_account_logs_includes_domains(tmp_path, settings, monkeypatch):
    owner = UserFactory(username="loguser")
    Domain.objects.create(owner=owner, name="example.test", document_root=str(tmp_path / "public_html"))
    data = list_account_logs(owner)
    assert data["username"] == "loguser"
    assert len(data["domains"]) == 1
    assert data["domains"][0]["name"] == "example.test"
    assert len(data["domains"][0]["logs"]) >= 4


@pytest.mark.django_db
def test_tail_account_log_reads_file(tmp_path, settings, monkeypatch):
    owner = UserFactory(username="loguser2")
    Domain.objects.create(owner=owner, name="site.test", document_root=str(tmp_path / "htdocs"))
    nginx = tmp_path / "nginx"
    nginx.mkdir()
    log = nginx / "site.test.access.log"
    log.write_text("line-a\nline-b\nline-c\n", encoding="utf-8")

    import apps.accounts.account_logs as al

    def fake_candidates(domain_name: str):
        return [
            {
                "kind": "access",
                "engine": "nginx",
                "label": "Access",
                "domain": domain_name,
                "path": str(log),
                "exists": True,
                "size_bytes": log.stat().st_size,
                "modified_at": None,
            }
        ]

    monkeypatch.setattr(al, "_log_candidates", fake_candidates)
    monkeypatch.setattr(
        al,
        "_resolve_log_path",
        lambda owner, domain_name, kind: Path(log),
    )
    payload = tail_account_log(owner, domain_name="site.test", kind="access", lines=50)
    assert payload["exists"] is True
    assert payload["lines"][-1] == "line-c"


@pytest.mark.django_db
def test_logs_api_requires_scope(api: APIClient):
    admin = AdminFactory()
    owner = UserFactory(username="scoped")
    Domain.objects.create(owner=owner, name="scoped.test", document_root="/tmp/x")
    api.force_authenticate(user=admin)
    res = api.get(reverse("user-logs-list", kwargs={"pk": owner.pk}))
    assert res.status_code == 200
    assert res.json()["data"]["username"] == "scoped"
