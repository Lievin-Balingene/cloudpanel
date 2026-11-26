"""Jetons, WHM JSON API et UAPI."""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import AdminFactory, UserFactory
from apps.domains.models import Domain


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def _issue(api: APIClient, user, **payload):  # type: ignore[no-untyped-def]
    api.force_authenticate(user=user)
    body = {"name": "ci", "audience": "both", "scopes": ["*"], **payload}
    response = api.post(reverse("api-token-list"), body, format="json")
    api.force_authenticate(user=None)
    assert response.status_code == 201, response.content
    return response.json()["data"]["token"]


@pytest.mark.django_db
def test_whm_version_with_token(api: APIClient):
    admin = AdminFactory()
    secret = _issue(api, admin, audience="whm")
    response = api.get(
        "/api/json-api/version",
        HTTP_AUTHORIZATION=f"whm {admin.username}:{secret}",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["metadata"]["result"] == 1
    assert body["metadata"]["command"] == "version"
    assert body["data"]["version"]


@pytest.mark.django_db
def test_uapi_lists_own_domain(api: APIClient):
    user = UserFactory()
    Domain.objects.create(name="exemple-api.test", owner=user, domain_type=Domain.DomainType.PRIMARY)
    secret = _issue(api, user, audience="uapi")
    response = api.get(
        "/api/execute/DomainInfo/list_domains",
        HTTP_AUTHORIZATION=f"cpanel {user.username}:{secret}",
    )
    assert response.status_code == 200
    body = response.json()
    assert body["result"]["status"] == 1
    assert body["result"]["data"]["main_domain"] == "exemple-api.test"


@pytest.mark.django_db
def test_apirequest_runs_panel_route_as_token_user(api: APIClient):
    admin = AdminFactory()
    secret = _issue(api, admin, audience="whm")
    response = api.post(
        "/api/json-api/apirequest",
        {"method": "GET", "path": "/api/v1/auth/me/"},
        format="json",
        HTTP_AUTHORIZATION=f"whm {admin.username}:{secret}",
    )
    assert response.status_code == 200, response.content
    body = response.json()
    assert body["metadata"]["result"] == 1
    assert body["data"]["body"]["data"]["username"] == admin.username


@pytest.mark.django_db
def test_apirequest_rejects_login_route(api: APIClient):
    admin = AdminFactory()
    secret = _issue(api, admin, audience="both")
    response = api.post(
        "/api/json-api/apirequest",
        {"method": "POST", "path": "/api/v1/auth/login/", "data": {}},
        format="json",
        HTTP_AUTHORIZATION=f"Bearer {secret}",
    )
    assert response.status_code == 400
    assert response.json()["metadata"]["result"] == 0


@pytest.mark.django_db
def test_whm_cpanel_runs_uapi_on_account(api: APIClient):
    admin = AdminFactory()
    user = UserFactory()
    Domain.objects.create(name="via-cpanel.test", owner=user, domain_type=Domain.DomainType.PRIMARY)
    secret = _issue(api, admin, audience="whm")
    response = api.get(
        "/api/json-api/cpanel",
        {
            "cpanel_jsonapi_user": user.username,
            "cpanel_jsonapi_module": "DomainInfo",
            "cpanel_jsonapi_func": "list_domains",
        },
        HTTP_AUTHORIZATION=f"whm {admin.username}:{secret}",
    )
    assert response.status_code == 200, response.content
    assert response.json()["data"]["main_domain"] == "via-cpanel.test"


@pytest.mark.django_db
def test_client_token_cannot_call_whm(api: APIClient):
    user = UserFactory()
    secret = _issue(api, user, audience="uapi")
    response = api.get(
        "/api/json-api/listaccts",
        HTTP_AUTHORIZATION=f"whm {user.username}:{secret}",
    )
    assert response.status_code == 403
    assert response.json()["metadata"]["result"] == 0


@pytest.mark.django_db
def test_scope_blocks_other_functions(api: APIClient):
    user = UserFactory()
    secret = _issue(api, user, audience="uapi", scopes=["Variables.get_user_information"])
    denied = api.get(
        "/api/execute/DomainInfo/list_domains",
        HTTP_AUTHORIZATION=f"anga {user.username}:{secret}",
    )
    assert denied.status_code == 403
    ok = api.get(
        "/api/execute/Variables/get_user_information",
        HTTP_AUTHORIZATION=f"Bearer {secret}",
    )
    assert ok.status_code == 200
    assert ok.json()["result"]["data"]["user"] == user.username


@pytest.mark.django_db
def test_revoked_token_rejected(api: APIClient):
    admin = AdminFactory()
    api.force_authenticate(user=admin)
    created = api.post(reverse("api-token-list"), {"name": "tmp", "audience": "whm"}, format="json")
    secret = created.json()["data"]["token"]
    token_id = created.json()["data"]["id"]
    api.delete(reverse("api-token-detail", args=[token_id]))
    api.force_authenticate(user=None)
    response = api.get(
        "/api/json-api/version",
        HTTP_AUTHORIZATION=f"whm {admin.username}:{secret}",
    )
    assert response.status_code == 401


@pytest.mark.django_db
def test_client_cannot_mint_whm_token(api: APIClient):
    user = UserFactory()
    api.force_authenticate(user=user)
    response = api.post(
        reverse("api-token-list"),
        {"name": "rootish", "audience": "whm"},
        format="json",
    )
    assert response.status_code == 403
