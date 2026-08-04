"""Client API WHM distant (Transfer Tool)."""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from apps.core.exceptions import VZoneAPIException


class WhmRemoteClient:
    def __init__(
        self,
        host: str,
        *,
        port: int = 2087,
        user: str = "root",
        token: str = "",
        insecure_ssl: bool = False,
        timeout: int = 120,
    ) -> None:
        self.host = host.strip().rstrip("/")
        if self.host.startswith("https://"):
            self.host = self.host[len("https://") :]
        if self.host.startswith("http://"):
            self.host = self.host[len("http://") :]
        self.port = int(port or 2087)
        self.user = user.strip() or "root"
        self.token = token.strip()
        self.insecure_ssl = insecure_ssl
        self.timeout = timeout

    def _url(self, function: str, params: dict[str, Any] | None = None) -> str:
        q = {"api.version": 1}
        if params:
            q.update(params)
        query = urllib.parse.urlencode(q)
        return f"https://{self.host}:{self.port}/json-api/{function}?{query}"

    def _request(self, function: str, params: dict[str, Any] | None = None) -> dict:
        if not self.token:
            raise VZoneAPIException(detail="Token WHM requis.", code="whm_token_required", status_code=400)
        url = self._url(function, params)
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"whm {self.user}:{self.token}")
        context = None
        if self.insecure_ssl:
            context = ssl._create_unverified_context()  # noqa: S323
        try:
            with urllib.request.urlopen(req, timeout=self.timeout, context=context) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:800]
            raise VZoneAPIException(
                detail=f"WHM HTTP {exc.code}: {body or exc.reason}",
                code="whm_http_error",
                status_code=502,
            ) from exc
        except Exception as exc:  # noqa: BLE001
            raise VZoneAPIException(
                detail=f"Connexion WHM impossible: {exc}",
                code="whm_connection_failed",
                status_code=502,
            ) from exc
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise VZoneAPIException(
                detail="Réponse WHM non JSON.",
                code="whm_bad_response",
                status_code=502,
            ) from exc
        return data if isinstance(data, dict) else {"data": data}

    def version(self) -> dict:
        data = self._request("version")
        return data

    def list_accounts(self) -> list[dict]:
        data = self._request("listaccts")
        # api.version=1 → data.acct ; legacy → acct
        payload = data.get("data") or data
        accts = payload.get("acct") or payload.get("accounts") or []
        if isinstance(accts, dict):
            accts = list(accts.values())
        results = []
        for a in accts:
            if not isinstance(a, dict):
                continue
            results.append(
                {
                    "user": a.get("user") or a.get("username") or "",
                    "domain": a.get("domain") or "",
                    "email": a.get("email") or "",
                    "plan": a.get("plan") or a.get("package") or "",
                    "diskused": a.get("diskused") or a.get("disk_used") or "",
                    "disklimit": a.get("disklimit") or a.get("disk_limit") or "",
                    "ip": a.get("ip") or "",
                    "owner": a.get("owner") or "",
                    "suspended": bool(a.get("suspended") or a.get("suspendreason")),
                }
            )
        return [r for r in results if r.get("user")]

    def start_pkgacct(self, username: str) -> dict:
        """Demande un package compte (best-effort selon version WHM)."""
        username = username.strip()
        # Tentatives d'API selon versions WHM
        for fn, params in (
            ("create_account_backup", {"username": username}),
            ("pkgacct", {"user": username, "homedir": 1}),
        ):
            try:
                return {"function": fn, "response": self._request(fn, params)}
            except VZoneAPIException:
                continue
        raise VZoneAPIException(
            detail=(
                "Ce WHM distant ne permet pas le packaging API automatique. "
                "Sur le serveur source, générez une archive "
                f"`/scripts/pkgacct {username}` ou Transfer Tool → "
                "téléchargez le cpmove, puis importez-la ici."
            ),
            code="whm_pkgacct_unsupported",
            status_code=501,
        )

    def download_bytes(self, url_path: str) -> bytes:
        url = f"https://{self.host}:{self.port}{url_path}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", f"whm {self.user}:{self.token}")
        context = ssl._create_unverified_context() if self.insecure_ssl else None  # noqa: S323
        with urllib.request.urlopen(req, timeout=max(self.timeout, 600), context=context) as resp:
            return resp.read()
