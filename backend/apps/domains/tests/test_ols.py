"""Tests OpenLiteSpeed routing (sans installer OLS)."""
from __future__ import annotations

import pytest

from apps.accounts.factories import UserFactory
from apps.core.exceptions import VZoneAPIException
from apps.domains.models import Domain
from apps.domains.ols_vhosts import (
    render_listener_maps,
    render_vhconf,
    render_virtualhost_block,
    uses_ols_engine,
)
from apps.domains.services import create_domain
from apps.domains.vhosts import DomainBackend, _location_body


@pytest.mark.django_db
def test_uses_ols_engine_respects_flag(settings, tmp_path):
    settings.VZONE_OLS_ENABLED = "0"
    owner = UserFactory(username="olsowner1")
    domain = create_domain(name="ols-flag.test", owner=owner, web_engine=Domain.WebEngine.NGINX)
    domain.web_engine = Domain.WebEngine.OLS
    assert uses_ols_engine(domain) is False

    settings.VZONE_OLS_ENABLED = "1"
    # Simulate installed marker
    marker = tmp_path / "ols" / ".installed"
    marker.parent.mkdir(parents=True)
    marker.write_text("1", encoding="utf-8")
    settings.VZONE_DATA_ROOT = tmp_path
    assert uses_ols_engine(domain) is True
    domain.web_engine = Domain.WebEngine.NGINX
    assert uses_ols_engine(domain) is False


@pytest.mark.django_db
def test_render_nginx_proxy_to_ols(settings):
    settings.VZONE_OLS_LISTEN = "127.0.0.1:8088"
    backend = DomainBackend(mode="php", docroot="/home/u/public_html", php_socket="/run/php.sock")
    body = _location_body(backend, use_ols=True)
    assert "proxy_pass http://127.0.0.1:8088" in body
    assert "fastcgi_pass" not in body

    fpm = _location_body(backend, use_ols=False)
    assert "fastcgi_pass" in fpm


@pytest.mark.django_db
def test_ols_vhconf_contains_lsphp(tmp_path):
    owner = UserFactory(username="olsowner2")
    domain = create_domain(name="lsphp.test", owner=owner)
    # Sans index.php → pas de règles front-controller
    text = render_vhconf(domain=domain, docroot=str(tmp_path / "empty"), php_version="8.2")
    assert "docRoot" in text
    assert "lsapi:" in text
    assert "autoLoadHtaccess" in text
    assert "index.php, index.html, index.htm" in text
    assert "END_WP_REWRITE" not in text

    # Avec WordPress markers → rewrite natives
    wp_root = tmp_path / "wp"
    wp_root.mkdir()
    (wp_root / "index.php").write_text("<?php\n", encoding="utf-8")
    (wp_root / "wp-config.php").write_text("<?php\n", encoding="utf-8")
    text_wp = render_vhconf(domain=domain, docroot=str(wp_root), php_version="8.2")
    assert "END_WP_REWRITE" in text_wp
    assert "RewriteRule . /index.php [L]" in text_wp

    block = render_virtualhost_block(domain=domain, docroot="/home/u/public_html")
    assert "virtualhost" in block
    assert "setUIDMode              2" in block
    maps = render_listener_maps([domain])
    assert "listener vzoneHttp" in maps
    assert "map                     lsphp.test" in maps


@pytest.mark.django_db
def test_create_ols_domain_rejected_when_disabled(settings):
    settings.VZONE_OLS_ENABLED = "0"
    owner = UserFactory(username="olsowner3")
    with pytest.raises(VZoneAPIException) as exc:
        create_domain(name="need-ols.test", owner=owner, web_engine=Domain.WebEngine.OLS)
    assert exc.value.default_code == "ols_unavailable"


@pytest.mark.django_db
def test_default_engine_auto_when_installed(settings, tmp_path):
    settings.VZONE_OLS_ENABLED = "auto"
    settings.VZONE_OLS_DEFAULT_ENGINE = True
    settings.VZONE_DATA_ROOT = tmp_path
    marker = tmp_path / "ols" / ".installed"
    marker.parent.mkdir(parents=True)
    marker.write_text("1", encoding="utf-8")
    owner = UserFactory(username="olsowner4")
    domain = create_domain(name="auto-ols.test", owner=owner)
    assert domain.web_engine == Domain.WebEngine.OLS
