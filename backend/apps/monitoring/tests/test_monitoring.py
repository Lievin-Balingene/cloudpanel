"""Tests module Monitoring."""
from __future__ import annotations

import pytest
from django.core import mail
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.accounts.models import User
from apps.monitoring.models import AlertEvent, AlertRule
from apps.monitoring.services import create_rule, evaluate_rules


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def admin_user(db):
    return UserFactory(
        username="monadmin",
        password="TestPassword123!",
        role=User.Role.ADMINISTRATOR,
        is_staff=True,
    )


@pytest.mark.integration
@pytest.mark.django_db
def test_create_rule_and_evaluate(api: APIClient, admin_user, settings):
    settings.DEFAULT_FROM_EMAIL = "alerts@vzone.local"
    settings.VZONE_ALERT_DEFAULT_RECIPIENTS = "ops@vzone.local"
    api.force_authenticate(user=admin_user)

    created = api.post(
        reverse("monitoring-rule-list"),
        {
            "name": "CPU élevé",
            "metric": "cpu_percent",
            "operator": "gte",
            "threshold": 0,
            "severity": "warning",
            "cooldown_minutes": 0,
            "notify_email": True,
            "recipients": "ops@vzone.local",
        },
        format="json",
    )
    assert created.status_code == 201
    assert created.json()["data"]["name"] == "CPU élevé"

    evaluated = api.post(reverse("monitoring-evaluate"), {}, format="json")
    assert evaluated.status_code == 200
    data = evaluated.json()["data"]
    assert data["checked"] >= 1
    assert data["fired"] >= 1
    assert AlertEvent.objects.filter(status=AlertEvent.Status.OPEN).count() >= 1
    assert len(mail.outbox) >= 1

    overview = api.get(reverse("monitoring-overview"))
    assert overview.status_code == 200
    assert overview.json()["data"]["rules"] >= 1
    assert overview.json()["data"]["events_open"] >= 1


@pytest.mark.integration
@pytest.mark.django_db
def test_acknowledge_and_resolve(api: APIClient, admin_user, settings):
    settings.VZONE_ALERT_DEFAULT_RECIPIENTS = "ops@vzone.local"
    rule = create_rule(
        name="RAM",
        metric="ram_percent",
        threshold=0,
        cooldown_minutes=0,
        notify_email=False,
        created_by=admin_user,
    )
    evaluate_rules(metrics={"cpu_percent": 10, "ram_percent": 95, "disk_percent": 10, "load_1": 0.1, "services": {}})
    event = AlertEvent.objects.filter(rule=rule).first()
    assert event is not None

    api.force_authenticate(user=admin_user)
    ack = api.post(reverse("monitoring-event-ack", kwargs={"pk": event.pk}))
    assert ack.status_code == 200
    assert ack.json()["data"]["status"] == "acknowledged"

    resolved = api.post(reverse("monitoring-event-resolve", kwargs={"pk": event.pk}))
    assert resolved.status_code == 200
    assert resolved.json()["data"]["status"] == "resolved"


@pytest.mark.integration
@pytest.mark.django_db
def test_client_forbidden(api: APIClient):
    client_user = UserFactory(username="monclient", role=User.Role.CLIENT)
    api.force_authenticate(user=client_user)
    resp = api.get(reverse("monitoring-overview"))
    assert resp.status_code == 403


@pytest.mark.unit
@pytest.mark.django_db
def test_cooldown_skips(settings):
    settings.VZONE_ALERT_DEFAULT_RECIPIENTS = "ops@vzone.local"
    rule = create_rule(
        name="Disk",
        metric="disk_percent",
        threshold=0,
        cooldown_minutes=60,
        notify_email=False,
    )
    metrics = {"cpu_percent": 1, "ram_percent": 1, "disk_percent": 99, "load_1": 0.1, "services": {}}
    first = evaluate_rules(metrics=metrics)
    assert first["fired"] == 1
    second = evaluate_rules(metrics=metrics)
    assert second["fired"] == 0
    assert second["skipped_cooldown"] >= 1
    assert AlertEvent.objects.filter(rule=rule).count() == 1


@pytest.mark.unit
@pytest.mark.django_db
def test_service_down_rule(settings):
    settings.VZONE_ALERT_DEFAULT_RECIPIENTS = "ops@vzone.local"
    create_rule(
        name="Redis down",
        metric="service_down",
        service_name="redis",
        threshold=1,
        operator="gte",
        cooldown_minutes=0,
        notify_email=False,
    )
    result = evaluate_rules(
        metrics={
            "cpu_percent": 1,
            "ram_percent": 1,
            "disk_percent": 1,
            "load_1": 0.1,
            "services": {"redis": False, "nginx": True},
        }
    )
    assert result["fired"] == 1
