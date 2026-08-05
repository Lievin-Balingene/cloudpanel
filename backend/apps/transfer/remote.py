"""Client API WHM distant (Transfer Tool) — packaging + téléchargement cpmove."""
from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from apps.core.exceptions import VZoneAPIException

ProgressCb = Callable[[int, str], None]


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
        # Enlever éventuel :port dans le host
        if ":" in self.host and self.host.count(":") == 1:
            h, _, p = self.host.partition(":")
            if p.isdigit():
                self.host = h
                port = int(p)
        self.port = int(port or 2087)
        self.user = user.strip() or "root"
        self.token = token.strip()
        self.insecure_ssl = insecure_ssl
        self.timeout = timeout

    def _ssl_context(self) -> ssl.SSLContext | None:
        if self.insecure_ssl:
            return ssl._create_unverified_context()  # noqa: S323
        return None

    def _url(self, function: str, params: dict[str, Any] | None = None) -> str:
        q: dict[str, Any] = {"api.version": 1}
        if params:
            q.update(params)
        query = urllib.parse.urlencode(q)
        return f"https://{self.host}:{self.port}/json-api/{function}?{query}"

    def _auth_header(self) -> str:
        return f"whm {self.user}:{self.token}"

    def _request(
        self,
        function: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: int | None = None,
    ) -> dict:
        if not self.token:
            raise VZoneAPIException(
                detail="Token API WHM requis (pas le mot de passe root). "
                "WHM → Development → Manage API Tokens.",
                code="whm_token_required",
                status_code=400,
            )
        url = self._url(function, params)
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", self._auth_header())
        try:
            with urllib.request.urlopen(
                req,
                timeout=timeout or self.timeout,
                context=self._ssl_context(),
            ) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")[:800]
            if exc.code in {401, 403}:
                raise VZoneAPIException(
                    detail=(
                        f"Authentification WHM refusée (HTTP {exc.code}). "
                        "Utilisez un API Token WHM (root), pas le mot de passe du compte."
                    ),
                    code="whm_auth_failed",
                    status_code=502,
                ) from exc
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
        if not isinstance(data, dict):
            return {"data": data}
        meta = data.get("metadata") or {}
        if meta.get("result") in {0, "0", False} and function not in {"version"}:
            reason = meta.get("reason") or meta.get("output") or "échec WHM"
            raise VZoneAPIException(
                detail=f"WHM {function}: {reason}",
                code="whm_api_error",
                status_code=502,
            )
        return data

    def version(self) -> dict:
        return self._request("version")

    def list_accounts(self) -> list[dict]:
        data = self._request("listaccts")
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

    def _stream_download(self, url: str, dest: Path, *, timeout: int = 3600) -> int:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", self._auth_header())
        written = 0
        with urllib.request.urlopen(req, timeout=timeout, context=self._ssl_context()) as resp:
            ctype = (resp.headers.get("Content-Type") or "").lower()
            # Erreur JSON renvoyée à la place du tarball
            peek = resp.read(4)
            rest_start = peek
            if peek.startswith(b"{") or peek.startswith(b"["):
                body = peek + resp.read(4000)
                try:
                    err = json.loads(body.decode("utf-8", errors="replace"))
                    reason = (err.get("metadata") or {}).get("reason") or body[:200]
                except Exception:  # noqa: BLE001
                    reason = body[:200]
                raise VZoneAPIException(
                    detail=f"Téléchargement WHM refusé: {reason}",
                    code="whm_download_failed",
                    status_code=502,
                )
            with dest.open("wb") as out:
                if peek:
                    out.write(peek)
                    written += len(peek)
                while True:
                    chunk = resp.read(1024 * 1024)
                    if not chunk:
                        break
                    out.write(chunk)
                    written += len(chunk)
        if written < 64:
            raise VZoneAPIException(
                detail=f"Archive téléchargée trop petite ({written} o).",
                code="whm_download_empty",
                status_code=502,
            )
        # gzip magic or tar
        head = dest.read_bytes()[:4]
        if not (head.startswith(b"\x1f\x8b") or head.startswith(b"ustar") or head[:2] == b"PK"):
            # parfois tar non compressé commence autrement — accepter si > 1 Ko
            if written < 1024:
                raise VZoneAPIException(
                    detail="Le fichier téléchargé n'est pas une archive cpmove valide.",
                    code="whm_invalid_archive",
                    status_code=502,
                )
        _ = ctype  # unused, kept for debug
        _ = rest_start
        return written

    def download_cpmove(self, username: str, dest: Path, *, progress: ProgressCb | None = None) -> Path:
        """Télécharge cpmove-USER.tar.gz depuis le WHM distant."""
        username = username.strip()
        dest.parent.mkdir(parents=True, exist_ok=True)
        candidates = [
            self._url("fetch_pkgacct", {"user": username}),
            f"https://{self.host}:{self.port}/cgi/downloadcpmove.cgi?"
            + urllib.parse.urlencode({"file": f"cpmove-{username}.tar.gz"}),
            f"https://{self.host}:{self.port}/cgi/getfile.cgi?"
            + urllib.parse.urlencode({"file": f"/home/cpmove-{username}.tar.gz"}),
            f"https://{self.host}:{self.port}/download?"
            + urllib.parse.urlencode({"file": f"/home/cpmove-{username}.tar.gz"}),
            f"https://{self.host}:{self.port}/cgi/getfile.cgi?"
            + urllib.parse.urlencode({"file": f"/home/{username}/cpmove-{username}.tar.gz"}),
        ]
        errors: list[str] = []
        for idx, url in enumerate(candidates):
            try:
                if progress:
                    progress(
                        60 + idx,
                        f"Téléchargement cpmove (essai {idx + 1}/{len(candidates)})…",
                    )
                size = self._stream_download(url, dest, timeout=max(self.timeout, 3600))
                if progress:
                    progress(90, f"Archive téléchargée ({size} octets)")
                return dest
            except Exception as exc:  # noqa: BLE001
                short = url.split("?")[0].rsplit("/", 1)[-1]
                errors.append(f"{short}: {exc}")
                dest.unlink(missing_ok=True)
                continue
        raise VZoneAPIException(
            detail="Impossible de télécharger le cpmove distant. " + " ; ".join(errors[:3]),
            code="whm_download_failed",
            status_code=502,
        )

    def start_background_pkgacct(self, username: str) -> str | None:
        data = self._request(
            "start_background_pkgacct",
            {"user": username},
            timeout=max(self.timeout, 180),
        )
        payload = data.get("data") or {}
        session_id = payload.get("session_id") or payload.get("sessionid")
        return str(session_id) if session_id else None

    def pkgacct_session_state(self, session_id: str) -> str:
        data = self._request("get_pkgacct_session_state", {"session_id": session_id})
        payload = data.get("data") or {}
        return str(payload.get("state") or "").upper()

    def run_pkgacct_sync(self, username: str) -> dict:
        """pkgacct synchrone (peut prendre longtemps)."""
        return self._request(
            "pkgacct",
            {"user": username, "homedir": 1},
            timeout=max(self.timeout, 7200),
        )

    def package_and_fetch(
        self,
        username: str,
        dest: Path,
        *,
        progress: ProgressCb | None = None,
        poll_seconds: int = 5,
        max_wait_seconds: int = 7200,
    ) -> Path:
        """
        Crée un cpmove sur le WHM distant puis le télécharge localement.
        Pipeline compatible transfert cPanel → V-zone.
        """
        username = username.strip()
        if not username:
            raise VZoneAPIException(detail="Nom de compte distant requis.", code="missing_user", status_code=400)

        session_id: str | None = None
        if progress:
            progress(10, f"Démarrage pkgacct distant pour {username}…")

        # 1) Background (WHM moderne)
        try:
            session_id = self.start_background_pkgacct(username)
        except VZoneAPIException as exc:
            if progress:
                progress(12, f"start_background_pkgacct indisponible ({exc.detail}), repli pkgacct…")
            session_id = None

        if session_id:
            if progress:
                progress(15, f"Session pkgacct {session_id} — attente…")
            deadline = time.time() + max_wait_seconds
            last_state = ""
            while time.time() < deadline:
                try:
                    state = self.pkgacct_session_state(session_id)
                except VZoneAPIException:
                    state = "RUNNING"
                last_state = state
                if state == "COMPLETED":
                    if progress:
                        progress(55, "Packaging distant terminé — téléchargement…")
                    break
                if state == "FAILED":
                    raise VZoneAPIException(
                        detail=f"pkgacct distant a échoué (session {session_id}).",
                        code="whm_pkgacct_failed",
                        status_code=502,
                    )
                if progress:
                    elapsed = int(max_wait_seconds - (deadline - time.time()))
                    pct = min(50, 15 + elapsed // 30)
                    progress(pct, f"Packaging en cours ({state or 'RUNNING'})…")
                time.sleep(poll_seconds)
            else:
                raise VZoneAPIException(
                    detail=f"Timeout pkgacct distant (état={last_state}).",
                    code="whm_pkgacct_timeout",
                    status_code=504,
                )
        else:
            # 2) Synchrone
            if progress:
                progress(20, "pkgacct synchrone (peut être long)…")
            try:
                self.run_pkgacct_sync(username)
            except VZoneAPIException as exc:
                # 3) Peut-être qu'un cpmove existe déjà
                if progress:
                    progress(25, f"pkgacct sync échoué ({exc.detail}) — tentative téléchargement existant…")

        if progress:
            progress(60, "Téléchargement de l'archive cpmove…")
        return self.download_cpmove(username, dest, progress=progress)
