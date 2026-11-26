"""Fonctions WHM JSON API et UAPI branchées sur les services réels du panneau."""
from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.panel_api.errors import ApiCallError


def _p(params: dict, *names: str, default: Any = None) -> Any:
    for name in names:
        if name in params and params[name] not in (None, ""):
            return params[name]
    return default


def _need(params: dict, *names: str) -> Any:
    value = _p(params, *names)
    if value is None:
        raise ApiCallError(f"Paramètre requis : {names[0]}")
    return value


def _priv(caller, code: str) -> None:  # type: ignore[no-untyped-def]
    if not caller.has_reseller_priv(code):
        raise ApiCallError(f"Privilège requis : {code}", http_status=403)


def _owned_accounts(caller):  # type: ignore[no-untyped-def]
    from apps.accounts.models import User

    if caller.is_administrator:
        return User.objects.select_related("quota").all()
    if caller.is_reseller:
        return User.objects.select_related("quota").filter(parent=caller)
    return User.objects.none()


def _account_row(user) -> dict:  # type: ignore[no-untyped-def]
    from apps.domains.models import Domain

    domain = (
        Domain.objects.filter(owner=user, domain_type=Domain.DomainType.PRIMARY)
        .values_list("name", flat=True)
        .first()
        or ""
    )
    quota = getattr(user, "quota", None)
    return {
        "user": user.username,
        "email": user.email,
        "domain": domain,
        "owner": user.parent.username if user.parent_id else "root",
        "suspended": 1 if user.is_suspended else 0,
        "suspendreason": "suspended" if user.is_suspended else "",
        "unix_startdate": user.date_joined.strftime("%Y-%m-%d") if user.date_joined else "",
        "plan": "",
        "disklimit": "unlimited" if quota and quota.unlimited_disk else (str(quota.disk_mb) if quota else ""),
        "maxpop": quota.emails if quota else 0,
        "maxsql": quota.databases if quota else 0,
        "maxaddons": quota.domains if quota else 0,
        "maxftp": quota.ftp_accounts if quota else 0,
        "role": user.role,
    }


