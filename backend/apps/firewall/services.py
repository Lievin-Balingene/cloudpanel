"""Services firewall / Fail2Ban (mock ou live CLI)."""
from __future__ import annotations

import ipaddress
import json
import logging
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.core.exceptions import VZoneAPIException
from apps.firewall.models import Fail2BanBan, Fail2BanJail, FirewallEventLog, FirewallRule

logger = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[\w .\-]{2,120}$")
DEFAULT_JAILS = (
    ("sshd", "sshd", 5, 600, 3600),
    ("nginx-http-auth", "nginx-http-auth", 5, 600, 3600),
    ("postfix", "postfix", 5, 600, 3600),
)


def provision_mode() -> str:
    mode = getattr(settings, "VZONE_FIREWALL_PROVISION_MODE", "auto").lower()
    if mode not in {"auto", "live", "mock"}:
        mode = "auto"
    if mode == "auto":
        if shutil.which(fail2ban_binary()) or shutil.which(iptables_binary()):
            return "live"
        return "mock"
    return mode


def config_root() -> Path:
    root = Path(
        getattr(settings, "VZONE_FIREWALL_CONFIG_DIR", None)
        or (Path(settings.VZONE_DATA_ROOT) / "firewall")
    )
    root.mkdir(parents=True, exist_ok=True)
    (root / "rules").mkdir(exist_ok=True)
    (root / "fail2ban").mkdir(exist_ok=True)
    return root


def iptables_binary() -> str:
    configured = getattr(settings, "VZONE_IPTABLES_BIN", "") or ""
    if configured:
        return configured
    return shutil.which("iptables") or "iptables"


def fail2ban_binary() -> str:
    configured = getattr(settings, "VZONE_FAIL2BAN_BIN", "") or ""
    if configured:
        return configured
    return shutil.which("fail2ban-client") or "fail2ban-client"


def _add_log(
    event_type: str,
    *,
    success: bool = True,
    message: str = "",
    actor: User | None = None,
) -> None:
    FirewallEventLog.objects.create(
        event_type=event_type,
        success=success,
        message=message[:4000],
        actor=actor,
    )


