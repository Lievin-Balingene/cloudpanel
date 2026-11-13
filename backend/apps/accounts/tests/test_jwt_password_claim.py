"""Access JWT invalidés après changement de mot de passe."""
from __future__ import annotations

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.accounts.authentication import VZoneJWTAuthentication, password_fingerprint
from apps.accounts.factories import UserFactory
from apps.accounts.services import issue_tokens


@pytest.mark.django_db
def test_access_token_rejected_after_password_change():
    user = UserFactory(username="jwtuser")
    tokens = issue_tokens(user)
    access = AccessToken(tokens["access"])
    assert access.get("pv") == password_fingerprint(user)

    auth = VZoneJWTAuthentication()
    # Avant changement → OK
    assert auth.get_user(access).pk == user.pk

    user.set_password("BrandNewPass99!")
    user.save(update_fields=["password"])

    from rest_framework_simplejwt.exceptions import InvalidToken

    with pytest.raises(InvalidToken):
        auth.get_user(access)


@pytest.mark.django_db
def test_me_endpoint_401_after_password_reset(api_client=None):
    api = APIClient()
    user = UserFactory(username="jwtreload")
    tokens = issue_tokens(user)
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
    ok = api.get("/api/v1/auth/me/")
    assert ok.status_code == 200

    user.set_password("AnotherNewPass99!")
    user.save(update_fields=["password"])
    blocked = api.get("/api/v1/auth/me/")
    assert blocked.status_code in {401, 403}
