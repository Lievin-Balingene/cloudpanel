"""Client API WHM distant (Transfer Tool) — packaging + téléchargement cpmove."""
from __future__ import annotations

import base64
import json
import re
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
    """
    Client WHM API 1.

    Accepte dans le champ « token » :
    - un API Token WHM (Manage API Tokens)
    - un access hash legacy (sans retours à la ligne)
    - le mot de passe root / reseller (auth Basic HTTP)
    """

    def __init__(
        self,
        host: str,
        *,
        port: int = 2087,
        user: str = "root",
        token: str = "",
        insecure_ssl: bool = False,
        ssh_port: int = 22,
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
        self.ssh_port = int(ssh_port or 22)
        self.timeout = timeout
        self._auth_header_value: str | None = None
        self.auth_method: str = ""

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

    def _auth_candidates(self) -> list[tuple[str, str]]:
        """(méthode, valeur Authorization) — ordre : token, hash aplati, Basic password."""
        secret = self.token
        flat = re.sub(r"\s+", "", secret)
        out: list[tuple[str, str]] = []
        seen: set[str] = set()

        def add(name: str, header: str) -> None:
            if header and header not in seen:
                seen.add(header)
                out.append((name, header))

        # API Token / Access Hash (docs cPanel)
        add("whm-token", f"whm {self.user}:{secret}")
        if flat != secret:
            add("whm-token-flat", f"whm {self.user}:{flat}")
        add("WHM-hash", f"WHM {self.user}:{secret}")
        if flat != secret:
            add("WHM-hash-flat", f"WHM {self.user}:{flat}")
        # Username + password (Basic) — ce que beaucoup d'admins collent dans le champ
        raw = f"{self.user}:{secret}".encode("utf-8")
        add("basic-password", "Basic " + base64.b64encode(raw).decode("ascii"))
        return out

    def _auth_header(self) -> str:
        if not self._auth_header_value:
            self.ensure_auth()
        assert self._auth_header_value is not None
        return self._auth_header_value

    def ensure_auth(self) -> dict:
        """Probe version() avec chaque schéma d'auth jusqu'à succès."""
        if self._auth_header_value:
            try:
                return self._request_once("version")
            except VZoneAPIException:
                self._auth_header_value = None
                self.auth_method = ""

        if not self.token:
            raise VZoneAPIException(
                detail=(
                    "Identifiant WHM requis : API Token (WHM → Development → Manage API Tokens) "
                    "ou mot de passe root/reseller."
                ),
                code="whm_token_required",
                status_code=400,
            )

        auth_errors: list[str] = []
        last_non_auth: VZoneAPIException | None = None

        for method, header in self._auth_candidates():
            self._auth_header_value = header
            self.auth_method = method
            try:
                data = self._request_once("version", allow_auth_retry=False)
                return data
            except VZoneAPIException as exc:
                exc_code = getattr(exc, "default_code", None) or getattr(exc, "code", "") or ""
                if exc_code == "whm_auth_failed":
                    auth_errors.append(method)
                    self._auth_header_value = None
                    self.auth_method = ""
                    continue
                # Autre erreur HTTP/API : l'auth a probablement fonctionné
                last_non_auth = exc
                # Garder l'auth qui a passé le 401/403
                if method.startswith("basic"):
                    # version() a parfois un corps atypique — retenter listaccts
                    try:
                        return self._request_once("listaccts", allow_auth_retry=False)
                    except VZoneAPIException as exc2:
                        code2 = getattr(exc2, "default_code", None) or getattr(exc2, "code", "") or ""
                        if code2 == "whm_auth_failed":
                            auth_errors.append(method)
                            self._auth_header_value = None
                            self.auth_method = ""
                            continue
                        raise
                raise

        detail = (
            "Authentification WHM refusée (HTTP 401/403). "
            "Essayé : API Token (Authorization: whm), access hash, et mot de passe (Basic). "
            "Vérifiez user/root, le secret, le port 2087, et que l'API n'est pas bloquée "
            "(2FA sur password → activer « API requests » dans Security Policies)."
        )
        if auth_errors:
            detail += f" Méthodes tentées : {', '.join(auth_errors)}."
        if last_non_auth:
            raise last_non_auth
        raise VZoneAPIException(
            detail=detail,
            code="whm_auth_failed",
            status_code=502,
        )

    def _request_once(
        self,
        function: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: int | None = None,
        allow_auth_retry: bool = True,
    ) -> dict:
        if not self._auth_header_value:
            if allow_auth_retry:
                self.ensure_auth()
            else:
                raise VZoneAPIException(
                    detail="Auth WHM non initialisée.",
                    code="whm_auth_failed",
                    status_code=502,
                )
        url = self._url(function, params)
        req = urllib.request.Request(url, method="GET")
        req.add_header("Authorization", self._auth_header_value or "")
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
                        "Token API, access hash ou mot de passe invalide."
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
            reason = str(meta.get("reason") or meta.get("output") or "échec WHM")
            # Certains WHM renvoient result=0 + "Permission denied" / auth dans le JSON
            low = reason.lower()
            if any(x in low for x in ("permission denied", "auth", "login", "token", "password")):
                raise VZoneAPIException(
                    detail=f"Authentification WHM refusée: {reason}",
                    code="whm_auth_failed",
                    status_code=502,
                )
            raise VZoneAPIException(
                detail=f"WHM {function}: {reason}",
                code="whm_api_error",
                status_code=502,
            )
        return data

    def _request(
        self,
        function: str,
        params: dict[str, Any] | None = None,
        *,
        timeout: int | None = None,
    ) -> dict:
        if not self.token:
            raise VZoneAPIException(
                detail=(
                    "Identifiant WHM requis : API Token ou mot de passe root/reseller."
                ),
                code="whm_token_required",
                status_code=400,
            )
        self.ensure_auth()
        return self._request_once(function, params, timeout=timeout)

    def version(self) -> dict:
        return self.ensure_auth()

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

    def list_cparchive_files(self) -> list[dict[str, str]]:
        """Liste les archives cpmove/backup disponibles sur le serveur WHM."""
        data = self._request("list_cparchive_files")
        payload = data.get("data") or {}
        files = payload.get("quickrestore_files") or []
        if isinstance(files, dict):
            files = list(files.values())
        out: list[dict[str, str]] = []
        for entry in files:
            if not isinstance(entry, dict):
                continue
            out.append(
                {
                    "user": str(entry.get("user") or ""),
                    "file": str(entry.get("file") or ""),
                    "path": str(entry.get("path") or "/home"),
                }
            )
        return out

    def resolve_cpmove_paths(self, username: str) -> list[str]:
        """Chemins distants probables pour le cpmove d'un compte."""
        username = username.strip()
        paths: list[str] = []
        seen: set[str] = set()

        def add(path: str) -> None:
            p = path.strip()
            if p and p not in seen:
                seen.add(p)
                paths.append(p)

        try:
            for entry in self.list_cparchive_files():
                if (entry.get("user") or "").lower() != username.lower():
                    continue
                base = (entry.get("path") or "/home").rstrip("/")
                name = entry.get("file") or ""
                if name:
                    add(f"{base}/{name}")
        except VZoneAPIException:
            pass

        for name in (
            f"cpmove-{username}.tar.gz",
            f"cpmove-{username}.tar",
            f"{username}.tar.gz",
            f"{username}.tar",
        ):
            for base in ("/home", "/home2", "/home3", "/root"):
                add(f"{base}/{name}")
        return paths

    def _remote_file_size_scp(self, remote_path: str) -> int:
        """Vérifie l'existence et la taille d'un fichier distant via SFTP."""
        import paramiko

        ssh = paramiko.SSHClient()
        if self.insecure_ssl:
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        else:
            ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            ssh.connect(
                self.host,
                port=self.ssh_port,
                username=self.user,
                password=self.token,
                timeout=30,
                allow_agent=False,
                look_for_keys=False,
            )
            sftp = ssh.open_sftp()
            try:
                return int(sftp.stat(remote_path).st_size)
            finally:
                sftp.close()
        finally:
            ssh.close()

    def download_via_scp(self, remote_path: str, dest: Path) -> int:
        """Télécharge un fichier via SFTP/SSH (mot de passe root requis)."""
        if self.auth_method != "basic-password":
            raise VZoneAPIException(
                detail=(
                    "Téléchargement SCP impossible avec un API Token seul. "
                    "Utilisez le mot de passe root WHM/SSH pour migrer depuis WHM distant."
                ),
                code="whm_scp_password_required",
                status_code=400,
            )
        try:
            import paramiko
        except ImportError as exc:
            raise VZoneAPIException(
                detail="Bibliothèque paramiko manquante sur le serveur V-zone.",
                code="whm_scp_unavailable",
                status_code=500,
            ) from exc

        dest.parent.mkdir(parents=True, exist_ok=True)
        ssh = paramiko.SSHClient()
        if self.insecure_ssl:
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        else:
            ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            ssh.connect(
                self.host,
                port=self.ssh_port,
                username=self.user,
                password=self.token,
                timeout=60,
                allow_agent=False,
                look_for_keys=False,
            )
            sftp = ssh.open_sftp()
            try:
                sftp.get(remote_path, str(dest))
            finally:
                sftp.close()
        except Exception as exc:  # noqa: BLE001
            raise VZoneAPIException(
                detail=f"SCP/SFTP {remote_path}: {exc}",
                code="whm_scp_failed",
                status_code=502,
            ) from exc
        finally:
            ssh.close()

        size = dest.stat().st_size
        if size < 64:
            dest.unlink(missing_ok=True)
            raise VZoneAPIException(
                detail=f"Fichier distant trop petit ({size} o): {remote_path}",
                code="whm_download_empty",
                status_code=502,
            )
        head = dest.read_bytes()[:4]
        if not (head.startswith(b"\x1f\x8b") or head.startswith(b"ustar") or head[:2] == b"PK"):
            if size < 1024:
                dest.unlink(missing_ok=True)
                raise VZoneAPIException(
                    detail=f"Fichier distant invalide (pas une archive): {remote_path}",
                    code="whm_invalid_archive",
                    status_code=502,
                )
        return size

    def _download_split_parts_scp(self, first_part_path: str, dest: Path) -> int:
        """Assemble cpmove-USER.tar.gz.part00001… en une seule archive locale."""
        import os

        import paramiko

        base_dir = os.path.dirname(first_part_path) or "/home"
        prefix = os.path.basename(first_part_path).split(".part")[0]

        ssh = paramiko.SSHClient()
        if self.insecure_ssl:
            ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        else:
            ssh.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            ssh.connect(
                self.host,
                port=self.ssh_port,
                username=self.user,
                password=self.token,
                timeout=60,
                allow_agent=False,
                look_for_keys=False,
            )
            sftp = ssh.open_sftp()
            try:
                names = sorted(
                    n for n in sftp.listdir(base_dir) if n.startswith(prefix + ".part") or n == prefix
                )
                if not names:
                    raise VZoneAPIException(
                        detail=f"Aucune partie split trouvée pour {prefix}",
                        code="whm_download_failed",
                        status_code=502,
                    )
                dest.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with dest.open("wb") as out:
                    for name in names:
                        part_path = f"{base_dir.rstrip('/')}/{name}"
                        with sftp.open(part_path, "rb") as part:
                            while True:
                                chunk = part.read(1024 * 1024)
                                if not chunk:
                                    break
                                out.write(chunk)
                                written += len(chunk)
            finally:
                sftp.close()
        finally:
            ssh.close()
        return written

    def _scp_download_candidates(
        self,
        username: str,
        dest: Path,
        *,
        progress: ProgressCb | None = None,
    ) -> int:
        errors: list[str] = []
        paths = self.resolve_cpmove_paths(username)
        for idx, remote_path in enumerate(paths):
            if progress:
                progress(62 + min(idx, 5), f"SCP {remote_path}…")
            try:
                if ".part" in remote_path:
                    return self._download_split_parts_scp(remote_path, dest)
                size = self._remote_file_size_scp(remote_path)
                if size < 64:
                    errors.append(f"{remote_path}: {size} o")
                    continue
                return self.download_via_scp(remote_path, dest)
            except VZoneAPIException as exc:
                errors.append(f"{remote_path}: {exc.detail}")
                dest.unlink(missing_ok=True)
                continue
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{remote_path}: {exc}")
                dest.unlink(missing_ok=True)
                continue
        raise VZoneAPIException(
            detail="SCP/SFTP impossible. " + " ; ".join(errors[:4]),
            code="whm_scp_failed",
            status_code=502,
        )

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

    def download_cpmove(
        self,
        username: str,
        dest: Path,
        *,
        progress: ProgressCb | None = None,
        wait_seconds: int = 120,
    ) -> Path:
        """Télécharge cpmove-USER depuis le WHM distant (SCP puis repli HTTP)."""
        username = username.strip()
        dest.parent.mkdir(parents=True, exist_ok=True)

        deadline = time.time() + wait_seconds
        last_scp_error: VZoneAPIException | None = None
        while time.time() < deadline:
            try:
                size = self._scp_download_candidates(username, dest, progress=progress)
                if progress:
                    progress(90, f"Archive téléchargée via SCP ({size} octets)")
                return dest
            except VZoneAPIException as exc:
                last_scp_error = exc
                if getattr(exc, "default_code", "") == "whm_scp_password_required":
                    break
                if progress:
                    progress(61, "Archive pas encore prête — nouvelle tentative SCP…")
                time.sleep(5)

        if last_scp_error and getattr(last_scp_error, "default_code", "") == "whm_scp_password_required":
            raise last_scp_error

        # Repli HTTP (rare ; la plupart des WHM n'exposent pas de CGI de download)
        paths = self.resolve_cpmove_paths(username)
        http_candidates: list[str] = []
        for remote_path in paths[:6]:
            http_candidates.append(
                f"https://{self.host}:{self.port}/download?"
                + urllib.parse.urlencode({"file": remote_path})
            )
        errors: list[str] = []
        if last_scp_error:
            errors.append(f"SCP: {last_scp_error.detail}")
        for idx, url in enumerate(http_candidates):
            try:
                if progress:
                    progress(65 + idx, f"Téléchargement HTTP (essai {idx + 1})…")
                size = self._stream_download(url, dest, timeout=max(self.timeout, 3600))
                if progress:
                    progress(90, f"Archive téléchargée ({size} octets)")
                return dest
            except Exception as exc:  # noqa: BLE001
                short = url.split("?")[0].rsplit("/", 1)[-1]
                errors.append(f"{short}: {exc}")
                dest.unlink(missing_ok=True)
        raise VZoneAPIException(
            detail=(
                "Impossible de télécharger le cpmove distant. "
                + " ; ".join(errors[:4])
                + ". Vérifiez que SSH root (port "
                + str(self.ssh_port)
                + ") accepte le mot de passe."
            ),
            code="whm_download_failed",
            status_code=502,
        )

    def start_background_pkgacct(self, username: str) -> str | None:
        data = self._request(
            "start_background_pkgacct",
            {"user": username, "split": 0},
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
