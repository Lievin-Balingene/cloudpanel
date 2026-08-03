"""Hachage mots de passe compatible Dovecot (SHA512-CRYPT / $6$)."""
from __future__ import annotations

from typing import Final

# passlib est la référence portable ; crypt (libc) en secours sur Linux.
try:
    from passlib.hash import sha512_crypt as _sha512_crypt

    def hash_password(raw: str) -> str:
        return _sha512_crypt.using(rounds=5000).hash(raw)

    def verify_password(raw: str, hashed: str) -> bool:
        if not hashed:
            return False
        # Accepte {SHA512-CRYPT}$6$… ou $6$… seul
        cleaned = hashed.removeprefix("{SHA512-CRYPT}")
        try:
            return _sha512_crypt.verify(raw, cleaned)
        except (ValueError, TypeError):
            return False

except ImportError:  # pragma: no cover
    import crypt

    _METHOD: Final = getattr(crypt, "METHOD_SHA512", None)

    def hash_password(raw: str) -> str:
        if _METHOD is None:
            salt = crypt.mksalt(crypt.METHOD_CRYPT)  # type: ignore[attr-defined]
            return crypt.crypt(raw, salt)
        return crypt.crypt(raw, _METHOD)

    def verify_password(raw: str, hashed: str) -> bool:
        if not hashed:
            return False
        cleaned = hashed.removeprefix("{SHA512-CRYPT}")
        try:
            return crypt.crypt(raw, cleaned) == cleaned
        except OSError:
            return False


def dovecot_password_field(hashed: str) -> str:
    """Préfixe optionnel pour passwd-file Dovecot."""
    if hashed.startswith("{") or hashed.startswith("$"):
        if hashed.startswith("$6$"):
            return f"{{SHA512-CRYPT}}{hashed}"
        return hashed
    return hashed
