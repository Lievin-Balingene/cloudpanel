"""Tests du registre de modules et de la santé."""
from __future__ import annotations

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.core.module_registry import ModuleMeta, ModuleRegistry
from apps.core.services import build_health_status, collect_system_metrics


@pytest.mark.unit
def test_module_registry_register_and_enabled(settings):
    reg = ModuleRegistry()
    reg.register(
        ModuleMeta(
            name="demo",
            label="Demo",
            version="1.0.0",
            description="Module de test",
        )
    )
    settings.VZONE_ENABLED_MODULES = ["demo"]
    assert reg.is_enabled("demo") is True
    assert reg.get("demo").label == "Demo"


@pytest.mark.unit
def test_module_registry_duplicate_raises():
    reg = ModuleRegistry()
    meta = ModuleMeta(name="x", label="X", version="1", description="x")
    reg.register(meta)
    with pytest.raises(ValueError):
        reg.register(meta)


@pytest.mark.unit
def test_collect_system_metrics_shape():
    metrics = collect_system_metrics()
    assert "cpu" in metrics
    assert "memory" in metrics
    assert "disk" in metrics
    assert "percent" in metrics["cpu"]


@pytest.mark.unit
def test_health_status_structure():
    status = build_health_status()
    assert status.status in {"healthy", "degraded"}
    assert "database" in status.checks
    assert "cache" in status.checks


@pytest.mark.integration
@pytest.mark.django_db
def test_health_endpoint_ok():
    client = APIClient()
    response = client.get(reverse("health"))
    assert response.status_code in {200, 503}
    body = response.json()
    assert body["success"] is True
    assert "version" in body["data"]


@pytest.mark.integration
@pytest.mark.django_db
def test_version_endpoint():
    client = APIClient()
    response = client.get(reverse("version"))
    assert response.status_code == 200
    assert response.json()["data"]["product"] == "V-zone Panel"