def _validate_cidr(value: str, *, field: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    try:
        ipaddress.ip_network(value, strict=False)
    except ValueError as exc:
        raise VZoneAPIException(
            detail=f"{field} invalide.",
            code="invalid_cidr",
            status_code=400,
        ) from exc
    return value


def _validate_ports(port_start: int | None, port_end: int | None) -> tuple[int | None, int | None]:
    if port_start is None and port_end is None:
        return None, None
    if port_start is None:
        port_start = port_end
    if port_end is None:
        port_end = port_start
    port_start = int(port_start)
    port_end = int(port_end)
    if not (1 <= port_start <= 65535 and 1 <= port_end <= 65535):
        raise VZoneAPIException(detail="Port hors plage.", code="invalid_port", status_code=400)
    if port_end < port_start:
        raise VZoneAPIException(detail="port_end < port_start.", code="invalid_port", status_code=400)
    return port_start, port_end


def write_rule_meta(rule: FirewallRule) -> Path:
    path = config_root() / "rules" / f"{rule.pk}.json"
    path.write_text(
        json.dumps(
            {
                "id": rule.pk,
                "name": rule.name,
                "action": rule.action,
                "protocol": rule.protocol,
                "direction": rule.direction,
                "port_start": rule.port_start,
                "port_end": rule.port_end,
                "source_cidr": rule.source_cidr,
                "dest_cidr": rule.dest_cidr,
                "priority": rule.priority,
                "is_enabled": rule.is_enabled,
                "is_applied": rule.is_applied,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _run_cmd(args: list[str], *, timeout: int = 30) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, check=True, capture_output=True, text=True, timeout=timeout)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        stderr = getattr(exc, "stderr", None) or str(exc)
        raise VZoneAPIException(
            detail="Échec commande firewall.",
            code="firewall_cmd_failed",
            status_code=502,
            extra={"stderr": stderr, "cmd": args},
        ) from exc


def _iptables_args(rule: FirewallRule, *, delete: bool = False) -> list[str]:
    chain = "INPUT" if rule.direction == FirewallRule.Direction.IN else "OUTPUT"
    action = "ACCEPT" if rule.action == FirewallRule.Action.ALLOW else "DROP"
    args = [iptables_binary(), "-D" if delete else "-A", chain]
    if rule.protocol != FirewallRule.Protocol.ANY:
        args.extend(["-p", rule.protocol])
    if rule.source_cidr:
        args.extend(["-s", rule.source_cidr])
    if rule.dest_cidr:
        args.extend(["-d", rule.dest_cidr])
    if rule.port_start is not None:
        if rule.port_end and rule.port_end != rule.port_start:
            args.extend(["--dport", f"{rule.port_start}:{rule.port_end}"])
        else:
            args.extend(["--dport", str(rule.port_start)])
    args.extend(["-j", action, "-m", "comment", "--comment", f"vzone:{rule.pk}"])
    return args


@transaction.atomic
def create_rule(
    *,
    name: str,
    action: str = FirewallRule.Action.ALLOW,
    protocol: str = FirewallRule.Protocol.TCP,
    direction: str = FirewallRule.Direction.IN,
    port_start: int | None = None,
    port_end: int | None = None,
    source_cidr: str = "",
    dest_cidr: str = "",
    priority: int = 100,
    is_enabled: bool = True,
    notes: str = "",
    apply_now: bool = False,
    created_by: User | None = None,
) -> FirewallRule:
    name = (name or "").strip()
    if not NAME_RE.match(name):
        raise VZoneAPIException(detail="Nom de règle invalide.", code="invalid_name", status_code=400)
    if action not in FirewallRule.Action.values:
        raise VZoneAPIException(detail="Action invalide.", code="invalid_action", status_code=400)
    if protocol not in FirewallRule.Protocol.values:
        raise VZoneAPIException(detail="Protocole invalide.", code="invalid_protocol", status_code=400)
    if direction not in FirewallRule.Direction.values:
        raise VZoneAPIException(detail="Direction invalide.", code="invalid_direction", status_code=400)
    port_start, port_end = _validate_ports(port_start, port_end)
    source_cidr = _validate_cidr(source_cidr, field="source_cidr")
    dest_cidr = _validate_cidr(dest_cidr, field="dest_cidr")

    rule = FirewallRule.objects.create(
        name=name,
        action=action,
        protocol=protocol,
        direction=direction,
        port_start=port_start,
        port_end=port_end,
        source_cidr=source_cidr,
        dest_cidr=dest_cidr,
        priority=max(0, int(priority)),
        is_enabled=is_enabled,
        notes=notes,
        created_by=created_by,
    )
    write_rule_meta(rule)
    _add_log(FirewallEventLog.Event.RULE_CREATE, message=f"created {rule.name}", actor=created_by)
    if apply_now and is_enabled:
        apply_rule(rule, actor=created_by)
    return rule


@transaction.atomic
def update_rule(rule: FirewallRule, **fields: Any) -> FirewallRule:
    allowed = {
        "name",
        "action",
        "protocol",
        "direction",
        "port_start",
        "port_end",
        "source_cidr",
        "dest_cidr",
        "priority",
        "is_enabled",
        "notes",
    }
    port_start = fields.get("port_start", rule.port_start)
    port_end = fields.get("port_end", rule.port_end)
    if "port_start" in fields or "port_end" in fields:
        port_start, port_end = _validate_ports(port_start, port_end)
        fields["port_start"] = port_start
        fields["port_end"] = port_end
    for key, value in fields.items():
        if key not in allowed or value is None and key not in {"port_start", "port_end", "notes"}:
            if key in {"port_start", "port_end"} and value is None:
                setattr(rule, key, None)
            continue
        if key == "name":
            value = str(value).strip()
            if not NAME_RE.match(value):
                raise VZoneAPIException(detail="Nom invalide.", code="invalid_name", status_code=400)
        if key == "source_cidr":
            value = _validate_cidr(str(value), field="source_cidr")
        if key == "dest_cidr":
            value = _validate_cidr(str(value), field="dest_cidr")
        if key in {"action", "protocol", "direction"}:
            choices = {
                "action": FirewallRule.Action.values,
                "protocol": FirewallRule.Protocol.values,
                "direction": FirewallRule.Direction.values,
            }[key]
            if value not in choices:
                raise VZoneAPIException(detail=f"{key} invalide.", code=f"invalid_{key}", status_code=400)
        if key == "priority":
            value = max(0, int(value))
        setattr(rule, key, value)
    rule.is_applied = False
    rule.save()
    write_rule_meta(rule)
    _add_log(FirewallEventLog.Event.RULE_UPDATE, message=f"updated {rule.name}")
    return rule


def apply_rule(rule: FirewallRule, *, actor: User | None = None) -> FirewallRule:
    if not rule.is_enabled:
        raise VZoneAPIException(detail="Règle désactivée.", code="disabled", status_code=400)
    try:
        if provision_mode() == "mock":
            write_rule_meta(rule)
            (config_root() / "rules" / f"{rule.pk}.applied").write_text("1", encoding="utf-8")
        else:
            _run_cmd(_iptables_args(rule, delete=False))
        rule.is_applied = True
        rule.last_error = ""
        rule.save(update_fields=["is_applied", "last_error", "updated_at"])
        write_rule_meta(rule)
        _add_log(FirewallEventLog.Event.RULE_APPLY, message=f"applied {rule.name}", actor=actor)
    except VZoneAPIException as exc:
        rule.last_error = str(exc.detail)
        rule.save(update_fields=["last_error", "updated_at"])
        _add_log(
            FirewallEventLog.Event.FAIL,
            success=False,
            message=str(exc.detail),
            actor=actor,
        )
        raise
    return rule


@transaction.atomic
def delete_rule(rule: FirewallRule, *, actor: User | None = None) -> None:
    try:
        if provision_mode() == "live" and rule.is_applied:
            try:
                _run_cmd(_iptables_args(rule, delete=True))
            except VZoneAPIException:
                logger.warning("Impossible de retirer la règle iptables %s", rule.pk)
        meta = config_root() / "rules" / f"{rule.pk}.json"
        applied = config_root() / "rules" / f"{rule.pk}.applied"
        meta.unlink(missing_ok=True)
        applied.unlink(missing_ok=True)
        _add_log(FirewallEventLog.Event.RULE_DELETE, message=f"deleted {rule.name}", actor=actor)
        rule.delete()
    except VZoneAPIException as exc:
        _add_log(FirewallEventLog.Event.FAIL, success=False, message=str(exc.detail), actor=actor)
        raise


def ensure_default_jails() -> None:
    for name, filter_name, max_retry, find_time, ban_time in DEFAULT_JAILS:
        Fail2BanJail.objects.get_or_create(
            name=name,
            defaults={
                "filter_name": filter_name,
                "max_retry": max_retry,
                "find_time": find_time,
                "ban_time": ban_time,
                "is_enabled": True,
            },
        )


def sync_fail2ban(*, actor: User | None = None) -> list[Fail2BanJail]:
    ensure_default_jails()
    jails = list(Fail2BanJail.objects.all())
    if provision_mode() == "mock":
        state_path = config_root() / "fail2ban" / "state.json"
        state = {}
        if state_path.exists():
            state = json.loads(state_path.read_text(encoding="utf-8"))
        for jail in jails:
            bans = Fail2BanBan.objects.filter(jail=jail, status=Fail2BanBan.Status.ACTIVE).count()
            jail.currently_banned = bans
            jail.total_banned = max(jail.total_banned, bans)
            jail.save(update_fields=["currently_banned", "total_banned", "updated_at"])
            state[jail.name] = {
                "currently_banned": jail.currently_banned,
                "total_banned": jail.total_banned,
                "enabled": jail.is_enabled,
            }
        state_path.write_text(json.dumps(state, indent=2), encoding="utf-8")
        _add_log(FirewallEventLog.Event.SYNC, message="mock fail2ban sync", actor=actor)
        return jails

    # live: fail2ban-client status
    try:
        result = _run_cmd([fail2ban_binary(), "status"])
        # parse jail list from output
        jail_names: list[str] = []
        for line in (result.stdout or "").splitlines():
            if "Jail list:" in line:
                part = line.split(":", 1)[1]
                jail_names = [j.strip() for j in part.replace(",", " ").split() if j.strip()]
        for name in jail_names:
            jail, _ = Fail2BanJail.objects.get_or_create(name=name, defaults={"filter_name": name})
            try:
                detail = _run_cmd([fail2ban_binary(), "status", name])
                banned = 0
                for line in (detail.stdout or "").splitlines():
                    if "Currently banned:" in line:
                        banned = int(line.split(":")[-1].strip() or 0)
                    if "Total banned:" in line:
                        jail.total_banned = int(line.split(":")[-1].strip() or 0)
                jail.currently_banned = banned
                jail.is_enabled = True
                jail.save()
            except VZoneAPIException:
                logger.warning("Impossible de lire le status de la jail %s", name)
        jails = list(Fail2BanJail.objects.all())
        _add_log(FirewallEventLog.Event.SYNC, message=f"synced {len(jail_names)} jails", actor=actor)
    except VZoneAPIException as exc:
        _add_log(FirewallEventLog.Event.FAIL, success=False, message=str(exc.detail), actor=actor)
        raise
    return jails


def ban_ip(
    *,
    ip_address: str,
    jail_name: str = "sshd",
    reason: str = "",
    actor: User | None = None,
) -> Fail2BanBan:
    try:
        ipaddress.ip_address(ip_address)
    except ValueError as exc:
        raise VZoneAPIException(detail="Adresse IP invalide.", code="invalid_ip", status_code=400) from exc
    ensure_default_jails()
    jail, _ = Fail2BanJail.objects.get_or_create(name=jail_name, defaults={"filter_name": jail_name})
    existing = Fail2BanBan.objects.filter(
        jail=jail, ip_address=ip_address, status=Fail2BanBan.Status.ACTIVE
    ).first()
    if existing:
        return existing

    try:
        if provision_mode() == "mock":
            path = config_root() / "fail2ban" / "bans.jsonl"
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"jail": jail.name, "ip": ip_address, "action": "ban"}) + "\n")
        else:
            _run_cmd([fail2ban_binary(), "set", jail.name, "banip", ip_address])
        ban = Fail2BanBan.objects.create(
            jail=jail,
            ip_address=ip_address,
            status=Fail2BanBan.Status.ACTIVE,
            reason=reason,
            created_by=actor,
        )
        jail.currently_banned = Fail2BanBan.objects.filter(
            jail=jail, status=Fail2BanBan.Status.ACTIVE
        ).count()
        jail.total_banned += 1
        jail.save(update_fields=["currently_banned", "total_banned", "updated_at"])
        _add_log(
            FirewallEventLog.Event.BAN,
            message=f"ban {ip_address} on {jail.name}",
            actor=actor,
        )
        return ban
    except VZoneAPIException as exc:
        _add_log(FirewallEventLog.Event.FAIL, success=False, message=str(exc.detail), actor=actor)
        raise


