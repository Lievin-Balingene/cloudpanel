"""Client API WHM distant (Transfer Tool) — packaging + téléchargement cpmove."""
from __future__ import annotations

import base64
import json
import posixpath
import re
import secrets
import socket
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Callable

from apps.core.exceptions import VZoneAPIException

ProgressCb = Callable[[int, str], None]

_SSH_CONNECT_TIMEOUT = 15


def _egress_ip_hint() -> str:
    try:
        from django.conf import settings

        ip = (getattr(settings, "VZONE_PUBLIC_IP", "") or "").strip()
        if ip:
            return f" Autorisez l'IP sortante V-zone ({ip}) dans le firewall du serveur source."
    except Exception:  # noqa: BLE001
        pass
    return ""


def _classify_ssh_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "authentication" in msg or "auth failed" in msg:
        return "auth"
    if "connection refused" in msg or "errno 111" in msg:
        return "refused"
    if "timed out" in msg or "timeout" in msg or "errno 110" in msg:
        return "timeout"
    if "no route" in msg or "unreachable" in msg or "errno 113" in msg:
        return "network"
    return "other"


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
                    "homedir": a.get("homedir") or "",
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

    def resolve_cpmove_paths(self, username: str, *, extra: list[str] | None = None) -> list[str]:
        """Chemins distants probables pour le cpmove d'un compte (API WHM en priorité)."""
        username = username.strip()
        paths: list[str] = []
        seen: set[str] = set()

        def add(path: str) -> None:
            p = path.strip()
            if p and p not in seen:
                seen.add(p)
                paths.append(p)

        for raw in extra or []:
            add(raw)

        home = self.account_homedir(username).rstrip("/")
        for name in (
            f"cpmove-{username}.tar.gz",
            f"cpmove-{username}.tar",
            f"{username}.tar.gz",
            f"{username}.tar",
        ):
            add(f"{home}/{name}")

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

    def account_domain(self, username: str) -> str:
        username = username.strip().lower()
        for acct in self.list_accounts():
            if (acct.get("user") or "").lower() == username:
                return (acct.get("domain") or "").strip().lower().rstrip(".")
        return ""

    def account_homedir(self, username: str) -> str:
        """Répertoire home cPanel du compte (/home/user, /home2/user, …)."""
        username = username.strip().lower()
        for acct in self.list_accounts():
            if (acct.get("user") or "").lower() == username:
                home = (acct.get("homedir") or "").strip().rstrip("/")
                if home:
                    return home
        return f"/home/{username}"

    @staticmethod
    def _rel_to_account_home(username: str, absolute: str) -> str:
        """Chemin relatif au home cPanel (/home/user)."""
        home = f"/home/{username.strip().lower()}"
        abs_norm = absolute.replace("\\", "/")
        if abs_norm.startswith(home + "/"):
            return abs_norm[len(home) + 1 :]
        return posixpath.relpath(abs_norm, home)

    def _path_inside_homedir(self, username: str, absolute: str) -> bool:
        home = self.account_homedir(username).rstrip("/")
        abs_norm = absolute.replace("\\", "/")
        return abs_norm == home or abs_norm.startswith(home + "/")

    def _cpanel_fileop(
        self,
        cpanel_user: str,
        *,
        op: str,
        sourcefiles: str,
        destfiles: str = "",
    ) -> None:
        """Fileman::fileop via WHM API (API 2)."""
        params: dict[str, Any] = {
            "user": cpanel_user,
            "cpanel_jsonapi_user": cpanel_user,
            "cpanel_jsonapi_apiversion": 2,
            "cpanel_jsonapi_module": "Fileman",
            "cpanel_jsonapi_func": "fileop",
            "op": op,
            "sourcefiles": sourcefiles,
            "doubledecode": 1,
        }
        if destfiles:
            params["destfiles"] = destfiles
        data = self._request("cpanel", params)
        block = data.get("cpanelresult") or data.get("data") or {}
        if isinstance(block, dict):
            err = block.get("error") or block.get("reason")
            if err and str(err).lower() not in {"", "ok", "success"}:
                raise VZoneAPIException(
                    detail=f"Fileman {op}: {err}",
                    code="whm_cpanel_fileop_failed",
                    status_code=502,
                )
            rows = block.get("data")
            if isinstance(rows, list):
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    if row.get("result") in {0, "0", False}:
                        reason = row.get("error") or row.get("reason") or f"échec {op}"
                        raise VZoneAPIException(
                            detail=f"Fileman {op}: {reason}",
                            code="whm_cpanel_fileop_failed",
                            status_code=502,
                        )

    def _cpanel_fileop_cleanup(self, cpanel_user: str, rel_path: str) -> None:
        for op in ("unlink", "trash"):
            try:
                self._cpanel_fileop(
                    cpanel_user,
                    op=op,
                    sourcefiles=rel_path,
                    destfiles="" if op == "unlink" else rel_path,
                )
                return
            except VZoneAPIException:
                continue

    def _copy_cpmove_into_homedir(self, username: str, remote_path: str) -> str:
        """
        Copie un cpmove situé hors du home (ex. /home/cpmove-user.tar.gz)
        dans le répertoire du compte pour permettre Fileman / public_html.
        """
        home = self.account_homedir(username).rstrip("/")
        basename = posixpath.basename(remote_path)
        dest_rel = basename
        dest_abs = f"{home}/{basename}"
        if self._path_inside_homedir(username, remote_path):
            return remote_path
        last_err = ""
        for op in ("copy", "link"):
            try:
                self._cpanel_fileop(
                    username,
                    op=op,
                    sourcefiles=remote_path,
                    destfiles=dest_rel,
                )
                return dest_abs
            except VZoneAPIException as exc:
                last_err = str(exc.detail)
                continue
        raise VZoneAPIException(
            detail=(
                f"Impossible de copier {remote_path} vers {home} "
                f"(Fileman bloque les chemins hors home). {last_err}"
            ),
            code="whm_cpanel_fileop_failed",
            status_code=502,
        )

    def _download_via_public_site(
        self,
        username: str,
        remote_path: str,
        dest: Path,
        *,
        progress: ProgressCb | None = None,
    ) -> int:
        """
        Expose le cpmove via lien dans public_html et télécharge via le domaine du compte.
        Contourne SSH / URLs WHM 404 quand le site est servi depuis le serveur source.
        """
        domain = self.account_domain(username)
        if not domain:
            raise VZoneAPIException(
                detail=f"Domaine introuvable pour le compte {username}.",
                code="whm_download_failed",
                status_code=502,
            )
        try:
            import requests
        except ImportError as exc:
            raise VZoneAPIException(
                detail="Bibliothèque requests manquante.",
                code="whm_http_unavailable",
                status_code=500,
            ) from exc

        token = secrets.token_hex(10)
        filename = f".vz-{token}.tar.gz"
        rel_dest = f"public_html/{filename}"
        publish_path = remote_path
        fileop_errors: list[str] = []

        if not self._path_inside_homedir(username, remote_path):
            if progress:
                progress(62, f"Copie {remote_path} dans le home du compte…")
            try:
                publish_path = self._copy_cpmove_into_homedir(username, remote_path)
            except VZoneAPIException as exc:
                fileop_errors.append(str(exc.detail))

        rel_src = self._rel_to_account_home(username, publish_path)
        if rel_src.startswith("../"):
            fileop_errors.append(
                f"Chemin hors home ({publish_path}) — impossible via Fileman sans SSH."
            )

        linked = False
        for op in ("link", "copy"):
            try:
                if progress:
                    progress(63, f"Lien public ({op}) {rel_src} → {rel_dest}…")
                self._cpanel_fileop(username, op=op, sourcefiles=rel_src, destfiles=rel_dest)
                linked = True
                break
            except VZoneAPIException as exc:
                fileop_errors.append(f"{op}: {exc.detail}")
                continue
        if not linked:
            hint = fileop_errors[-1] if fileop_errors else "Fileman a refusé l'opération."
            raise VZoneAPIException(
                detail=(
                    f"Impossible de publier {remote_path} dans public_html ({hint}). "
                    "Relancez le transfert après mise à jour V-zone (pkgacct dans le home du compte)"
                    + _egress_ip_hint()
                    + "."
                ),
                code="whm_download_failed",
                status_code=502,
            )

        sess = requests.Session()
        sess.verify = not self.insecure_ssl
        urls = [
            f"https://{domain}/{filename}",
            f"http://{domain}/{filename}",
            f"https://www.{domain}/{filename}",
        ]
        errors: list[str] = []
        try:
            for url in urls:
                try:
                    if progress:
                        progress(65, f"GET {url}…")
                    return self._http_download_file(sess, url, dest, timeout=7200)
                except VZoneAPIException as exc:
                    errors.append(f"{url}: {exc.detail}")
                    dest.unlink(missing_ok=True)
        finally:
            self._cpanel_fileop_cleanup(username, rel_dest)

        raise VZoneAPIException(
            detail="Téléchargement via domaine impossible. " + " ; ".join(errors[:3]),
            code="whm_download_failed",
            status_code=502,
        )

    def _paths_from_pkgacct_log(self, session_id: str) -> list[str]:
        """Extrait les chemins cpmove du journal pkgacct WHM."""
        paths: list[str] = []
        try:
            data = self._request("fetch_pkgacct_master_log", {"session_id": session_id})
        except VZoneAPIException:
            return paths
        raw = (data.get("data") or {}).get("contents") or ""
        if not raw:
            return paths
        for match in re.finditer(r"(/[\w./-]*cpmove[\w./-]*)", raw):
            paths.append(match.group(1).rstrip(".,;"))
        for match in re.finditer(r"(/home[\w./-]*backup[\w./-]*\.tar\.gz)", raw):
            paths.append(match.group(1))
        return paths

    def _require_password_auth(self) -> None:
        if self.auth_method != "basic-password":
            raise VZoneAPIException(
                detail=(
                    "Téléchargement SCP impossible avec un API Token seul. "
                    "Utilisez le mot de passe root WHM/SSH pour migrer depuis WHM distant."
                ),
                code="whm_scp_password_required",
                status_code=400,
            )

    def _ssh_client(self):
        """Ouvre une session SSH (fermer avec .close())."""
        self._require_password_auth()
        try:
            import paramiko
        except ImportError as exc:
            raise VZoneAPIException(
                detail="Bibliothèque paramiko manquante sur le serveur V-zone.",
                code="whm_scp_unavailable",
                status_code=500,
            ) from exc

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
                timeout=_SSH_CONNECT_TIMEOUT,
                banner_timeout=_SSH_CONNECT_TIMEOUT,
                auth_timeout=_SSH_CONNECT_TIMEOUT,
                allow_agent=False,
                look_for_keys=False,
            )
        except Exception as exc:  # noqa: BLE001
            kind = _classify_ssh_error(exc)
            hint = _egress_ip_hint()
            if kind == "timeout":
                detail = (
                    f"Connexion SSH impossible (timeout) vers {self.host}:{self.ssh_port}.{hint} "
                    "Le port SSH doit être ouvert depuis le serveur V-zone vers le WHM source."
                )
                code = "whm_ssh_unreachable"
            elif kind == "refused":
                detail = (
                    f"Connexion SSH refusée sur {self.host}:{self.ssh_port}. "
                    f"Vérifiez le port SSH (pas seulement 2087 WHM).{hint}"
                )
                code = "whm_ssh_unreachable"
            elif kind == "auth":
                detail = (
                    f"Authentification SSH refusée pour {self.user}@{self.host}:{self.ssh_port}. "
                    "Le mot de passe root WHM doit aussi fonctionner en SSH."
                )
                code = "whm_ssh_auth_failed"
            else:
                detail = f"SSH {self.host}:{self.ssh_port}: {exc}{hint}"
                code = "whm_ssh_unreachable"
            raise VZoneAPIException(detail=detail, code=code, status_code=502) from exc
        return ssh

    def check_ssh_access(self) -> dict[str, Any]:
        """Test rapide SSH (port + auth)."""
        if self.auth_method != "basic-password":
            return {
                "ok": False,
                "message": "Mot de passe root requis pour SCP (API Token seul insuffisant).",
            }
        try:
            with socket.create_connection((self.host, self.ssh_port), timeout=8):
                pass
        except OSError as exc:
            return {
                "ok": False,
                "message": (
                    f"Port SSH {self.ssh_port} injoignable sur {self.host}: {exc}."
                    + _egress_ip_hint()
                ),
            }
        ssh = self._ssh_client()
        try:
            _stdin, stdout, _stderr = ssh.exec_command("echo ok", timeout=10)
            stdout.channel.recv_exit_status()
            if stdout.read().decode().strip() != "ok":
                return {"ok": False, "message": "SSH connecté mais commande test échouée."}
            return {"ok": True, "message": f"SSH OK ({self.host}:{self.ssh_port})"}
        except Exception as exc:  # noqa: BLE001
            return {"ok": False, "message": str(exc)}
        finally:
            ssh.close()

    def _discover_cpmove_ssh(self, ssh: Any, username: str) -> list[str]:
        """find distant pour localiser l'archive réelle."""
        safe = re.sub(r"[^a-zA-Z0-9_-]", "", username)
        cmd = (
            f"find /home /home2 /home3 /root /var/cpanel/user_backups -maxdepth 2 "
            f"\\( -name 'cpmove-{safe}*.tar.gz' -o -name 'cpmove-{safe}*.tar' "
            f"-o -name 'backup-*{safe}*.tar.gz' -o -name '{safe}.tar.gz' "
            f"-o -type d -name 'cpmove-{safe}' \\) -printf '%p\\n' 2>/dev/null | head -30"
        )
        _stdin, stdout, _stderr = ssh.exec_command(cmd, timeout=90)
        stdout.channel.recv_exit_status()
        return [line.strip() for line in stdout.read().decode("utf-8", errors="replace").splitlines() if line.strip()]

    def _validate_downloaded_archive(self, dest: Path, remote_path: str) -> int:
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

    def _sftp_download_file(self, sftp: Any, remote_path: str, dest: Path) -> int:
        dest.parent.mkdir(parents=True, exist_ok=True)
        sftp.get(remote_path, str(dest))
        return self._validate_downloaded_archive(dest, remote_path)

    def _sftp_download_split(self, sftp: Any, first_part_path: str, dest: Path) -> int:
        import os

        base_dir = os.path.dirname(first_part_path) or "/home"
        prefix = os.path.basename(first_part_path).split(".part")[0]
        names = sorted(
            n for n in sftp.listdir(base_dir) if n.startswith(prefix + ".part") or n == prefix
        )
        if not names:
            raise VZoneAPIException(
                detail=f"Aucune partie split trouvée pour {prefix}",
                code="whm_archive_not_ready",
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
        return self._validate_downloaded_archive(dest, first_part_path)

    def _scp_download_candidates(
        self,
        username: str,
        dest: Path,
        *,
        progress: ProgressCb | None = None,
        extra_paths: list[str] | None = None,
    ) -> int:
        """Une seule session SSH : discover + téléchargement."""
        paths = self.resolve_cpmove_paths(username, extra=extra_paths)
        ssh = self._ssh_client()
        try:
            discovered = self._discover_cpmove_ssh(ssh, username)
            merged: list[str] = []
            seen: set[str] = set()
            for p in discovered + paths:
                if p not in seen:
                    seen.add(p)
                    merged.append(p)

            if progress and discovered:
                progress(62, f"Archives trouvées via SSH : {len(discovered)}")

            sftp = ssh.open_sftp()
            errors: list[str] = []
            try:
                for idx, remote_path in enumerate(merged):
                    if progress:
                        progress(63 + min(idx, 4), f"SCP {remote_path}…")
                    try:
                        if ".part" in remote_path:
                            return self._sftp_download_split(sftp, remote_path, dest)
                        try:
                            st = sftp.stat(remote_path)
                        except OSError:
                            errors.append(f"{remote_path}: absent")
                            continue
                        if st.st_size < 64:
                            errors.append(f"{remote_path}: {st.st_size} o")
                            continue
                        return self._sftp_download_file(sftp, remote_path, dest)
                    except VZoneAPIException as exc:
                        errors.append(f"{remote_path}: {exc.detail}")
                        dest.unlink(missing_ok=True)
                        continue
                    except OSError as exc:
                        errors.append(f"{remote_path}: {exc}")
                        dest.unlink(missing_ok=True)
                        continue
            finally:
                sftp.close()
        finally:
            ssh.close()

        raise VZoneAPIException(
            detail=(
                "Archive cpmove introuvable sur le serveur distant"
                + (f" ({'; '.join(errors[:4])})" if errors else "")
                + ". Le packaging pkgacct est peut-être encore en cours."
            ),
            code="whm_archive_not_ready",
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

    def _http_download_urls(self, remote_path: str, cp_token: str = "") -> list[str]:
        """URLs WHM possibles pour télécharger un fichier (session ou auth directe)."""
        enc = urllib.parse.quote(remote_path, safe="")
        token = cp_token.strip("/")
        prefix = f"https://{self.host}:{self.port}"
        urls = []
        if token:
            urls.extend(
                [
                    f"{prefix}/{token}/download?file={enc}",
                    f"{prefix}/{token}/scripts/download?file={enc}",
                    f"{prefix}/{token}/cgi/getfile.cgi?file={enc}",
                ]
            )
        urls.extend(
            [
                f"{prefix}/download?file={enc}",
                f"{prefix}/scripts/download?file={enc}",
                f"{prefix}/cgi/getfile.cgi?file={enc}",
                f"{prefix}/cgi/downloadcpmove.cgi?file={enc.rsplit('/', 1)[-1]}",
            ]
        )
        return urls

    def _open_whm_http_session(self):
        """Session HTTP avec cookies WHM (create_user_session)."""
        try:
            import requests
        except ImportError as exc:
            raise VZoneAPIException(
                detail="Bibliothèque requests manquante.",
                code="whm_http_unavailable",
                status_code=500,
            ) from exc

        sess = requests.Session()
        sess.verify = not self.insecure_ssl
        sess.headers.update({"Authorization": self._auth_header()})
        data = self._request("create_user_session", {"user": self.user, "service": "whostmgrd"})
        payload = data.get("data") or {}
        session_url = payload.get("url") or ""
        cp_token = str(payload.get("cp_security_token") or "").strip("/")
        if not session_url:
            raise VZoneAPIException(
                detail="WHM create_user_session n'a pas renvoyé d'URL.",
                code="whm_session_failed",
                status_code=502,
            )
        try:
            resp = sess.get(session_url, timeout=60, allow_redirects=True)
            resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise VZoneAPIException(
                detail=f"Activation session WHM impossible: {exc}",
                code="whm_session_failed",
                status_code=502,
            ) from exc
        # Les requêtes de download utilisent les cookies, pas Authorization
        sess.headers.pop("Authorization", None)
        return sess, cp_token

    def _http_download_file(
        self,
        sess: Any,
        url: str,
        dest: Path,
        *,
        timeout: int = 7200,
    ) -> int:
        import requests

        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            with sess.get(url, stream=True, timeout=(60, timeout)) as resp:
                resp.raise_for_status()
                ctype = (resp.headers.get("Content-Type") or "").lower()
                peek = resp.raw.read(4, decode_content=False)
                if peek.startswith(b"{") or peek.startswith(b"["):
                    body = peek + resp.content[:4000]
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
                if "text/html" in ctype and len(peek) < 256:
                    # Probable page d'erreur WHM
                    rest = resp.raw.read(2000, decode_content=False)
                    if b"<html" in (peek + rest).lower():
                        raise VZoneAPIException(
                            detail="WHM a renvoyé une page HTML au lieu de l'archive.",
                            code="whm_download_failed",
                            status_code=502,
                        )
                written = 0
                with dest.open("wb") as out:
                    if peek:
                        out.write(peek)
                        written += len(peek)
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            out.write(chunk)
                            written += len(chunk)
        except VZoneAPIException:
            dest.unlink(missing_ok=True)
            raise
        except requests.RequestException as exc:
            dest.unlink(missing_ok=True)
            raise VZoneAPIException(
                detail=f"HTTP {url.split('?')[0]}: {exc}",
                code="whm_download_failed",
                status_code=502,
            ) from exc
        return self._validate_downloaded_archive(dest, url)

    def _http_download_candidates(
        self,
        username: str,
        dest: Path,
        *,
        progress: ProgressCb | None = None,
        extra_paths: list[str] | None = None,
    ) -> int:
        """Télécharge via session WHM (port 2087) — sans SSH."""
        paths = self.resolve_cpmove_paths(username, extra=extra_paths)
        if progress:
            progress(60, "Téléchargement HTTP WHM (session 2087)…")
        sess, cp_token = self._open_whm_http_session()
        errors: list[str] = []
        for remote_path in paths[:8]:
            for url in self._http_download_urls(remote_path, cp_token):
                short = url.split("?")[0].rsplit("/", 1)[-1]
                try:
                    if progress:
                        progress(62, f"HTTP {short} — {remote_path}…")
                    return self._http_download_file(sess, url, dest)
                except VZoneAPIException as exc:
                    errors.append(f"{short}: {exc.detail}")
                    dest.unlink(missing_ok=True)
                    continue
        raise VZoneAPIException(
            detail="Téléchargement HTTP WHM impossible. " + " ; ".join(errors[:4]),
            code="whm_download_failed",
            status_code=502,
        )

    def download_cpmove(
        self,
        username: str,
        dest: Path,
        *,
        progress: ProgressCb | None = None,
        wait_seconds: int = 180,
        extra_paths: list[str] | None = None,
    ) -> Path:
        """Télécharge cpmove-USER (SCP si SSH OK, sinon session HTTP WHM 2087)."""
        username = username.strip()
        dest.parent.mkdir(parents=True, exist_ok=True)

        ssh_probe = self.check_ssh_access()
        ssh_ok = bool(ssh_probe.get("ok"))
        errors: list[str] = []

        if ssh_ok:
            if progress:
                progress(58, f"SSH {self.host}:{self.ssh_port}…")
            deadline = time.time() + wait_seconds
            last_scp_error: VZoneAPIException | None = None
            while time.time() < deadline:
                try:
                    size = self._scp_download_candidates(
                        username,
                        dest,
                        progress=progress,
                        extra_paths=extra_paths,
                    )
                    if progress:
                        progress(90, f"Archive téléchargée via SCP ({size} octets)")
                    return dest
                except VZoneAPIException as exc:
                    last_scp_error = exc
                    code = getattr(exc, "default_code", "") or ""
                    if code in {"whm_scp_password_required", "whm_ssh_auth_failed"}:
                        errors.append(str(exc.detail))
                        break
                    if code != "whm_archive_not_ready":
                        errors.append(str(exc.detail))
                        break
                    if progress:
                        progress(61, "Archive pas encore prête — nouvelle tentative SCP…")
                    time.sleep(8)
            if last_scp_error and getattr(last_scp_error, "default_code", "") == "whm_archive_not_ready":
                errors.append(str(last_scp_error.detail))
        else:
            msg = str(ssh_probe.get("message") or "SSH inaccessible")
            errors.append(msg)
            if progress:
                progress(58, "SSH indisponible — repli HTTP WHM…")

        try:
            size = self._http_download_candidates(
                username,
                dest,
                progress=progress,
                extra_paths=extra_paths,
            )
            if progress:
                progress(90, f"Archive téléchargée via HTTP ({size} octets)")
            return dest
        except VZoneAPIException as exc:
            errors.append(str(exc.detail))

        # Repli : lien temporaire dans public_html + GET via le domaine du compte
        paths = self.resolve_cpmove_paths(username, extra=extra_paths)
        for remote_path in paths[:4]:
            try:
                if progress:
                    progress(64, f"Téléchargement web {remote_path}…")
                size = self._download_via_public_site(
                    username, remote_path, dest, progress=progress
                )
                if progress:
                    progress(90, f"Archive via domaine ({size} octets)")
                return dest
            except VZoneAPIException as exc:
                errors.append(str(exc.detail))
                dest.unlink(missing_ok=True)

        raise VZoneAPIException(
            detail=(
                "Impossible de télécharger le cpmove distant. "
                + " | ".join(errors[:5])
                + ". Solutions : (1) ouvrir le port SSH "
                + str(self.ssh_port)
                + " depuis le serveur V-zone"
                + _egress_ip_hint()
                + " ; (2) uploader l'archive dans l'onglet « Archive cPanel »."
            ),
            code="whm_download_failed",
            status_code=502,
        )

    def start_background_pkgacct(self, username: str, *, tarroot: str | None = None) -> str | None:
        dest_dir = (tarroot or self.account_homedir(username)).rstrip("/")
        data = self._request(
            "start_background_pkgacct",
            {"user": username, "split": 0, "tarroot": dest_dir},
            timeout=max(self.timeout, 180),
        )
        payload = data.get("data") or {}
        session_id = payload.get("session_id") or payload.get("sessionid")
        return str(session_id) if session_id else None

    def pkgacct_session_state(self, session_id: str) -> str:
        data = self._request("get_pkgacct_session_state", {"session_id": session_id})
        payload = data.get("data") or {}
        return str(payload.get("state") or "").upper()

    def run_pkgacct_sync(self, username: str, *, tarroot: str | None = None) -> dict:
        """pkgacct synchrone (peut prendre longtemps)."""
        dest_dir = (tarroot or self.account_homedir(username)).rstrip("/")
        return self._request(
            "pkgacct",
            {"user": username, "homedir": 1, "tarroot": dest_dir},
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

        homedir = self.account_homedir(username)
        if progress:
            progress(11, f"pkgacct distant → {homedir}…")

        # 1) Background (WHM moderne)
        try:
            session_id = self.start_background_pkgacct(username, tarroot=homedir)
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
                self.run_pkgacct_sync(username, tarroot=homedir)
            except VZoneAPIException as exc:
                # 3) Peut-être qu'un cpmove existe déjà
                if progress:
                    progress(25, f"pkgacct sync échoué ({exc.detail}) — tentative téléchargement existant…")

        if progress:
            progress(60, "Téléchargement de l'archive cpmove…")
        extra_paths = self._paths_from_pkgacct_log(session_id) if session_id else []
        return self.download_cpmove(username, dest, progress=progress, extra_paths=extra_paths)
