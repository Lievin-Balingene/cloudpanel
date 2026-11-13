"""JWT auth AngaPanel — invalide les access tokens après reset / change password."""
from __future__ import annotations

import hashlib

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken


def password_fingerprint(user) -> str:  # type: ignore[no-untyped-def]
    """Empreinte du hash MDP Django — change à chaque set_password()."""
    raw = (getattr(user, "password", None) or "").encode("utf-8", errors="ignore")
    return hashlib.sha256(raw).hexdigest()[:24]


class VZoneJWTAuthentication(JWTAuthentication):
    """Rejette les access tokens émis avant un changement de mot de passe."""

    def get_user(self, validated_token):  # type: ignore[no-untyped-def]
        user = super().get_user(validated_token)
        claim = validated_token.get("pv")
        expected = password_fingerprint(user)
        # Absent ou différent → session émise avant set_password / reset
        if claim != expected:
            raise InvalidToken("Session invalidée (mot de passe modifié).")
        if not getattr(user, "is_active", True) or getattr(user, "is_suspended", False):
            raise InvalidToken("Compte indisponible.")
        return user
