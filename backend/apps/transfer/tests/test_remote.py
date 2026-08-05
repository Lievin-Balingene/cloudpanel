"""Tests client WHM remote (sans réseau)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

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
    assert "refusé" in str(exc.value.detail).lower() or "no file" in str(exc.value.detail).lower()
