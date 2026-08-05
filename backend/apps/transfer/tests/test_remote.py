"""Tests client WHM remote (sans réseau)."""
from __future__ import annotations

import base64
import json
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
import urllib.error

from apps.core.exceptions import VZoneAPIException
from apps.transfer.remote import WhmRemoteClient


def test_whm_host_strips_scheme_and_port():
    c = WhmRemoteClient("https://whm.example.com:2087", port=2087, token="tok")
    assert c.host == "whm.example.com"
    assert c.port == 2087


def test_list_accounts_parses_payload():
    client = WhmRemoteClient("whm.test", token="abc")
    fake = {
        "metadata": {"result": 1},
        "data": {
            "acct": [
                {"user": "alice", "domain": "alice.test", "email": "a@x.com", "plan": "default"},
                {"user": "", "domain": "skip"},
            ]
        },
    }
    with patch.object(client, "_request", return_value=fake):
        accounts = client.list_accounts()
    assert len(accounts) == 1
    assert accounts[0]["user"] == "alice"


def test_download_rejects_json_error(tmp_path: Path):
    client = WhmRemoteClient("whm.test", token="abc", insecure_ssl=True)
    dest = tmp_path / "cpmove.tar.gz"

    class FakeResp:
        headers = {"Content-Type": "application/json"}

        def read(self, n: int = -1):
            payload = json.dumps({"metadata": {"result": 0, "reason": "no file"}}).encode()
            if not hasattr(self, "_sent"):
                self._sent = True
                return payload if n < 0 else payload[:n]
            return b""

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with patch("urllib.request.urlopen", return_value=FakeResp()):
        with pytest.raises(VZoneAPIException) as exc:
            client._stream_download("https://whm.test:2087/x", dest)
    detail = str(exc.value.detail).lower()
    assert "no file" in detail or "refus" in detail or "trop petite" in detail or "json" in detail


def test_auth_falls_back_to_basic_password():
    """Si Authorization: whm échoue en 403, Basic password doit réussir."""
    client = WhmRemoteClient("whm.test", user="root", token="Tempo2025@", insecure_ssl=True)
    calls: list[str] = []

    def fake_urlopen(req, timeout=None, context=None):
        auth = req.get_header("Authorization") or ""
        calls.append(auth)
        if auth.startswith("whm ") or auth.startswith("WHM "):
            err = urllib.error.HTTPError(
                url=req.full_url,
                code=403,
                msg="Forbidden",
                hdrs=None,
                fp=BytesIO(b"denied"),
            )
            raise err

        expected = "Basic " + base64.b64encode(b"root:Tempo2025@").decode("ascii")
        assert auth == expected

        class Ok:
            def read(self):
                return json.dumps({"metadata": {"result": 1}, "data": {"version": "128"}}).encode()

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        return Ok()

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        data = client.ensure_auth()
    assert client.auth_method == "basic-password"
    assert data["metadata"]["result"] == 1
    assert any(c.startswith("Basic ") for c in calls)


def test_auth_candidates_include_basic_and_whm():
    c = WhmRemoteClient("h", user="root", token="secret")
    names = [n for n, _ in c._auth_candidates()]
    assert "whm-token" in names
    assert "basic-password" in names


def test_resolve_cpmove_paths_from_api():
    client = WhmRemoteClient("whm.test", token="abc")
    client._auth_header_value = "whm root:abc"
    client.auth_method = "whm-token"
    fake = {
        "metadata": {"result": 1},
        "data": {
            "quickrestore_files": [
                {"user": "alice", "file": "cpmove-alice.tar.gz", "path": "/home"},
                {"user": "bob", "file": "cpmove-bob.tar.gz", "path": "/home2"},
            ]
        },
    }
    with patch.object(client, "_request", return_value=fake):
        paths = client.resolve_cpmove_paths("alice")
    assert paths[0] == "/home/alice/cpmove-alice.tar.gz"
    assert "/home/cpmove-alice.tar.gz" in paths


def test_download_cpmove_uses_scp_when_password_auth(tmp_path: Path):
    client = WhmRemoteClient(
        "whm.test",
        user="root",
        token="secret",
        insecure_ssl=True,
        ssh_port=2222,
    )
    client._auth_header_value = "Basic x"
    client.auth_method = "basic-password"
    dest = tmp_path / "cpmove.tar.gz"
    dest.write_bytes(b"\x1f\x8b" + b"x" * 128)

    with patch.object(client, "check_ssh_access", return_value={"ok": True, "message": "SSH OK"}):
        with patch.object(client, "resolve_cpmove_paths", return_value=["/home/cpmove-u.tar.gz"]):
            with patch.object(client, "_scp_download_candidates", return_value=130) as scp:
                out = client.download_cpmove("u", dest)
    scp.assert_called_once()
    assert out == dest


