"""Web terminal consumer — client jailé / admin WHM root."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import pty
import signal
import subprocess
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

JAILTERM = Path("/usr/local/sbin/vzone-jailterm")
ROOTTERM = Path("/usr/local/sbin/vzone-rootterm")


@database_sync_to_async
def _resolve_user_and_access(user_id: int) -> tuple[object | None, bool, str]:
    """Retourne (user, allowed, mode) où mode = root|jail."""
    try:
        user = User.objects.get(pk=user_id, is_active=True, is_suspended=False)
    except User.DoesNotExist:
        return None, False, "jail"
    role = getattr(user, "role", None)
    if role == "administrator":
        allow = bool(getattr(settings, "VZONE_TERMINAL_ALLOW_ADMIN", True))
        return user, allow, "root"
    if role == "reseller":
        # Revendeur : pas de root machine — même modèle que client (jail) si compte OS
        return user, True, "jail"
    assignment = PackageAssignment.objects.filter(user=user).select_related("package").first()
    allowed = bool(assignment and assignment.package and assignment.package.allow_ssh)
    return user, allowed, "jail"


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

        user, allowed, mode = await _resolve_user_and_access(user_id)
        if user is None:
            await self.close(code=4401)
            return

        # Accepter le WS avant tout message d'erreur (sinon navigateur = [erreur WebSocket])
        subs = [str(p) for p in (self.scope.get("subprotocols") or [])]
        if "vzone" in subs:
            await self.accept(subprotocol="vzone")
        else:
            await self.accept()

        if not allowed:
            await self.send(
                text_data=(
                    "\r\n[terminal] accès refusé\r\n"
                    "[terminal] Admin: VZONE_TERMINAL_ALLOW_ADMIN=true dans /etc/vzone/vzone.env\r\n"
                    "[terminal] Client: activez SSH dans le package\r\n"
                )
            )
            await self.close(code=4403)
            return

        self.user = user
        self._mode = mode

        try:
            if mode == "root":
                self._start_root_pty()
            else:
                jail, home, prep_err = await _prepare_jail(user)
                self._start_jail_pty(jail=jail, home=Path(home), prep_err=prep_err)
        except Exception as exc:  # noqa: BLE001
            logger.exception("terminal start failed")
            msg = str(exc)[:400]
            await self.send(
                text_data=(
                    "\r\n[terminal] impossible de démarrer le shell\r\n"
                    f"[terminal] {msg}\r\n"
                    "[terminal] sudo bash /opt/vzone-src/scripts/ensure-mkhome-sudoers.sh\r\n"
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

    def _probe_sudo_helper(self, cmd: list[str]) -> tuple[bool, str]:
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
        except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)
        if proc.returncode == 0:
            return True, ""
        err = (proc.stderr or proc.stdout or "").strip() or f"exit {proc.returncode}"
        return False, err

    def _sudo_fail_detail(self, err: str, *, hint: str) -> str:
        if "no new privileges" in (err or "").lower():
            return (
                f"{err} — NoNewPrivileges systemd : "
                "systemctl daemon-reload && systemctl restart vzone-api"
            )
        return f"{err} — {hint}"

    def _spawn_pty(self, cmd: list[str], *, env: dict[str, str], cwd: str = "/tmp") -> None:
        master_fd, slave_fd = pty.openpty()
        self._resize(120, 34, master_fd=master_fd)
        try:
            proc = subprocess.Popen(
                cmd,
                stdin=slave_fd,
                stdout=slave_fd,
                stderr=slave_fd,
                cwd=cwd,
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

    def _start_root_pty(self) -> None:
        """Shell root WHM (administrators uniquement)."""
        if not ROOTTERM.is_file():
            raise RuntimeError(
                f"{ROOTTERM} absent — sudo bash /opt/vzone-src/scripts/ensure-mkhome-sudoers.sh"
            )
        ok, err = self._probe_sudo_helper(["sudo", "-n", str(ROOTTERM), "--check"])
        if not ok:
            raise RuntimeError(
                self._sudo_fail_detail(
                    err,
                    hint="sudo bash /opt/vzone-src/scripts/ensure-mkhome-sudoers.sh",
                )
            )
        env = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "TERM": "xterm-256color",
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "HOME": "/root",
            "USER": "root",
            "LOGNAME": "root",
        }
        self._spawn_pty(["sudo", "-n", str(ROOTTERM)], env=env, cwd="/root")

    def _start_jail_pty(
        self,
        *,
        jail: str | None = None,
        home: Path | None = None,
        prep_err: str | None = None,
    ) -> None:
        jail = jail or _jail_username(self.user)
        if jail in {"root", "vzone"}:
            raise RuntimeError("compte privilégié interdit dans le terminal client")

        cwd = home or _jail_home(self.user, jail)
        if not cwd.exists():
            try:
                cwd.mkdir(parents=True, exist_ok=True)
            except OSError:
                cwd = Path("/tmp")

        if not JAILTERM.is_file():
            raise RuntimeError(
                f"{JAILTERM} absent — sudo bash /opt/vzone-src/scripts/ensure-mkhome-sudoers.sh"
            )

        ok, jail_err = self._probe_sudo_helper(
            ["sudo", "-n", str(JAILTERM), "--check", jail]
        )
        if not ok:
            try:
                from apps.accounts.linux_users import provision_home_via_root

                provision_home_via_root(jail)
                ok, jail_err = self._probe_sudo_helper(
                    ["sudo", "-n", str(JAILTERM), "--check", jail]
                )
            except Exception as exc:  # noqa: BLE001
                jail_err = f"{jail_err}; mkhome: {exc}"

        if not ok:
            detail = prep_err or f"vzone-jailterm --check {jail}: {jail_err}"
            raise RuntimeError(
                self._sudo_fail_detail(
                    detail,
                    hint=(
                        "sudo bash /opt/vzone-src/scripts/ensure-mkhome-sudoers.sh "
                        f"&& sudo /usr/local/sbin/vzone-mkhome {jail}"
                    ),
                )
            )

        env = {
            "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
            "TERM": "xterm-256color",
            "LANG": os.environ.get("LANG", "C.UTF-8"),
            "HOME": str(cwd),
            "USER": jail,
            "LOGNAME": jail,
        }
        self._spawn_pty(["sudo", "-n", str(JAILTERM), jail], env=env, cwd="/tmp")

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
