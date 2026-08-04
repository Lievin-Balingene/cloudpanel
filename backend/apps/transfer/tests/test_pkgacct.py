"""Tests parser Transfer Tool / pkgacct."""
from __future__ import annotations

import tarfile
from pathlib import Path

import pytest

from apps.transfer.pkgacct import (
    find_account_root,
    inspect_bundle,
    list_userdata_domains,
    parse_dns_zone_file,
)


@pytest.mark.unit
def test_parse_dns_zone_file():
    text = """
$TTL 14400
example.com. IN SOA ns1.example.com. hostmaster.example.com. ( 2024010100 3600 1800 1209600 86400 )
example.com. 14400 IN A 1.2.3.4
www 14400 IN CNAME example.com.
mail 14400 IN A 1.2.3.5
example.com. 14400 IN MX 10 mail.example.com.
example.com. 14400 IN TXT "v=spf1 a -all"
"""
    records = parse_dns_zone_file(text, "example.com")
    types = {r["record_type"] for r in records}
    assert "A" in types
    assert "MX" in types
    assert "TXT" in types
    assert any(r["name"] == "www" and r["record_type"] == "CNAME" for r in records)


@pytest.mark.unit
def test_inspect_minimal_cpmove(tmp_path: Path):
    root = tmp_path / "demo"
    (root / "userdata").mkdir(parents=True)
    (root / "dnszones").mkdir()
    (root / "mysql").mkdir()
    (root / "homedir" / "public_html").mkdir(parents=True)
    (root / "homedir" / "public_html" / "index.html").write_text("hi", encoding="utf-8")
    (root / "userdata" / "main").write_text(
        "main_domain: demo.test\ncontactemail: admin@demo.test\nuser: demo\n",
        encoding="utf-8",
    )
    (root / "userdata" / "demo.test").write_text(
        "servername: demo.test\ndocumentroot: /home/demo/public_html\n",
        encoding="utf-8",
    )
    (root / "mysql" / "demo_wp.sql").write_text("-- dump\n", encoding="utf-8")

    archive = tmp_path / "cpmove-demo.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        tf.add(root, arcname="demo")

    extract_dir = tmp_path / "out"
    extract_dir.mkdir()
    with tarfile.open(archive, "r:gz") as tf:
        tf.extractall(extract_dir)

    account = find_account_root(extract_dir)
    bundle = inspect_bundle(account)
    assert bundle.username == "demo"
    assert bundle.main_domain == "demo.test"
    assert bundle.homedir is not None
    domains = list_userdata_domains(bundle)
    assert any(d["name"] == "demo.test" for d in domains)