def unban_ip(
    *,
    ip_address: str,
    jail_name: str | None = None,
    actor: User | None = None,
) -> int:
    try:
        ipaddress.ip_address(ip_address)
    except ValueError as exc:
        raise VZoneAPIException(detail="Adresse IP invalide.", code="invalid_ip", status_code=400) from exc

    qs = Fail2BanBan.objects.filter(ip_address=ip_address, status=Fail2BanBan.Status.ACTIVE)
    if jail_name:
        qs = qs.filter(jail__name=jail_name)
    bans = list(qs.select_related("jail"))
    if not bans and provision_mode() == "live" and jail_name:
        # tentative live même sans enregistrement DB
        try:
            _run_cmd([fail2ban_binary(), "set", jail_name, "unbanip", ip_address])
            _add_log(
                FirewallEventLog.Event.UNBAN,
                message=f"unban {ip_address} on {jail_name}",
                actor=actor,
            )
            return 1
        except VZoneAPIException as exc:
            _add_log(FirewallEventLog.Event.FAIL, success=False, message=str(exc.detail), actor=actor)
            raise

    count = 0
    for ban in bans:
        try:
            if provision_mode() == "mock":
                path = config_root() / "fail2ban" / "bans.jsonl"
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(
                        json.dumps({"jail": ban.jail.name, "ip": ip_address, "action": "unban"}) + "\n"
                    )
            else:
                _run_cmd([fail2ban_binary(), "set", ban.jail.name, "unbanip", ip_address])
            ban.status = Fail2BanBan.Status.UNBANNED
            ban.unbanned_at = timezone.now()
            ban.save(update_fields=["status", "unbanned_at"])
            ban.jail.currently_banned = Fail2BanBan.objects.filter(
                jail=ban.jail, status=Fail2BanBan.Status.ACTIVE
            ).count()
            ban.jail.save(update_fields=["currently_banned", "updated_at"])
            count += 1
        except VZoneAPIException as exc:
            _add_log(FirewallEventLog.Event.FAIL, success=False, message=str(exc.detail), actor=actor)
            raise
    if count:
        _add_log(
            FirewallEventLog.Event.UNBAN,
            message=f"unban {ip_address} ({count})",
            actor=actor,
        )
    return count


def overview_for(_user: User | None = None) -> dict[str, Any]:
    ensure_default_jails()
    return {
        "rules": FirewallRule.objects.count(),
        "rules_enabled": FirewallRule.objects.filter(is_enabled=True).count(),
        "rules_applied": FirewallRule.objects.filter(is_applied=True).count(),
        "jails": Fail2BanJail.objects.count(),
        "jails_enabled": Fail2BanJail.objects.filter(is_enabled=True).count(),
        "bans_active": Fail2BanBan.objects.filter(status=Fail2BanBan.Status.ACTIVE).count(),
        "provision_mode": provision_mode(),
    }
