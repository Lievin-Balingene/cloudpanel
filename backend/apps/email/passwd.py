"""Hachage mots de passe compatible Dovecot (SHA512-CRYPT / $6$)."""
from __future__ import annotations

_crypt = None
_METHOD = None
try:
    import crypt as _crypt_mod

    _crypt = _crypt_mod
    _METHOD = getattr(_crypt_mod, "METHOD_SHA512", None)
except ImportError:  # Windows / Python 3.13+
    pass


def hash_password(raw: str) -> str:
    """Produit un hash $6$salt$hash (sans rounds=) pour Dovecot passwd-file."""
    if _crypt is not None and _METHOD is not None:
        return _crypt.crypt(raw, _crypt.mksalt(_METHOD))
    from passlib.hash import sha512_crypt

    # rounds=5000 (défaut SHA512-CRYPT) → format classique $6$salt$hash
    return sha512_crypt.using(rounds=5000).hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    if not hashed or not raw:
        return False
    cleaned = hashed.removeprefix("{SHA512-CRYPT}")
    if _crypt is not None and cleaned.startswith("$"):
        try:
            return _crypt.crypt(raw, cleaned) == cleaned
        except OSError:
            pass
    try:
        from passlib.hash import sha512_crypt

        return sha512_crypt.verify(raw, cleaned)
    except Exception:  # noqa: BLE001
        return False


def dovecot_password_field(hashed: str) -> str:
    """Champ password pour passwd-file Dovecot."""
    if not hashed:
        return ""
    if hashed.startswith("{"):
        return hashed
    if hashed.startswith("$6$"):
        return f"{{SHA512-CRYPT}}{hashed}"
    return hashed
