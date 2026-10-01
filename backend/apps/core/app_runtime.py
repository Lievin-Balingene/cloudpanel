"""Helpers runtime partagés (ports, kill, process) pour apps Python / Node."""
from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)

KILL_PORT = Path("/usr/local/sbin/vzone-kill-port")


def process_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def port_listening(port: int, host: str = "127.0.0.1", timeout: float = 0.4) -> bool:
    if port <= 0:
        return False
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def wait_port(port: int, *, timeout_s: float = 15.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if port_listening(port):
            return True
        time.sleep(0.25)
    return False


def pids_listening_on_port(port: int) -> list[int]:
    """PIDs qui écoutent sur le port TCP (ss / lsof / fuser)."""
    if port <= 0:
        return []
    pids: set[int] = set()
    try:
        out = subprocess.run(
            ["ss", "-ltnp", f"sport = :{port}"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        ).stdout or ""
        for m in re.finditer(r"pid=(\d+)", out):
            pids.add(int(m.group(1)))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pass
    if not pids:
        try:
            out = subprocess.run(
                ["lsof", "-t", f"-iTCP:{port}", "-sTCP:LISTEN"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            ).stdout or ""
            for line in out.splitlines():
                line = line.strip()
                if line.isdigit():
                    pids.add(int(line))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    if not pids:
        try:
            out = subprocess.run(
                ["fuser", f"{port}/tcp"],
                capture_output=True,
                text=True,
                timeout=8,
                check=False,
            )
            blob = f"{out.stdout or ''} {out.stderr or ''}"
            for m in re.finditer(r"(\d+)", blob):
                pids.add(int(m.group(1)))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    return sorted(pids)


def kill_app_pid(pid: int | None) -> None:
    if not pid:
        return
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(pid, sig)
        except (ProcessLookupError, PermissionError, OSError):
            try:
                os.kill(pid, sig)
            except (ProcessLookupError, PermissionError, OSError):
                return
        time.sleep(0.35)
        if not process_alive(pid):
            return


def free_listen_port(port: int) -> None:
    """Tue tout process qui occupe encore le port (orphans gunicorn/node)."""
    if port <= 0:
        return
    if KILL_PORT.is_file():
        try:
            proc = subprocess.run(
                ["sudo", "-n", str(KILL_PORT), str(int(port))],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if proc.returncode == 0:
                logger.info("kill-port %s OK: %s", port, (proc.stdout or "").strip())
            else:
                logger.warning(
                    "kill-port %s rc=%s out=%s err=%s",
                    port,
                    proc.returncode,
                    (proc.stdout or "")[-300:],
                    (proc.stderr or "")[-300:],
                )
        except (OSError, subprocess.TimeoutExpired) as exc:
            logger.warning("kill-port %s failed: %s", port, exc)
    for pid in pids_listening_on_port(port):
        logger.info("Libération port %s : kill pid %s (fallback)", port, pid)
        kill_app_pid(pid)
    try:
        subprocess.run(
            ["fuser", "-k", f"{port}/tcp"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        pass
    deadline = time.time() + 4.0
    while time.time() < deadline and port_listening(port):
        time.sleep(0.2)
    if port_listening(port):
        leftover = pids_listening_on_port(port)
        logger.error("Port %s toujours occupé après kill (pids=%s)", port, leftover)


def our_process_owns_port(master_pid: int, port: int) -> bool:
    """True si master_pid (ou un de ses enfants) écoute sur port."""
    listeners = set(pids_listening_on_port(port))
    if not listeners:
        return process_alive(master_pid) and port_listening(port)
    if master_pid in listeners:
        return True
    try:
        for pid in listeners:
            try:
                stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8", errors="replace")
                after = stat.rsplit(")", 1)[-1].strip().split()
                ppid = int(after[1]) if len(after) > 1 else -1
                if ppid == master_pid or pid == master_pid:
                    return True
                try:
                    if os.getpgid(pid) == os.getpgid(master_pid):
                        return True
                except OSError:
                    pass
            except (OSError, ValueError, IndexError):
                continue
    except Exception:  # noqa: BLE001
        logger.debug("owns_port probe skip", exc_info=True)
    return False


def normalize_app_domain(value: str) -> str:
    """Normalise Application URL (sans schéma / chemin / www)."""
    v = (value or "").strip().lower()
    for prefix in ("https://", "http://"):
        if v.startswith(prefix):
            v = v[len(prefix) :]
    v = v.split("/")[0].split("?")[0].strip(".")
    if v.startswith("www."):
        v = v[4:]
    return v