def whm_version(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from vzone import __version__

    return {"version": __version__, "api": "anga-whm-1", "hostname": _hostname()}


def _hostname() -> str:
    import socket

    return socket.gethostname()


def whm_applist(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.panel_api.dispatch import public_catalog

    apps = [row for row in public_catalog() if row["kind"] == "whm"]
    return {"app": apps}


def whm_listaccts(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    _priv(caller, "list-accts")
    search = str(_p(params, "search", "searchtype", default="") or "").lower()
    rows = []
    for user in _owned_accounts(caller).order_by("username"):
        row = _account_row(user)
        if search and search not in " ".join(
            [row["user"], row["email"], row["domain"], row["role"]]
        ).lower():
            continue
        rows.append(row)
    return {"acct": rows}


def whm_accountsummary(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    _priv(caller, "list-accts")
    username = str(_need(params, "user", "username"))
    user = _owned_accounts(caller).filter(username=username).first()
    if user is None:
        raise ApiCallError(f"Compte introuvable : {username}")
    return {"acct": [_account_row(user)]}


def whm_createacct(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.accounts.serializers import UserCreateSerializer
    from apps.packages.models import HostingPackage

    _priv(caller, "create-acct")
    username = str(_need(params, "username", "user")).strip()
    domain = str(_need(params, "domain")).strip()
    password = str(_need(params, "password"))
    email = str(_p(params, "contactemail", "email", default="") or "").strip()
    if not email:
        email = f"{username}@{domain}"
    plan = str(_p(params, "plan", "pkgname", default="") or "").strip()
    package_id = None
    if plan:
        pkg = HostingPackage.objects.filter(name__iexact=plan).first() or HostingPackage.objects.filter(
            slug__iexact=plan
        ).first()
        if pkg is None:
            raise ApiCallError(f"Package introuvable : {plan}")
        package_id = pkg.id

    class _Req:
        def __init__(self, user):  # type: ignore[no-untyped-def]
            self.user = user

    payload = {
        "username": username,
        "email": email,
        "password": password,
        "domain": domain,
        "role": "client",
        "package_id": package_id,
        "phone": str(_p(params, "phone", default="") or ""),
    }
    serializer = UserCreateSerializer(data=payload, context={"request": _Req(caller)})
    if not serializer.is_valid():
        raise ApiCallError(_flatten(serializer.errors))
    user = serializer.save()
    return {"user": user.username, "domain": domain, "acct": _account_row(user)}


def whm_suspend(*, caller, account, params, suspended: bool) -> dict:  # type: ignore[no-untyped-def]
    _priv(caller, "suspend-acct")
    username = str(_need(params, "user", "username"))
    user = _owned_accounts(caller).filter(username=username).first()
    if user is None:
        raise ApiCallError(f"Compte introuvable : {username}")
    if user.is_administrator:
        raise ApiCallError("Impossible de suspendre un administrateur.", http_status=403)
    user.is_suspended = suspended
    user.save(update_fields=["is_suspended", "updated_at"])
    return {"user": user.username, "suspended": 1 if suspended else 0}


def whm_suspendacct(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    return whm_suspend(caller=caller, account=account, params=params, suspended=True)


def whm_unsuspendacct(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    return whm_suspend(caller=caller, account=account, params=params, suspended=False)


def whm_passwd(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    _priv(caller, "edit-account")
    username = str(_need(params, "user", "username"))
    password = str(_need(params, "password"))
    user = _owned_accounts(caller).filter(username=username).first()
    if user is None:
        raise ApiCallError(f"Compte introuvable : {username}")
    if user.is_administrator and not caller.is_administrator:
        raise ApiCallError("Interdit.", http_status=403)
    if len(password) < 10:
        raise ApiCallError("Mot de passe trop court (min 10).")
    user.set_password(password)
    user.save(update_fields=["password", "updated_at"])
    return {"user": user.username, "changed": 1}


def whm_removeacct(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.accounts.services import delete_account

    _priv(caller, "kill-acct")
    username = str(_need(params, "user", "username"))
    user = _owned_accounts(caller).filter(username=username).first()
    if user is None:
        raise ApiCallError(f"Compte introuvable : {username}")
    if user.pk == caller.pk or user.is_administrator:
        raise ApiCallError("Suppression refusée.", http_status=403)
    delete_account(user)
    return {"user": username, "removed": 1}


def whm_listpkgs(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.packages.models import HostingPackage

    _priv(caller, "list-pkgs")
    rows = []
    for pkg in HostingPackage.objects.filter(is_active=True).order_by("name"):
        rows.append(
            {
                "name": pkg.name,
                "slug": pkg.slug,
                "type": pkg.package_type,
                "quota": "unlimited" if pkg.unlimited_disk else pkg.disk_mb,
                "bwlimit": "unlimited" if pkg.unlimited_bandwidth else pkg.bandwidth_mb,
                "maxpop": pkg.emails if hasattr(pkg, "emails") else None,
                "maxsql": pkg.databases if hasattr(pkg, "databases") else None,
                "maxaddon": pkg.domains if hasattr(pkg, "domains") else None,
                "maxftp": pkg.ftp_accounts if hasattr(pkg, "ftp_accounts") else None,
            }
        )
    return {"package": rows}


def whm_listzones(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.dns.services import zones_queryset_for

    _priv(caller, "manage-dns")
    zones = []
    for zone in zones_queryset_for(caller):
        zones.append({"domain": zone.name, "zone": zone.name, "owner": zone.owner.username})
    return {"zone": zones}


def whm_dumpzone(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.dns.services import zones_queryset_for

    _priv(caller, "manage-dns")
    name = str(_need(params, "domain", "zone")).strip().lower().rstrip(".")
    zone = zones_queryset_for(caller).filter(name=name).first()
    if zone is None:
        raise ApiCallError(f"Zone introuvable : {name}")
    records = [
        {
            "line": rec.id,
            "type": rec.record_type,
            "name": rec.name,
            "record": rec.content,
            "ttl": rec.ttl or zone.ttl_default,
            "priority": rec.priority,
        }
        for rec in zone.records.all()
    ]
    return {"zone": [{"record": records, "domain": zone.name}]}


def whm_addzonerecord(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    _priv(caller, "manage-dns")
    return _add_record(caller, params)


def whm_servicestatus(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.dashboard.services import overview_for

    if not caller.is_administrator and not caller.has_reseller_priv("res-monitoring"):
        raise ApiCallError("Privilège requis : res-monitoring", http_status=403)
    data = overview_for(caller)
    return {"status": data}


def uapi_user_info(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    return {
        "user": account.username,
        "email": account.email,
        "role": account.role,
        "suspended": bool(account.is_suspended),
        "home": account.home_directory,
    }


def uapi_list_domains(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.domains.models import Domain

    domains = Domain.objects.filter(owner=account).order_by("name")
    main = ""
    addon, sub, parked = [], [], []
    for dom in domains:
        item = {"domain": dom.name, "type": dom.domain_type, "documentroot": dom.document_root}
        if dom.domain_type == Domain.DomainType.PRIMARY and not main:
            main = dom.name
        elif dom.domain_type == Domain.DomainType.SUBDOMAIN:
            sub.append(item)
        elif dom.domain_type in {Domain.DomainType.PARKED, Domain.DomainType.ALIAS}:
            parked.append(item)
        else:
            addon.append(item)
    return {"main_domain": main, "addon_domains": addon, "sub_domains": sub, "parked_domains": parked}


def uapi_single_domain(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.domains.models import Domain

    name = str(_need(params, "domain")).strip().lower()
    dom = Domain.objects.filter(owner=account, name=name).first()
    if dom is None:
        raise ApiCallError(f"Domaine introuvable : {name}")
    return {
        "domain": dom.name,
        "type": dom.domain_type,
        "documentroot": dom.document_root,
        "suspended": dom.is_suspended,
        "force_https": dom.force_https,
    }


def uapi_add_domain(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.domains.models import Domain
    from apps.domains.services import create_domain

    name = str(_need(params, "newdomain", "domain"))
    dtype = str(_p(params, "type", "domain_type", default="addon"))
    parent = None
    if dtype == "subdomain":
        parent_name = str(_need(params, "rootdomain", "parent"))
        parent = Domain.objects.filter(owner=account, name=parent_name).first()
        if parent is None:
            raise ApiCallError("Domaine parent introuvable.")
    dom = create_domain(
        name=name,
        owner=account,
        domain_type=dtype,
        parent=parent,
        document_root=str(_p(params, "dir", "document_root", default="") or ""),
    )
    return {"domain": dom.name, "type": dom.domain_type}


def uapi_list_pops(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.email.models import Mailbox

    boxes = Mailbox.objects.filter(mail_domain__owner=account).select_related("mail_domain")
    domain = str(_p(params, "domain", default="") or "")
    if domain:
        boxes = boxes.filter(mail_domain__name=domain.strip().lower())
    return {
        "pops": [
            {
                "email": box.address,
                "login": box.local_part,
                "domain": box.mail_domain.name,
                "quota": box.quota_mb,
                "suspended": box.is_suspended,
            }
            for box in boxes
        ]
    }


def _mail_domain(account, name: str):  # type: ignore[no-untyped-def]
    from apps.email.models import MailDomain

    md = MailDomain.objects.filter(owner=account, name=name.strip().lower()).first()
    if md is None:
        raise ApiCallError(f"Domaine mail introuvable : {name}")
    return md


def uapi_add_pop(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.email.services import create_mailbox

    email = str(_p(params, "email", default="") or "")
    if "@" in email:
        local, domain = email.split("@", 1)
    else:
        local = str(_need(params, "email", "local"))
        domain = str(_need(params, "domain"))
    box = create_mailbox(
        mail_domain=_mail_domain(account, domain),
        local_part=local,
        password=str(_need(params, "password")),
        quota_mb=int(_p(params, "quota", default=0) or 0) or None,
    )
    return {"email": box.address}


def uapi_passwd_pop(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.email.models import Mailbox
    from apps.email.services import update_mailbox

    email = str(_need(params, "email"))
    local, _, domain = email.partition("@")
    box = Mailbox.objects.filter(
        mail_domain__owner=account, mail_domain__name=domain, local_part=local
    ).first()
    if box is None:
        raise ApiCallError(f"Boîte introuvable : {email}")
    update_mailbox(box, password=str(_need(params, "password")))
    return {"email": email, "changed": 1}


def uapi_delete_pop(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.email.models import Mailbox
    from apps.email.services import delete_mailbox

    email = str(_need(params, "email"))
    local, _, domain = email.partition("@")
    box = Mailbox.objects.filter(
        mail_domain__owner=account, mail_domain__name=domain, local_part=local
    ).first()
    if box is None:
        raise ApiCallError(f"Boîte introuvable : {email}")
    delete_mailbox(box)
    return {"email": email, "deleted": 1}


def uapi_list_databases(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.databases.services import databases_qs

    engine = str(_p(params, "engine", default="") or "")
    qs = databases_qs(account)
    if engine:
        qs = qs.filter(engine=engine)
    return {
        "databases": [
            {"name": db.name, "engine": db.engine, "size_mb": db.size_mb} for db in qs
        ]
    }


def uapi_create_database(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.databases.services import create_database

    db = create_database(
        owner=account,
        name=str(_need(params, "name", "db")),
        engine=str(_p(params, "engine", default="mysql")),
    )
    return {"name": db.name, "engine": db.engine}


def uapi_delete_database(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.databases.services import databases_qs, delete_database

    name = str(_need(params, "name", "db"))
    db = databases_qs(account).filter(name=name).first()
    if db is None:
        db = databases_qs(account).filter(name__endswith=f"_{name}").first()
    if db is None:
        raise ApiCallError(f"Base introuvable : {name}")
    delete_database(db)
    return {"name": name, "deleted": 1}


def uapi_create_dbuser(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.databases.services import create_database_user, databases_qs, grant_privilege

    user = create_database_user(
        owner=account,
        username=str(_need(params, "name", "user", "username")),
        password=str(_need(params, "password")),
        engine=str(_p(params, "engine", default="mysql")),
    )
    dbname = str(_p(params, "database", "db", default="") or "")
    if dbname:
        db = databases_qs(account).filter(name=dbname, engine=user.engine).first()
        if db is None:
            raise ApiCallError(f"Base introuvable : {dbname}")
        grant_privilege(database=db, user=user, privileges=str(_p(params, "privileges", default="ALL")))
    return {"username": user.username, "engine": user.engine}


def uapi_list_ftp(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.ftp.services import accounts_queryset_for

    return {
        "ftp": [
            {
                "user": acc.username,
                "dir": acc.relative_directory,
                "quota": acc.quota_mb,
                "suspended": acc.is_suspended,
            }
            for acc in accounts_queryset_for(account)
        ]
    }


def uapi_add_ftp(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.ftp.services import create_ftp_account

    acc = create_ftp_account(
        owner=account,
        username=str(_need(params, "user", "username")),
        password=str(_need(params, "pass", "password")),
        relative_directory=str(_p(params, "homedir", "dir", default="public_html")),
        quota_mb=int(_p(params, "quota", default=0) or 0),
    )
    return {"user": acc.username, "dir": acc.relative_directory}


def uapi_delete_ftp(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.ftp.services import accounts_queryset_for, delete_ftp_account

    login = str(_need(params, "user", "username"))
    acc = accounts_queryset_for(account).filter(username=login).first()
    if acc is None:
        raise ApiCallError(f"Compte FTP introuvable : {login}")
    delete_ftp_account(acc)
    return {"user": login, "deleted": 1}


def uapi_list_cron(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.cron.services import jobs_queryset_for

    return {
        "cron": [
            {
                "linekey": job.id,
                "command": job.command,
                "minute": job.minute,
                "hour": job.hour,
                "day": job.day,
                "month": job.month,
                "weekday": job.weekday,
                "label": job.label,
                "active": job.is_active,
            }
            for job in jobs_queryset_for(account)
        ]
    }


def uapi_add_cron(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.cron.services import create_cron_job

    job = create_cron_job(
        owner=account,
        command=str(_need(params, "command")),
        minute=str(_p(params, "minute", default="0")),
        hour=str(_p(params, "hour", default="*")),
        day=str(_p(params, "day", default="*")),
        month=str(_p(params, "month", default="*")),
        weekday=str(_p(params, "weekday", default="*")),
        label=str(_p(params, "label", default="") or ""),
    )
    return {"linekey": job.id, "command": job.command}


def uapi_remove_cron(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.cron.services import delete_cron_job, jobs_queryset_for

    line = int(_need(params, "linekey", "id"))
    job = jobs_queryset_for(account).filter(pk=line).first()
    if job is None:
        raise ApiCallError("Tâche cron introuvable.")
    delete_cron_job(job)
    return {"linekey": line, "deleted": 1}


def uapi_list_zones(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.dns.services import zones_queryset_for

    return {"zones": [{"domain": z.name, "ttl": z.ttl_default} for z in zones_queryset_for(account)]}


def uapi_parse_zone(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.dns.services import zones_queryset_for

    name = str(_need(params, "zone", "domain")).strip().lower().rstrip(".")
    zone = zones_queryset_for(account).filter(name=name).first()
    if zone is None:
        raise ApiCallError(f"Zone introuvable : {name}")
    return {
        "zone": name,
        "records": [
            {
                "line": rec.id,
                "type": rec.record_type,
                "name": rec.name,
                "record": rec.content,
                "ttl": rec.ttl,
                "priority": rec.priority,
            }
            for rec in zone.records.all()
        ],
    }


def _add_record(owner, params: dict) -> dict:  # type: ignore[no-untyped-def]
    from apps.dns.models import DnsRecord
    from apps.dns.services import zones_queryset_for

    name = str(_need(params, "zone", "domain")).strip().lower().rstrip(".")
    zone = zones_queryset_for(owner).filter(name=name).first()
    if zone is None:
        raise ApiCallError(f"Zone introuvable : {name}")
    rec = DnsRecord(
        zone=zone,
        record_type=str(_need(params, "type")).upper(),
        name=str(_p(params, "name", default="@")),
        content=str(_need(params, "address", "record", "content")),
        ttl=int(_p(params, "ttl", default=0) or 0) or None,
        priority=_p(params, "priority"),
    )
    if rec.priority is not None:
        rec.priority = int(rec.priority)
    rec.full_clean()
    rec.save()
    try:
        from apps.dns.authoritative import schedule_zone_sync

        schedule_zone_sync(zone)
    except Exception:  # noqa: BLE001
        pass
    return {"line": rec.id, "zone": zone.name, "type": rec.record_type, "name": rec.name}


def uapi_add_zone_record(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    return _add_record(account, params)


def uapi_list_files(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.files.services import list_directory

    return list_directory(account, str(_p(params, "dir", "path", default="") or ""))


def uapi_php_versions(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.php.services import versions_qs

    return {
        "versions": [
            {"id": ver.id, "version": ver.version, "binary": ver.binary_path, "is_default": ver.is_default}
            for ver in versions_qs()
        ]
    }


def uapi_stats(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.dashboard.services import overview_for

    data = overview_for(account)
    data["generated_at"] = timezone.now().isoformat()
    return data


def whm_cpanel(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    """WHM API 1 `cpanel` : exécute une fonction UAPI sur un compte (comme WHM)."""
    from apps.panel_api.dispatch import CATALOG

    module = str(_need(params, "cpanel_jsonapi_module", "module"))
    func = str(_need(params, "cpanel_jsonapi_func", "func", "function"))
    name = f"{module}.{func}"
    spec = CATALOG.get(name)
    if spec is None or spec.kind != "uapi":
        raise ApiCallError(f"Fonction UAPI inconnue : {name}", http_status=404)
    return spec.handler(caller=caller, account=account, params=params)


_BLOCKED_API_PREFIXES = (
    "/api/v1/auth/login",
    "/api/v1/auth/logout",
    "/api/v1/auth/refresh",
    "/api/v1/auth/forgot-password",
    "/api/v1/auth/sso/",
)


def panel_request(*, actor, params) -> dict:  # type: ignore[no-untyped-def]
    """Appelle n'importe quelle route /api/v1/ avec l'identité du compte (toutes les actions du panneau)."""
    import json as _json
    from urllib.parse import urlencode

    from rest_framework.test import APIClient

    method = str(_p(params, "method", default="GET") or "GET").upper()
    if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        raise ApiCallError("Méthode invalide (GET, POST, PUT, PATCH, DELETE).")
    path = str(_need(params, "path", "uri", "endpoint")).strip()
    if not path.startswith("/"):
        path = "/" + path
    path = path.split("?", 1)[0]
    if not path.startswith("/api/v1/"):
        raise ApiCallError("Le chemin doit commencer par /api/v1/.")
    if any(path.startswith(prefix) for prefix in _BLOCKED_API_PREFIXES):
        raise ApiCallError(
            "Cette route d'authentification n'est pas appelable par jeton.",
            http_status=403,
        )
    body = params.get("data")
    if body is None:
        body = params.get("payload")
    if body is None:
        body = params.get("body")
    if isinstance(body, str) and body.strip():
        try:
            body = _json.loads(body)
        except _json.JSONDecodeError as exc:
            raise ApiCallError("data n'est pas du JSON.") from exc
    if body is None:
        body = {}
    query = params.get("query") or {}
    if isinstance(query, str) and query.strip():
        try:
            query = _json.loads(query)
        except _json.JSONDecodeError as exc:
            raise ApiCallError("query n'est pas du JSON.") from exc
    if isinstance(query, dict) and query:
        path = f"{path}?{urlencode(query, doseq=True)}"

    client = APIClient()
    client.force_authenticate(user=actor)
    kwargs = {}
    if method != "GET":
        kwargs["data"] = _json.dumps(body if isinstance(body, (dict, list)) else {})
        kwargs["content_type"] = "application/json"
    response = client.generic(method, path, **kwargs)
    try:
        parsed = response.json()
    except Exception:  # noqa: BLE001
        parsed = {"raw": response.content[:4000].decode("utf-8", "replace")}
    if response.status_code >= 400:
        message = parsed
        if isinstance(parsed, dict):
            err = parsed.get("error") or parsed.get("detail") or parsed
            message = err
        raise ApiCallError(str(message)[:800], http_status=response.status_code)
    return {"status": response.status_code, "body": parsed}


def whm_apirequest(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    _priv(caller, "list-accts")
    return panel_request(actor=caller, params=params)


def uapi_panel_request(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    return panel_request(actor=account, params=params)


def uapi_backup_list(*, caller, account, params) -> dict:  # type: ignore[no-untyped-def]
    from apps.backups.services import archives_qs

    return {
        "backups": [
            {
                "id": arc.id,
                "name": getattr(arc, "label", "") or getattr(arc, "filename", "") or str(arc.id),
                "status": getattr(arc, "status", ""),
                "created": arc.created_at.isoformat() if getattr(arc, "created_at", None) else "",
            }
            for arc in archives_qs(account)[:100]
        ]
    }


def _flatten(errors) -> str:  # type: ignore[no-untyped-def]
    if isinstance(errors, dict):
        parts = []
        for key, val in errors.items():
            parts.append(f"{key}: {_flatten(val)}")
        return "; ".join(parts)
    if isinstance(errors, (list, tuple)):
        return "; ".join(_flatten(item) for item in errors)
    return str(errors)


HANDLERS: list[dict] = [
    {"name": "version", "kind": "whm", "summary": "Version du panneau.", "params": [], "handler": whm_version},
    {"name": "applist", "kind": "whm", "summary": "Liste des fonctions WHM.", "params": [], "handler": whm_applist},
    {"name": "listaccts", "kind": "whm", "summary": "Liste des comptes.", "params": ["search"], "handler": whm_listaccts},
    {"name": "accountsummary", "kind": "whm", "summary": "Résumé d'un compte.", "params": ["user"], "handler": whm_accountsummary},
    {"name": "createacct", "kind": "whm", "summary": "Créer un compte client.", "params": ["username", "domain", "password", "contactemail", "plan"], "handler": whm_createacct},
    {"name": "suspendacct", "kind": "whm", "summary": "Suspendre un compte.", "params": ["user"], "handler": whm_suspendacct},
    {"name": "unsuspendacct", "kind": "whm", "summary": "Réactiver un compte.", "params": ["user"], "handler": whm_unsuspendacct},
    {"name": "passwd", "kind": "whm", "summary": "Changer le mot de passe d'un compte.", "params": ["user", "password"], "handler": whm_passwd},
    {"name": "removeacct", "kind": "whm", "summary": "Supprimer un compte.", "params": ["user"], "handler": whm_removeacct},
    {"name": "listpkgs", "kind": "whm", "summary": "Liste des packages.", "params": [], "handler": whm_listpkgs},
    {"name": "listzones", "kind": "whm", "summary": "Liste des zones DNS.", "params": [], "handler": whm_listzones},
    {"name": "dumpzone", "kind": "whm", "summary": "Contenu d'une zone DNS.", "params": ["domain"], "handler": whm_dumpzone},
    {"name": "addzonerecord", "kind": "whm", "summary": "Ajouter un enregistrement DNS.", "params": ["domain", "type", "name", "address"], "handler": whm_addzonerecord},
    {"name": "servicestatus", "kind": "whm", "summary": "État des services.", "params": [], "handler": whm_servicestatus},
    {
        "name": "cpanel",
        "kind": "whm",
        "summary": "Exécuter une fonction UAPI sur un compte (cpanel_jsonapi_user, module, func).",
        "params": ["cpanel_jsonapi_user", "cpanel_jsonapi_module", "cpanel_jsonapi_func"],
        "handler": whm_cpanel,
    },
    {
        "name": "apirequest",
        "kind": "whm",
        "summary": "Appeler n'importe quelle route /api/v1/ du panneau (method, path, data).",
        "params": ["method", "path", "data"],
        "handler": whm_apirequest,
    },
    {"name": "Variables.get_user_information", "kind": "uapi", "summary": "Identité du compte.", "params": ["account"], "handler": uapi_user_info},
    {"name": "DomainInfo.list_domains", "kind": "uapi", "summary": "Domaines du compte.", "params": ["account"], "handler": uapi_list_domains},
    {"name": "DomainInfo.single_domain_data", "kind": "uapi", "summary": "Détail d'un domaine.", "params": ["domain"], "handler": uapi_single_domain},
    {"name": "Domain.add_domain", "kind": "uapi", "summary": "Ajouter un domaine ou sous-domaine.", "params": ["domain", "type", "rootdomain", "dir"], "handler": uapi_add_domain},
    {"name": "Email.list_pops", "kind": "uapi", "summary": "Boîtes mail.", "params": ["domain"], "handler": uapi_list_pops},
    {"name": "Email.add_pop", "kind": "uapi", "summary": "Créer une boîte mail.", "params": ["email", "password", "quota"], "handler": uapi_add_pop},
    {"name": "Email.passwd_pop", "kind": "uapi", "summary": "Mot de passe d'une boîte.", "params": ["email", "password"], "handler": uapi_passwd_pop},
    {"name": "Email.delete_pop", "kind": "uapi", "summary": "Supprimer une boîte mail.", "params": ["email"], "handler": uapi_delete_pop},
    {"name": "Mysql.list_databases", "kind": "uapi", "summary": "Bases de données.", "params": ["engine"], "handler": uapi_list_databases},
    {"name": "Mysql.create_database", "kind": "uapi", "summary": "Créer une base.", "params": ["name", "engine"], "handler": uapi_create_database},
    {"name": "Mysql.delete_database", "kind": "uapi", "summary": "Supprimer une base.", "params": ["name"], "handler": uapi_delete_database},
    {"name": "Mysql.create_user", "kind": "uapi", "summary": "Créer un utilisateur SQL.", "params": ["name", "password", "engine", "database"], "handler": uapi_create_dbuser},
    {"name": "Ftp.list_ftp", "kind": "uapi", "summary": "Comptes FTP.", "params": [], "handler": uapi_list_ftp},
    {"name": "Ftp.add_ftp", "kind": "uapi", "summary": "Créer un compte FTP.", "params": ["user", "password", "homedir", "quota"], "handler": uapi_add_ftp},
    {"name": "Ftp.delete_ftp", "kind": "uapi", "summary": "Supprimer un compte FTP.", "params": ["user"], "handler": uapi_delete_ftp},
    {"name": "Cron.list_cron", "kind": "uapi", "summary": "Tâches cron.", "params": [], "handler": uapi_list_cron},
    {"name": "Cron.add_line", "kind": "uapi", "summary": "Ajouter une tâche cron.", "params": ["command", "minute", "hour", "day", "month", "weekday"], "handler": uapi_add_cron},
    {"name": "Cron.remove_line", "kind": "uapi", "summary": "Supprimer une tâche cron.", "params": ["linekey"], "handler": uapi_remove_cron},
    {"name": "DNS.list_zones", "kind": "uapi", "summary": "Zones DNS du compte.", "params": [], "handler": uapi_list_zones},
    {"name": "DNS.parse_zone", "kind": "uapi", "summary": "Enregistrements d'une zone.", "params": ["zone"], "handler": uapi_parse_zone},
    {"name": "DNS.mass_edit_zone", "kind": "uapi", "summary": "Ajouter un enregistrement DNS.", "params": ["zone", "type", "name", "address"], "handler": uapi_add_zone_record},
    {"name": "Fileman.list_files", "kind": "uapi", "summary": "Lister un dossier du compte.", "params": ["dir"], "handler": uapi_list_files},
    {"name": "LangPHP.php_get_installed_versions", "kind": "uapi", "summary": "Versions PHP connues.", "params": [], "handler": uapi_php_versions},
    {"name": "Stats.get_stats", "kind": "uapi", "summary": "Statistiques du compte.", "params": [], "handler": uapi_stats},
    {"name": "Backup.list_backups", "kind": "uapi", "summary": "Archives de sauvegarde.", "params": [], "handler": uapi_backup_list},
    {
        "name": "Panel.request",
        "kind": "uapi",
        "summary": "Appeler n'importe quelle route /api/v1/ au nom du compte (method, path, data).",
        "params": ["method", "path", "data", "account"],
        "handler": uapi_panel_request,
    },
]
