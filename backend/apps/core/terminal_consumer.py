"""Web terminal consumer (PTY) with package SSH authorization + drop privileges."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import pty
import shlex
import signal
import subprocess
import tempfile
import termios
from pathlib import Path
from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken

from apps.packages.models import PackageAssignment

User = get_user_model()
logger = logging.getLogger(__name__)


@database_sync_to_async
def _resolve_user_and_access(user_id: int) -> tuple[object | None, bool]:
    try:
        user = User.objects.get(pk=user_id, is_active=True, is_suspended=False)
    except User.DoesNotExist:
        return None, False
    if getattr(user, "role", None) in {"administrator", "reseller"}:
        return user, True
    assignment = PackageAssignment.objects.filter(user=user).select_related("package").first()
    allowed = bool(assignment and assignment.package and assignment.package.allow_ssh)
    return user, allowed


@database_sync_to_async
def _prepare_jail(user: object) -> tuple[str, str, str | None]:
    """Retourne (username OS, home, erreur_ou_None)."""
    from apps.accounts.linux_users import (
        ensure_linux_user,
        jail_username_for,
        linux_user_exists,
        provision_home_via_root,
        user_in_clients_group,
    )
    from apps.files.services import personal_home

    jail = jail_username_for(user)  # type: ignore[arg-type]
    home = str(personal_home(user))  # type: ignore[arg-type]
    err: str | None = None
    try:
        ensure_linux_user(user, home=Path(home))  # type: ignore[arg-type]
    except Exception as exc:  # noqa: BLE001
        logger.warning("ensure_linux_user: %s", exc)
    # Toujours rappeler mkhome si compte/groupe manquant (idempotent côté membership)
    if not linux_user_exists(jail) or not user_in_clients_group(jail):
        try:
            provision_home_via_root(jail)
        except Exception as exc:  # noqa: BLE001
            err = f"compte OS / groupe ({jail}): {exc}"
            logger.warning(err)
    if linux_user_exists(jail) and not user_in_clients_group(jail):
        err = (
            f"{jail} n'est pas dans le groupe vzone-clients "
            "(requis pour le terminal) — sudo bash scripts/ensure-mkhome-sudoers.sh"
        )
    elif not linux_user_exists(jail):
        err = err or f"compte OS absent: {jail}"
    return jail, home, err


def _jail_username(user: object) -> str:
    raw = (
        getattr(user, "system_username", None)
        or getattr(user, "username", None)
        or "user"
    )
    name = str(raw).strip().lower()
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        return "user"
    return name


def _jail_home(user: object, jail: str) -> Path:
    home = (getattr(user, "home_directory", "") or "").strip()
    if home:
        return Path(home)
    root = Path(getattr(settings, "VZONE_HOME_ROOT", "/home"))
    if str(getattr(user, "role", "")) == "administrator":
        return root / "admin"
    return root / jail


class WebTerminalConsumer(AsyncWebsocketConsumer):
    async def connect(self) -> None:
        token = self._extract_token()
        if not token:
            await self.close(code=4401)
            return
        try:
            payload = AccessToken(token)
            user_id = int(payload["user_id"])
        except Exception:  # noqa: BLE001
            await self.close(code=4401)
            return
        user, allowed = await _resolve_user_and_access(user_id)
        if user is None or not allowed:
            await self.close(code=4403)
            return
        if getattr(user, "role", None) == "administrator":
            if not getattr(settings, "VZONE_TERMINAL_ALLOW_ADMIN", False):
                await self.close(code=4403)
                return
        self.user = user

        subs = [str(p) for p in (self.scope.get("subprotocols") or [])]
        if "vzone" in subs:
            await self.accept(subprotocol="vzone")
        else:
            await self.accept()

        try:
            jail, home, prep_err = await _prepare_jail(user)
            self._start_pty(jail=jail, home=Path(home), prep_err=prep_err)
        except Exception as exc:  # noqa: BLE001
            logger.exception("terminal start failed")
            msg = str(exc)[:300]
            await self.send(
                text_data=(
                    "\r\n[terminal] impossible de démarrer le shell\r\n"
                    f"[terminal] {msg}\r\n"
                    "[terminal] Vérifiez: sudo bash /opt/vzone-src/scripts/ensure-mkhome-sudoers.sh\r\n"
                )
            )
            await self.close(code=4500)
            return
        self._reader_task = asyncio.create_task(self._read_pty())

    async def disconnect(self, code: int) -> None:
        task = getattr(self, "_reader_task", None)
        if task:
            task.cancel()
        proc = getattr(self, "_proc", None)
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except OSError:
                pass
        fd = getattr(self, "_master_fd", None)
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        rc = getattr(self, "_rcfile", None)
        if rc:
            try:
                Path(rc).unlink(missing_ok=True)
            except OSError:
                pass

    async def receive(self, text_data: str | None = None, bytes_data=None) -> None:
        if not text_data:
            return
        if text_data.startswith("{"):
            try:
                payload = json.loads(text_data)
            except json.JSONDecodeError:
                payload = {}
            if payload.get("type") == "resize":
                cols = int(payload.get("cols", 120))
                rows = int(payload.get("rows", 30))
                self._resize(cols, rows)
                return
            if payload.get("type") == "input":
                data = str(payload.get("data", ""))
                await self._write_input(data)
                return
        await self._write_input(text_data)

    async def _write_input(self, data: str) -> None:
        fd = getattr(self, "_master_fd", None)
        if fd is None:
            return
        await asyncio.to_thread(os.write, fd, data.encode("utf-8", errors="ignore"))

    async def _read_pty(self) -> None:
        while True:
            fd = getattr(self, "_master_fd", None)
            proc = getattr(self, "_proc", None)
            if fd is None or proc is None:
                return
            if proc.poll() is not None:
                await self.send(text_data=f"\r\n[terminal] session ended ({proc.returncode})\r\n")
                await self.close()
                return
            try:
                chunk = await asyncio.to_thread(os.read, fd, 4096)
            except OSError:
                await self.close()
                return
            if not chunk:
                await self.close()
                return
            await self.send(text_data=chunk.decode("utf-8", errors="ignore"))

    def _write_rcfile(self, *, jail: str, home: Path) -> Path:
        home_q = shlex.quote(str(home))
        jail_q = shlex.quote(jail)
        content = (
            "# V-zone web terminal — identité jail\n"
            f"export HOME={home_q}\n"
            f"export USER={jail_q}\n"
            f"export LOGNAME={jail_q}\n"
            f"export USERNAME={jail_q}\n"
            f"export HOSTNAME={jail_q}\n"
            f"export VZONE_JAIL_USER={jail_q}\n"
            "unset PROMPT_COMMAND\n"
            f"PS1='{jail_q}:\\w\\$ '\n"
            "export PS1\n"
            f"cd {home_q} 2>/dev/null || true\n"
            "umask 0077\n"
        )
        fd, path = tempfile.mkstemp(prefix="vzone-term-", suffix=".bashrc")
        os.close(fd)
        Path(path).write_text(content, encoding="utf-8")
        try:
            os.chmod(path, 0o644)
        except OSError:
            pass
        self._rcfile = path
        return Path(path)

    def _shell_command(self, *, jail: str, shell: str, rcfile: Path) -> list[str]:
        if jail in {"root", "vzone"}:
            raise RuntimeError("jail user privilégié interdit")
        return ["sudo", "-n", "-u", jail, "--", shell, "--noprofile", "--rcfile", str(rcfile), "-i"]

    def _sudo_probe(self, jail: str) -> tuple[bool, str]:
        """Teste sudo -n -u jail /bin/true ; retourne (ok, détail)."""
        last = "sudo indisponible"
        for true_bin in ("/bin/true", "/usr/bin/true"):
            try:
                proc = subprocess.run(
                    ["sudo", "-n", "-u", jail, "--", true_bin],
                    capture_output=True,
                    text=True,
                    timeout=5,
                    check=False,
                )
            except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
                return False, str(exc)
            if proc.returncode == 0:
                return True, ""
            last = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        return False, last

    def _start_pty(
        self,
        *,
        jail: str | None = None,
        home: Path | None = None,
        prep_err: str | None = None,
    ) -> None:
        shell = (getattr(settings, "VZONE_TERMINAL_SHELL", "/bin/bash") or "/bin/bash").strip()
        jail = jail or _jail_username(self.user)
        cwd = home or _jail_home(self.user, jail)
        if not cwd.exists():
            try:
                cwd.mkdir(parents=True, exist_ok=True)
            except OSError:
                cwd = Path("/tmp")

        use_sudo, sudo_err = self._sudo_probe(jail)
        # Dernier recours : re-provision mkhome puis re-test (groupe manquant)
        if not use_sudo:
            try:
                from apps.accounts.linux_users import provision_home_via_root

                provision_home_via_root(jail)
                use_sudo, sudo_err = self._sudo_probe(jail)
            except Exception as exc:  # noqa: BLE001
                sudo_err = f"{sudo_err}; mkhome: {exc}"

        fallback = bool(getattr(settings, "VZONE_TERMINAL_FALLBACK_SAME_UID", False))
        debug = bool(getattr(settings, "DEBUG", False))
        if not use_sudo and not (fallback and debug):
            detail = prep_err or f"sudo -n -u {jail} /bin/true a échoué: {sudo_err}"
            if "no new privileges" in (sudo_err or "").lower():
                detail = (
                    f"{detail} — NoNewPrivileges systemd bloque sudo : "
                    "mettez à jour deploy/systemd/vzone-api.service puis "
                    "systemctl daemon-reload && systemctl restart vzone-api"
                )
            else:
                detail = (
                    f"{detail} — sudo bash /opt/vzone-src/scripts/ensure-mkhome-sudoers.sh "
                    f"&& sudo /usr/local/sbin/vzone-mkhome {jail}"
                )
            raise RuntimeError(detail)

        # cwd doit être accessible au process vzone (avant setuid via sudo)
        start_cwd = str(cwd) if os.access(cwd, os.X_OK) else "/tmp"

        master_fd, slave_fd = pty.openpty()
        self._resize(120, 34, master_fd=master_fd)
        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["HOME"] = str(cwd)
        env["USER"] = jail
        env["LOGNAME"] = jail
        env["USERNAME"] = jail
        env["HOSTNAME"] = jail
        env["VZONE_JAIL_USER"] = jail
        env["PROMPT_COMMAND"] = ""
        # sudo lit souvent un env minimal
        env["PATH"] = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
        rcfile = self._write_rcfile(jail=jail, home=cwd)

        if use_sudo:
            cmd = self._shell_command(jail=jail, shell=shell, rcfile=rcfile)
        else:
            cmd = [shell, "--noprofile", "--rcfile", str(rcfile), "-i"]

        try:
            proc = subprocess.Popen(
                cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=start_cwd,
                env=env,
                preexec_fn=os.setsid,
                close_fds=True,
            )
        except OSError:
            os.close(slave_fd)
            os.close(master_fd)
            raise

        os.close(slave_fd)
        self._master_fd = master_fd
        self._proc = proc

    def _resize(self, cols: int, rows: int, *, master_fd: int | None = None) -> None:
        fd = master_fd if master_fd is not None else getattr(self, "_master_fd", None)
        if fd is None:
            return
        cols = max(40, min(400, cols))
        rows = max(12, min(200, rows))
        size = rows.to_bytes(2, "little") + cols.to_bytes(2, "little") + b"\x00" * 4
        try:
            import fcntl

            fcntl.ioctl(fd, termios.TIOCSWINSZ, size)
        except Exception:  # noqa: BLE001
            pass
        proc = getattr(self, "_proc", None)
        if proc and proc.poll() is None:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGWINCH)
            except OSError:
                pass

    def _extract_token(self) -> str | None:
        # Query string en premier (fiable ; JWT trop long pour Sec-WebSocket-Protocol)
        raw = (self.scope.get("query_string") or b"").decode("utf-8", errors="ignore")
        params = parse_qs(raw)
        token = (params.get("token") or [None])[0]
        if token:
            return token
        headers = {k.decode().lower(): v.decode() for k, v in (self.scope.get("headers") or [])}
        auth = headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            return auth.split(" ", 1)[1].strip() or None
        for proto in self.scope.get("subprotocols") or []:
            p = str(proto)
            if p.startswith("access_token."):
                return p.split(".", 1)[1] or None
        return None
