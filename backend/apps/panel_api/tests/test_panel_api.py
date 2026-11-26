"""Jetons, WHM JSON API et UAPI."""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import AdminFactory, ResellerFactory, UserFactory
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
    assert response.status_code == 403
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
def test_suspend_then_unsuspend(api: APIClient):
    admin = AdminFactory()
    user = UserFactory()
    secret = _issue(api, admin, audience="whm")
    user_secret = _issue(api, user, audience="uapi")
    auth = {"HTTP_AUTHORIZATION": f"whm {admin.username}:{secret}"}

    suspended = api.post("/api/json-api/suspendacct", {"user": user.username}, format="json", **auth)
    assert suspended.status_code == 200, suspended.content
    assert suspended.json()["metadata"]["result"] == 1
    assert suspended.json()["data"]["suspended"] == 1
    user.refresh_from_db()
    assert user.is_suspended is True
    assert user.is_active is False

    blocked = api.get(
        "/api/execute/Variables/get_user_information",
        HTTP_AUTHORIZATION=f"Bearer {user_secret}",
    )
    assert blocked.status_code == 403

    restored = api.post("/api/json-api/unsuspendacct", {"user": user.username}, format="json", **auth)
    assert restored.status_code == 200, restored.content
    assert restored.json()["data"]["suspended"] == 0
    user.refresh_from_db()
    assert user.is_suspended is False
    assert user.is_active is True


@pytest.mark.django_db
def test_cannot_suspend_self_or_foreign_account(api: APIClient):
    admin = AdminFactory()
    reseller = ResellerFactory()
    own = UserFactory(parent=reseller)
    foreign = UserFactory()
    admin_secret = _issue(api, admin, audience="whm")
    reseller_secret = _issue(api, reseller, audience="whm")

    self_hit = api.post(
        "/api/json-api/suspendacct",
        {"user": admin.username},
        format="json",
        HTTP_AUTHORIZATION=f"whm {admin.username}:{admin_secret}",
    )
    assert self_hit.status_code == 400
    assert self_hit.json()["metadata"]["result"] == 0

    denied = api.post(
        "/api/json-api/suspendacct",
        {"user": foreign.username},
        format="json",
        HTTP_AUTHORIZATION=f"whm {reseller.username}:{reseller_secret}",
    )
    assert denied.status_code == 200
    assert denied.json()["metadata"]["result"] == 0
    foreign.refresh_from_db()
    assert foreign.is_suspended is False

    ok = api.post(
        "/api/json-api/suspendacct",
        {"user": own.username},
        format="json",
        HTTP_AUTHORIZATION=f"whm {reseller.username}:{reseller_secret}",
    )
    assert ok.status_code == 200, ok.content
    assert ok.json()["data"]["suspended"] == 1


@pytest.mark.django_db
def test_apirequest_blocks_token_mint_and_traversal(api: APIClient):
    admin = AdminFactory()
    secret = _issue(api, admin, audience="both")
    auth = {"HTTP_AUTHORIZATION": f"Bearer {secret}"}
    minted = api.post(
        "/api/json-api/apirequest",
        {"method": "POST", "path": "/api/v1/api-tokens/", "data": {"name": "escalade"}},
        format="json",
        **auth,
    )
    assert minted.status_code == 403
    escaped = api.post(
        "/api/json-api/apirequest",
        {"method": "GET", "path": "/api/v1/../../etc/passwd"},
        format="json",
        **auth,
    )
    assert escaped.status_code == 403


@pytest.mark.django_db
def test_token_in_query_string_is_rejected(api: APIClient):
    admin = AdminFactory()
    secret = _issue(api, admin, audience="whm")
    response = api.get(f"/api/json-api/version?api_token={secret}&api_user={admin.username}")
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
