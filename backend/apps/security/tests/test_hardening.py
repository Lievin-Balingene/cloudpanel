"""Tests durcissement sécurité (Git branch/SSRF, tickets terminal)."""
from __future__ import annotations

import pytest

from apps.core.exceptions import VZoneAPIException
from apps.security.git_safe import validate_git_branch, validate_git_remote_url
from apps.security.terminal_tickets import consume_ws_ticket, issue_ws_ticket


def test_git_branch_rejects_option_injection():
    with pytest.raises(VZoneAPIException):
        validate_git_branch("--upload-pack=evil")
    with pytest.raises(VZoneAPIException):
        validate_git_branch("../main")
    with pytest.raises(VZoneAPIException):
        validate_git_branch("main;rm -rf /")
    assert validate_git_branch("feature/foo-bar") == "feature/foo-bar"
    assert validate_git_branch("main") == "main"


def test_git_url_blocks_ssrf_literals():
    with pytest.raises(VZoneAPIException):
        validate_git_remote_url("https://127.0.0.1/repo.git")
    with pytest.raises(VZoneAPIException):
        validate_git_remote_url("https://169.254.169.254/latest/meta-data")
    with pytest.raises(VZoneAPIException):
        validate_git_remote_url("http://localhost/repo.git")
    with pytest.raises(VZoneAPIException):
        validate_git_remote_url("https://user:pass@github.com/x/y.git")
    ok = validate_git_remote_url("https://github.com/example/webapp.git")
    assert ok.startswith("https://")


def test_ws_ticket_roundtrip():
    issued = issue_ws_ticket(user_id=42, mode="root", ttl_sec=60)
    claims = consume_ws_ticket(issued["ticket"])
    assert claims["uid"] == 42
    assert claims["mode"] == "root"
    with pytest.raises(VZoneAPIException):
        consume_ws_ticket(issued["ticket"] + "x")
