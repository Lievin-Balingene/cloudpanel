"""Services monitoring : évaluation de seuils et notifications."""
from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core.exceptions import VZoneAPIException
from apps.core.services import collect_system_metrics
from apps.dashboard.models import ResourceSnapshot
from apps.dashboard.services import service_statuses
from apps.monitoring.models import AlertEvent, AlertRule

logger = logging.getLogger(__name__)


def _compare(value: float, operator: str, threshold: float) -> bool:
    if operator == AlertRule.Operator.GT:
        return value > threshold
    if operator == AlertRule.Operator.GTE:
        return value >= threshold
    if operator == AlertRule.Operator.LT:
        return value < threshold
    if operator == AlertRule.Operator.LTE:
        return value <= threshold
    if operator == AlertRule.Operator.EQ:
        return abs(value - threshold) < 1e-9
    return False


def current_metrics() -> dict[str, Any]:
    """Métriques courantes (live) enrichies des services."""
    metrics = collect_system_metrics()
    load = metrics.get("load_average") or [None, None, None]
    services = {s["name"]: s["active"] for s in service_statuses()}
    return {
        "cpu_percent": float(metrics["cpu"]["percent"]),
        "ram_percent": float(metrics["memory"]["percent"]),
        "disk_percent": float(metrics["disk"]["percent"]),
        "load_1": float(load[0]) if load and load[0] is not None else None,
        "services": services,
        "collected_at": timezone.now().isoformat(),
    }


def latest_snapshot_metrics() -> dict[str, Any] | None:
    snap = ResourceSnapshot.objects.order_by("-collected_at").first()
    if not snap:
        return None
    return {
        "cpu_percent": snap.cpu_percent,
        "ram_percent": snap.ram_percent,
        "disk_percent": snap.disk_percent,
        "load_1": snap.load_1,
        "collected_at": snap.collected_at.isoformat(),
    }


def _metric_value_for_rule(rule: AlertRule, metrics: dict[str, Any]) -> float | None:
    if rule.metric == AlertRule.Metric.SERVICE_DOWN:
        services = metrics.get("services") or {}
        name = (rule.service_name or "").strip().lower()
        if not name:
            return None
        active = services.get(name)
        if active is None:
            # inconnu = considérer down
            return 1.0
        return 0.0 if active else 1.0
    value = metrics.get(rule.metric)
    if value is None:
        return None
    return float(value)


def _rule_triggered(rule: AlertRule, metrics: dict[str, Any]) -> tuple[bool, float | None]:
    value = _metric_value_for_rule(rule, metrics)
    if value is None:
        return False, None
    if rule.metric == AlertRule.Metric.SERVICE_DOWN:
        # threshold 1 = down, operator gte by default
        triggered = _compare(value, rule.operator or AlertRule.Operator.GTE, rule.threshold or 1.0)
        return triggered, value
    return _compare(value, rule.operator, rule.threshold), value


def _in_cooldown(rule: AlertRule) -> bool:
    if not rule.last_triggered_at or rule.cooldown_minutes <= 0:
        return False
    delta = timezone.now() - rule.last_triggered_at
    return delta.total_seconds() < rule.cooldown_minutes * 60


def resolve_recipients(rule: AlertRule) -> list[str]:
    emails = rule.recipient_list()
    if emails:
        return emails
    default = getattr(settings, "VZONE_ALERT_DEFAULT_RECIPIENTS", "") or ""
    emails = [e.strip() for e in default.split(",") if e.strip()]
    if emails:
        return emails
    admin_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""
    return [admin_email] if admin_email and "@" in admin_email else []


def send_alert_email(rule: AlertRule, event: AlertEvent) -> bool:
    recipients = resolve_recipients(rule)
    if not recipients:
        logger.warning("Aucune destinataire pour la règle %s", rule.name)
        return False
    subject = f"[V-zone][{rule.severity.upper()}] {rule.name}"
    body = (
        f"Alerte: {rule.name}\n"
        f"Sévérité: {rule.severity}\n"
        f"Métrique: {rule.metric}\n"
        f"Valeur: {event.metric_value}\n"
        f"Seuil: {rule.operator} {rule.threshold}\n"
        f"Message: {event.message}\n"
        f"Heure: {event.created_at.isoformat()}\n"
    )
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            recipient_list=recipients,
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Échec envoi e-mail alerte %s", rule.pk)
        return False


@transaction.atomic
def create_rule(
    *,
    name: str,
    metric: str,
    operator: str = AlertRule.Operator.GTE,
    threshold: float = 90.0,
    service_name: str = "",
    severity: str = AlertRule.Severity.WARNING,
    cooldown_minutes: int = 30,
    notify_email: bool = True,
    recipients: str = "",
    is_active: bool = True,
    notes: str = "",
    created_by: User | None = None,
) -> AlertRule:
    if metric not in AlertRule.Metric.values:
        raise VZoneAPIException(detail="Métrique invalide.", code="invalid_metric", status_code=400)
    if operator not in AlertRule.Operator.values:
        raise VZoneAPIException(detail="Opérateur invalide.", code="invalid_operator", status_code=400)
    if severity not in AlertRule.Severity.values:
        raise VZoneAPIException(detail="Sévérité invalide.", code="invalid_severity", status_code=400)
    if metric == AlertRule.Metric.SERVICE_DOWN and not service_name.strip():
        raise VZoneAPIException(
            detail="service_name requis pour service_down.",
            code="service_required",
            status_code=400,
        )
    return AlertRule.objects.create(
        name=name.strip(),
        metric=metric,
        operator=operator,
        threshold=float(threshold),
        service_name=service_name.strip().lower(),
        severity=severity,
        cooldown_minutes=max(0, int(cooldown_minutes)),
        notify_email=notify_email,
        recipients=recipients.strip(),
        is_active=is_active,
        notes=notes,
        created_by=created_by,
    )


