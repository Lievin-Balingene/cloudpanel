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
def test_uses_ols_engine_respects_flag(settings):
    settings.VZONE_OLS_ENABLED = False
    owner = UserFactory(username="olsowner1")
    domain = create_domain(name="ols-flag.test", owner=owner, web_engine=Domain.WebEngine.NGINX)
    domain.web_engine = Domain.WebEngine.OLS
    assert uses_ols_engine(domain) is False

    settings.VZONE_OLS_ENABLED = True
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
def test_ols_vhconf_contains_lsphp():
    owner = UserFactory(username="olsowner2")
    domain = create_domain(name="lsphp.test", owner=owner)
    text = render_vhconf(domain=domain, docroot="/home/u/public_html", php_version="8.2")
    assert "docRoot" in text
    assert "lsapi:" in text
    assert "autoLoadHtaccess" in text
    block = render_virtualhost_block(domain=domain, docroot="/home/u/public_html")
    assert "virtualhost" in block
    maps = render_listener_maps([domain])
    assert "listener vzoneHttp" in maps
    assert "map                     lsphp.test" in maps


@pytest.mark.django_db
def test_create_ols_domain_rejected_when_disabled(settings):
    settings.VZONE_OLS_ENABLED = False
    owner = UserFactory(username="olsowner3")
    with pytest.raises(VZoneAPIException) as exc:
        create_domain(name="need-ols.test", owner=owner, web_engine=Domain.WebEngine.OLS)
    assert exc.value.default_code == "ols_unavailable"
