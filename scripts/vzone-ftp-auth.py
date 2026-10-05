#!/usr/bin/env python3
"""Auth Pure-FTPd (pure-authd) → comptes FTP V-zone.

Protocole ExtAuth (stdin/stdout) :
  action:auth
  account:...
  password:...
  end

Réponse :
  auth_ok:1
  uid:...
  gid:...
  dir:...
  end
"""
from __future__ import annotations

import os
import pwd
import sys
from pathlib import Path

BACKEND = Path(os.environ.get("VZONE_ROOT", "/opt/vzone")) / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "vzone.settings.production")
os.chdir(str(BACKEND))

import django  # noqa: E402

django.setup()

from apps.ftp.services import authenticate_ftp  # noqa: E402


def _read_request() -> dict[str, str]:
    data: dict[str, str] = {}
    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.rstrip("\n")
        if line == "end":
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        data[key.strip().lower()] = value
    return data


def _reply(**fields: object) -> None:
    for key, value in fields.items():
        sys.stdout.write(f"{key}:{value}\n")
    sys.stdout.write("end\n")
    sys.stdout.flush()


def _uid_gid_for_account(account) -> tuple[int, int]:
    owner = account.owner
    candidates = [
        (getattr(owner, "system_username", None) or "").strip(),
        (owner.username or "").strip(),
        "vzone",
    ]
    for name in candidates:
        if not name:
            continue
        try:
            pw = pwd.getpwnam(name)
            return int(pw.pw_uid), int(pw.pw_gid)
        except KeyError:
            continue
    # Dernier recours : uid du processus
    return os.getuid(), os.getgid()


def main() -> int:
    req = _read_request()
    action = (req.get("action") or "auth").strip().lower()
    if action != "auth":
        _reply(auth_ok=0)
        return 0

    username = (req.get("account") or req.get("username") or "").strip()
    password = req.get("password") or ""
    peer = (req.get("peer") or req.get("remote_ip") or "").strip() or None

    if not username or not password:
        _reply(auth_ok=0)
        return 0

    account = authenticate_ftp(username, password, ip_address=peer)
    if account is None:
        _reply(auth_ok=0)
        return 0

    uid, gid = _uid_gid_for_account(account)
    directory = account.directory or ""
    if not directory or not Path(directory).is_dir():
        _reply(auth_ok=0)
        return 0

    # ./home = chroot dans directory (convention Pure-FTPd)
    _reply(
        auth_ok=1,
        uid=uid,
        gid=gid,
        dir=f"{directory}/./",
        throttling=max(0, int(account.bandwidth_kbs or 0)),
        user_quota_size=max(0, int(account.quota_mb or 0)) * 1024 * 1024,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception:  # noqa: BLE001
        _reply(auth_ok=0)
        raise SystemExit(0)