@transaction.atomic
def update_rule(rule: AlertRule, **fields: Any) -> AlertRule:
    allowed = {
        "name",
        "metric",
        "operator",
        "threshold",
        "service_name",
        "severity",
        "cooldown_minutes",
        "notify_email",
        "recipients",
        "is_active",
        "notes",
    }
    for key, value in fields.items():
        if key not in allowed or value is None:
            continue
        if key == "metric" and value not in AlertRule.Metric.values:
            raise VZoneAPIException(detail="Métrique invalide.", code="invalid_metric", status_code=400)
        if key == "operator" and value not in AlertRule.Operator.values:
            raise VZoneAPIException(detail="Opérateur invalide.", code="invalid_operator", status_code=400)
        if key == "severity" and value not in AlertRule.Severity.values:
            raise VZoneAPIException(detail="Sévérité invalide.", code="invalid_severity", status_code=400)
        if key == "service_name":
            value = str(value).strip().lower()
        if key == "name":
            value = str(value).strip()
        if key == "cooldown_minutes":
            value = max(0, int(value))
        if key == "threshold":
            value = float(value)
        setattr(rule, key, value)
    metric = rule.metric
    if metric == AlertRule.Metric.SERVICE_DOWN and not rule.service_name:
        raise VZoneAPIException(
            detail="service_name requis pour service_down.",
            code="service_required",
            status_code=400,
        )
    rule.save()
    return rule


def delete_rule(rule: AlertRule) -> None:
    rule.delete()


def acknowledge_event(event: AlertEvent, *, user: User) -> AlertEvent:
    if event.status == AlertEvent.Status.RESOLVED:
        raise VZoneAPIException(detail="Alerte déjà résolue.", code="already_resolved", status_code=400)
    event.status = AlertEvent.Status.ACKNOWLEDGED
    event.acknowledged_at = timezone.now()
    event.acknowledged_by = user
    event.save(update_fields=["status", "acknowledged_at", "acknowledged_by", "updated_at"])
    return event


def resolve_event(event: AlertEvent) -> AlertEvent:
    event.status = AlertEvent.Status.RESOLVED
    event.resolved_at = timezone.now()
    event.save(update_fields=["status", "resolved_at", "updated_at"])
    return event


def evaluate_rules(*, metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    """Évalue toutes les règles actives. Retourne un résumé."""
    metrics = metrics or current_metrics()
    fired = 0
    skipped_cooldown = 0
    checked = 0
    for rule in AlertRule.objects.filter(is_active=True):
        checked += 1
        triggered, value = _rule_triggered(rule, metrics)
        if not triggered:
            # auto-resolve open events if condition cleared
            open_events = AlertEvent.objects.filter(
                rule=rule,
                status__in=[AlertEvent.Status.OPEN, AlertEvent.Status.ACKNOWLEDGED],
            )
            for ev in open_events:
                resolve_event(ev)
            continue
        if _in_cooldown(rule):
            skipped_cooldown += 1
            continue
        message = (
            f"{rule.metric}={value} {rule.operator} {rule.threshold}"
            if rule.metric != AlertRule.Metric.SERVICE_DOWN
            else f"Service {rule.service_name} down"
        )
        event = AlertEvent.objects.create(
            rule=rule,
            status=AlertEvent.Status.OPEN,
            metric_value=value,
            message=message,
        )
        rule.last_triggered_at = timezone.now()
        rule.save(update_fields=["last_triggered_at", "updated_at"])
        if rule.notify_email:
            ok = send_alert_email(rule, event)
            if ok:
                event.notified = True
                event.notified_at = timezone.now()
                event.save(update_fields=["notified", "notified_at", "updated_at"])
        fired += 1
    return {
        "checked": checked,
        "fired": fired,
        "skipped_cooldown": skipped_cooldown,
        "metrics": {
            k: metrics.get(k)
            for k in ("cpu_percent", "ram_percent", "disk_percent", "load_1", "collected_at")
        },
    }


def overview_for(_user: User | None = None) -> dict[str, Any]:
    metrics = current_metrics()
    open_count = AlertEvent.objects.filter(status=AlertEvent.Status.OPEN).count()
    ack_count = AlertEvent.objects.filter(status=AlertEvent.Status.ACKNOWLEDGED).count()
    return {
        "rules": AlertRule.objects.count(),
        "rules_active": AlertRule.objects.filter(is_active=True).count(),
        "events_open": open_count,
        "events_acknowledged": ack_count,
        "events_total": AlertEvent.objects.count(),
        "metrics": metrics,
        "latest_snapshot": latest_snapshot_metrics(),
        "cooldown_default": int(getattr(settings, "VZONE_ALERT_COOLDOWN_MINUTES", 30)),
    }