def test_rel_to_account_home_cpmove_in_home_root():
    client = WhmRemoteClient("whm.test", token="abc")
    with patch.object(client, "account_homedir", return_value="/home/bienve"):
        assert client._rel_to_account_home("bienve", "/home/cpmove-bienve.tar.gz") == "../cpmove-bienve.tar.gz"
        assert client._rel_to_account_home("bienve", "/home/bienve/backup-x.tar.gz") == "backup-x.tar.gz"
        assert (
            client._rel_to_account_home("bienve", "/home/bienve/cpmove-bienve.tar.gz")
            == "cpmove-bienve.tar.gz"
        )
    with patch.object(client, "account_homedir", return_value="/home2/bienve"):
        assert (
            client._rel_to_account_home("bienve", "/home2/bienve/cpmove-bienve.tar.gz")
            == "cpmove-bienve.tar.gz"
        )


def test_start_background_pkgacct_uses_account_homedir():
    client = WhmRemoteClient("whm.test", token="abc")
    fake = {"metadata": {"result": 1}, "data": {"session_id": "sess-1"}}
    with patch.object(client, "account_homedir", return_value="/home2/bienve"):
        with patch.object(client, "_request", return_value=fake) as req:
            sid = client.start_background_pkgacct("bienve")
    assert sid == "sess-1"
    assert req.call_args[0][1]["tarroot"] == "/home2/bienve"


def test_resolve_cpmove_paths_prefers_account_homedir():
    client = WhmRemoteClient("whm.test", token="abc")
    with patch.object(client, "account_homedir", return_value="/home2/alice"):
        with patch.object(client, "list_cparchive_files", side_effect=VZoneAPIException(detail="x", code="x")):
            paths = client.resolve_cpmove_paths("alice")
    assert paths[0] == "/home2/alice/cpmove-alice.tar.gz"


def test_download_via_public_site_copies_outside_home_first(tmp_path: Path):
    client = WhmRemoteClient("whm.test", token="abc", insecure_ssl=True)
    dest = tmp_path / "cpmove.tar.gz"
    dest.write_bytes(b"\x1f\x8b" + b"x" * 128)

    with patch.object(client, "account_domain", return_value="example.test"):
        with patch.object(client, "account_homedir", return_value="/home/bienve"):
            with patch.object(
                client,
                "_copy_cpmove_into_homedir",
                return_value="/home/bienve/cpmove-bienve.tar.gz",
            ) as copy:
                with patch.object(client, "_cpanel_fileop") as fileop:
                    with patch.object(client, "_http_download_file", return_value=256):
                        size = client._download_via_public_site(
                            "bienve", "/home/cpmove-bienve.tar.gz", dest
                        )
    copy.assert_called_once()
    fileop.assert_called()
    assert size == 256


def test_download_cpmove_falls_back_to_public_site(tmp_path: Path):
    client = WhmRemoteClient("whm.test", token="secret", insecure_ssl=True)
    client.auth_method = "basic-password"
    dest = tmp_path / "cpmove.tar.gz"

    with patch.object(client, "check_ssh_access", return_value={"ok": False, "message": "SSH down"}):
        with patch.object(
            client,
            "_download_via_whm_root_basic",
            side_effect=VZoneAPIException(detail="root fail", code="whm_download_failed"),
        ):
            with patch.object(client, "_http_download_candidates", side_effect=VZoneAPIException(detail="http fail", code="whm_download_failed")):
                with patch.object(client, "resolve_cpmove_paths", return_value=["/home/cpmove-u.tar.gz"]):
                    with patch.object(client, "_download_via_public_site", return_value=256) as pub:
                        out = client.download_cpmove("u", dest)
    pub.assert_called_once()
    assert out == dest


def test_download_cpmove_falls_back_to_http_when_ssh_down(tmp_path: Path):
    client = WhmRemoteClient("whm.test", token="secret", insecure_ssl=True)
    client.auth_method = "basic-password"
    dest = tmp_path / "cpmove.tar.gz"

    with patch.object(client, "check_ssh_access", return_value={"ok": False, "message": "SSH down"}):
        with patch.object(
            client,
            "_download_via_whm_root_basic",
            side_effect=VZoneAPIException(detail="root fail", code="whm_download_failed"),
        ):
            with patch.object(client, "_http_download_candidates", return_value=128) as http:
                out = client.download_cpmove("u", dest)
    http.assert_called_once()
    assert out == dest


def test_package_and_fetch_uses_homedir_backup_when_ssh_blocked(tmp_path: Path):
    client = WhmRemoteClient("whm.test", token="secret", insecure_ssl=True)
    dest = tmp_path / "cpmove.tar.gz"
    with patch.object(client, "check_ssh_access", return_value={"ok": False, "message": "timeout"}):
        with patch.object(client, "_package_homedir_backup", return_value="/home/u/backup-x.tar.gz") as pkg:
            with patch.object(client, "download_cpmove", return_value=dest) as dl:
                out = client.package_and_fetch("u", dest)
    pkg.assert_called_once()
    dl.assert_called_once()
    assert dl.call_args.kwargs.get("extra_paths") == ["/home/u/backup-x.tar.gz"]
    assert out == dest


def test_check_ssh_access_reports_timeout():
    client = WhmRemoteClient("whm.test", token="secret")
    client.auth_method = "basic-password"
    with patch("socket.create_connection", side_effect=TimeoutError("timed out")):
        result = client.check_ssh_access()
    assert result["ok"] is False
    assert "injoignable" in result["message"].lower() or "timed out" in result["message"].lower()
