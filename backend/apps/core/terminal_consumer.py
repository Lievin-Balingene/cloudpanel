"""Web terminal consumer (PTY) with package SSH authorization."""
from __future__ import annotations

import asyncio
import json
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


def _jail_username(user: object) -> str:
    """Nom du répertoire jail / identité shell (pas le hostname Contabo)."""
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
        self.user = user
        await self.accept()
        try:
            self._start_pty()
        except Exception:  # noqa: BLE001
            await self.send(text_data="\r\n[terminal] unable to start shell\r\n")
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
        """
        Force le prompt « vzone@<compte_jail> » : bash \\h lit gethostname()
        (ex. vmi3182722 Contabo), pas le compte hébergé.
        """
        home_q = shlex.quote(str(home))
        jail_q = shlex.quote(jail)
        content = (
            "# V-zone web terminal — identité jail (ne pas utiliser \\h OS)\n"
            f"export HOME={home_q}\n"
            f"export USER={jail_q}\n"
            f"export LOGNAME={jail_q}\n"
            f"export USERNAME={jail_q}\n"
            f"export HOSTNAME={jail_q}\n"
            f"export VZONE_JAIL_USER={jail_q}\n"
            "unset PROMPT_COMMAND\n"
            f"PS1='vzone@{jail}:\\w\\$ '\n"
            "export PS1\n"
            f"cd {home_q} 2>/dev/null || true\n"
        )
        fd, path = tempfile.mkstemp(prefix="vzone-term-", suffix=".bashrc")
        os.close(fd)
        Path(path).write_text(content, encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        self._rcfile = path
        return Path(path)

    def _start_pty(self) -> None:
        shell = (getattr(settings, "VZONE_TERMINAL_SHELL", "/bin/bash") or "/bin/bash").strip()
        jail = _jail_username(self.user)
        cwd = _jail_home(self.user, jail)
        if not cwd.exists():
            try:
                cwd.mkdir(parents=True, exist_ok=True)
            except OSError:
                cwd = Path("/tmp")
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
        rcfile = self._write_rcfile(jail=jail, home=cwd)
        proc = subprocess.Popen(
            [shell, "--noprofile", "--rcfile", str(rcfile), "-i"],
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=str(cwd),
            env=env,
            preexec_fn=os.setsid,
            close_fds=True,
        )
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
        raw = (self.scope.get("query_string") or b"").decode("utf-8", errors="ignore")
        params = parse_qs(raw)
        token = (params.get("token") or [None])[0]
        return token
