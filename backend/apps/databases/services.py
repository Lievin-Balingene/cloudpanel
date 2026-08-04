"""Services bases de données : quotas, provisionnement MySQL/PostgreSQL, maps."""
from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q, QuerySet

from apps.accounts.models import User
from apps.core.exceptions import QuotaExceeded, VZoneAPIException
from apps.databases.models import Database, DatabaseEngine, DatabasePrivilege, DatabaseUser

logger = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,47}$")
USER_RE = re.compile(r"^[a-z][a-z0-9_]{1,31}$")


def databases_qs(user: User) -> QuerySet[Database]:
    qs = Database.objects.select_related("owner").prefetch_related("privileges__user")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def db_users_qs(user: User) -> QuerySet[DatabaseUser]:
    qs = DatabaseUser.objects.select_related("owner").prefetch_related("privileges__database")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(owner=user) | Q(owner__parent=user))
    return qs.filter(owner=user)


def privileges_qs(user: User) -> QuerySet[DatabasePrivilege]:
    qs = DatabasePrivilege.objects.select_related("database", "user", "database__owner")
    if user.role == User.Role.ADMINISTRATOR:
        return qs
    if user.role == User.Role.RESELLER:
        return qs.filter(Q(database__owner=user) | Q(database__owner__parent=user))
    return qs.filter(database__owner=user)


def _assert_database_quota(owner: User) -> None:
    quota = getattr(owner, "quota", None)
    if quota is None:
        return
    limit = quota.databases
    if limit == 0 and owner.role == User.Role.ADMINISTRATOR:
        return
    used = Database.objects.filter(owner=owner).count()
    if limit > 0 and used >= limit:
        raise QuotaExceeded(
            detail="Quota de bases de données atteint.",
            extra={"limit": limit, "used": used},
        )


def _prefix_name(raw: str, owner: User, *, kind: str) -> str:
    value = raw.strip().lower().replace("-", "_")
    prefix = f"{owner.username}_"
    if not value.startswith(prefix):
        value = f"{prefix}{value}"
    pattern = NAME_RE if kind == "db" else USER_RE
    if not pattern.match(value):
        raise VZoneAPIException(
            detail=f"Nom {kind} invalide (a-z, 0-9, _ ; préfixe {owner.username}_).",
            code="invalid_name",
            status_code=400,
        )
    return value


def maps_root() -> Path:
    root = Path(
        getattr(settings, "VZONE_DB_MAPS_DIR", None) or (Path(settings.VZONE_DATA_ROOT) / "databases")
    )
    root.mkdir(parents=True, exist_ok=True)
    (root / "pending").mkdir(exist_ok=True)
    return root


def provision_mode() -> str:
    mode = getattr(settings, "VZONE_DB_PROVISION_MODE", "auto").lower()
    return mode if mode in {"auto", "live", "mock"} else "auto"


def _mysql_configured() -> bool:
    return bool(getattr(settings, "VZONE_MYSQL_HOST", "") and getattr(settings, "VZONE_MYSQL_ADMIN_USER", ""))


def _pg_configured() -> bool:
    return bool(getattr(settings, "VZONE_PG_HOST", "") and getattr(settings, "VZONE_PG_ADMIN_USER", ""))


def should_execute(engine: str) -> bool:
    mode = provision_mode()
    if mode == "mock":
        return False
    if mode == "live":
        return _mysql_configured() if engine == DatabaseEngine.MYSQL else _pg_configured()
    return _mysql_configured() if engine == DatabaseEngine.MYSQL else _pg_configured()


def _escape_sql_literal(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "''")


def _write_pending_sql(name: str, sql: str) -> Path:
    path = maps_root() / "pending" / name
    path.write_text(sql if sql.endswith("\n") else sql + "\n", encoding="utf-8")
    return path


def _run_mysql(sql: str) -> None:
    host = settings.VZONE_MYSQL_HOST
    port = str(getattr(settings, "VZONE_MYSQL_PORT", 3306))
    user = settings.VZONE_MYSQL_ADMIN_USER
    password = getattr(settings, "VZONE_MYSQL_ADMIN_PASSWORD", "")
    binary = shutil.which("mysql") or getattr(settings, "VZONE_MYSQL_BIN", "mysql")
    cmd = [binary, f"-h{host}", f"-P{port}", f"-u{user}", "-e", sql]
    env = os.environ.copy()
    if password:
        env["MYSQL_PWD"] = password
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, env=env, timeout=60)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.exception("Échec provisionnement MySQL")
        raise VZoneAPIException(
            detail="Échec provisionnement MySQL.",
            code="mysql_provision_failed",
            status_code=502,
            extra={"stderr": getattr(exc, "stderr", str(exc))},
        ) from exc


def _run_psql(sql: str) -> None:
    host = settings.VZONE_PG_HOST
    port = str(getattr(settings, "VZONE_PG_PORT", 5432))
    user = settings.VZONE_PG_ADMIN_USER
    password = getattr(settings, "VZONE_PG_ADMIN_PASSWORD", "")
    dbname = getattr(settings, "VZONE_PG_ADMIN_DB", "postgres")
    binary = shutil.which("psql") or getattr(settings, "VZONE_PG_BIN", "psql")
    cmd = [
        binary,
        "-h",
        host,
        "-p",
        port,
        "-U",
        user,
        "-d",
        dbname,
        "-v",
        "ON_ERROR_STOP=1",
        "-c",
        sql,
    ]
    env = os.environ.copy()
    if password:
        env["PGPASSWORD"] = password
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, env=env, timeout=60)
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
        logger.exception("Échec provisionnement PostgreSQL")
        raise VZoneAPIException(
            detail="Échec provisionnement PostgreSQL.",
            code="pg_provision_failed",
            status_code=502,
            extra={"stderr": getattr(exc, "stderr", str(exc))},
        ) from exc


def apply_sql(engine: str, sql: str, *, label: str) -> None:
    if should_execute(engine):
        if engine == DatabaseEngine.MYSQL:
            _run_mysql(sql)
        else:
            _run_psql(sql)
    else:
        _write_pending_sql(f"{label}.sql", sql)
        logger.info("SQL %s enregistré (mode mock/auto sans backend)", label)


def mysql_privs(level: str) -> str:
    if level == "READ":
        return "SELECT, SHOW VIEW"
    if level == "WRITE":
        return (
            "SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, INDEX, ALTER, "
            "CREATE TEMPORARY TABLES, LOCK TABLES"
        )
    return "ALL PRIVILEGES"


def write_inventory() -> Path:
    root = maps_root()
    lines = ["# engine|name|owner|active"]
    for db in Database.objects.select_related("owner").order_by("engine", "name"):
        lines.append(f"{db.engine}|{db.name}|{db.owner.username}|{int(db.is_active)}")
    (root / "inventory.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    ulines = ["# engine|username|host|owner|active"]
    for u in DatabaseUser.objects.select_related("owner").order_by("engine", "username"):
        ulines.append(f"{u.engine}|{u.username}|{u.host}|{u.owner.username}|{int(u.is_active)}")
    (root / "users.txt").write_text("\n".join(ulines) + "\n", encoding="utf-8")
    return root


@transaction.atomic
def create_database(
    *,
    owner: User,
    name: str,
    engine: str = DatabaseEngine.MYSQL,
    charset: str = "utf8mb4",
    collation: str = "utf8mb4_unicode_ci",
    notes: str = "",
) -> Database:
    if engine not in DatabaseEngine.values:
        raise VZoneAPIException(detail="Moteur invalide.", code="invalid_engine", status_code=400)
    _assert_database_quota(owner)
    db_name = _prefix_name(name, owner, kind="db")
    if Database.objects.filter(engine=engine, name=db_name).exists():
        raise VZoneAPIException(detail="Cette base existe déjà.", code="exists", status_code=400)

    if engine == DatabaseEngine.POSTGRESQL:
        charset = "UTF8"
        collation = "default"
        sql = f'CREATE DATABASE "{db_name}" WITH ENCODING \'{charset}\' TEMPLATE template0;'
    else:
        sql = (
            f"CREATE DATABASE `{db_name}` "
            f"CHARACTER SET `{_escape_sql_literal(charset)}` "
            f"COLLATE `{_escape_sql_literal(collation)}`;"
        )
    apply_sql(engine, sql, label=f"create_db_{engine}_{db_name}")

    db = Database.objects.create(
        owner=owner,
        engine=engine,
        name=db_name,
        charset=charset,
        collation=collation,
        notes=notes,
    )
    write_inventory()
    return db


@transaction.atomic
def delete_database(db: Database) -> None:
    if db.engine == DatabaseEngine.POSTGRESQL:
        sql = (
            f'REVOKE CONNECT ON DATABASE "{db.name}" FROM PUBLIC; '
            f"SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
            f"WHERE datname = '{_escape_sql_literal(db.name)}' AND pid <> pg_backend_pid(); "
            f'DROP DATABASE IF EXISTS "{db.name}";'
        )
    else:
        sql = f"DROP DATABASE IF EXISTS `{db.name}`;"
    apply_sql(db.engine, sql, label=f"drop_db_{db.engine}_{db.name}")
    db.delete()
    write_inventory()


@transaction.atomic
def create_database_user(
    *,
    owner: User,
    username: str,
    password: str,
    engine: str = DatabaseEngine.MYSQL,
    host: str = "localhost",
    notes: str = "",
) -> DatabaseUser:
    if engine not in DatabaseEngine.values:
        raise VZoneAPIException(detail="Moteur invalide.", code="invalid_engine", status_code=400)
    if len(password) < 8:
        raise VZoneAPIException(detail="Mot de passe trop court (min 8).", code="weak_password", status_code=400)
    uname = _prefix_name(username, owner, kind="user")
    host = (host or "localhost").strip() or "localhost"
    if DatabaseUser.objects.filter(engine=engine, username=uname, host=host).exists():
        raise VZoneAPIException(detail="Cet utilisateur existe déjà.", code="exists", status_code=400)

    pwd = _escape_sql_literal(password)
    if engine == DatabaseEngine.POSTGRESQL:
        sql = f"CREATE USER \"{uname}\" WITH PASSWORD '{pwd}';"
    else:
        sql = f"CREATE USER '{uname}'@'{_escape_sql_literal(host)}' IDENTIFIED BY '{pwd}';"
    apply_sql(engine, sql, label=f"create_user_{engine}_{uname}")

    user = DatabaseUser(
        owner=owner,
        engine=engine,
        username=uname,
        host=host,
        notes=notes,
    )
    user.set_password(password)
    user.save()
    write_inventory()
    return user


@transaction.atomic
def update_database_user(
    user: DatabaseUser,
    *,
    password: str | None = None,
    is_active: bool | None = None,
    notes: str | None = None,
) -> DatabaseUser:
    if password is not None:
        if len(password) < 8:
            raise VZoneAPIException(detail="Mot de passe trop court.", code="weak_password", status_code=400)
        pwd = _escape_sql_literal(password)
        if user.engine == DatabaseEngine.POSTGRESQL:
            sql = f"ALTER USER \"{user.username}\" WITH PASSWORD '{pwd}';"
        else:
            sql = (
                f"ALTER USER '{user.username}'@'{_escape_sql_literal(user.host)}' "
                f"IDENTIFIED BY '{pwd}';"
            )
        apply_sql(user.engine, sql, label=f"alter_user_{user.engine}_{user.username}")
        user.set_password(password)
    if is_active is not None:
        user.is_active = is_active
    if notes is not None:
        user.notes = notes
    user.save()
    write_inventory()
    return user


@transaction.atomic
def delete_database_user(user: DatabaseUser) -> None:
    if user.engine == DatabaseEngine.POSTGRESQL:
        sql = f'DROP USER IF EXISTS "{user.username}";'
    else:
        sql = f"DROP USER IF EXISTS '{user.username}'@'{_escape_sql_literal(user.host)}';"
    apply_sql(user.engine, sql, label=f"drop_user_{user.engine}_{user.username}")
    user.delete()
    write_inventory()


@transaction.atomic
def grant_privilege(
    *,
    database: Database,
    user: DatabaseUser,
    privileges: str = "ALL",
) -> DatabasePrivilege:
    if database.engine != user.engine:
        raise VZoneAPIException(
            detail="Moteurs incompatibles entre base et utilisateur.",
            code="engine_mismatch",
            status_code=400,
        )
    if database.owner_id != user.owner_id:
        raise VZoneAPIException(
            detail="La base et l'utilisateur doivent appartenir au même compte.",
            code="owner_mismatch",
            status_code=400,
        )
    if privileges not in {"ALL", "READ", "WRITE"}:
        raise VZoneAPIException(detail="Privilèges invalides.", code="invalid_privs", status_code=400)

    if database.engine == DatabaseEngine.POSTGRESQL:
        if privileges == "READ":
            sql = (
                f'GRANT CONNECT ON DATABASE "{database.name}" TO "{user.username}";\n'
                f'GRANT USAGE ON SCHEMA public TO "{user.username}";\n'
                f'GRANT SELECT ON ALL TABLES IN SCHEMA public TO "{user.username}";\n'
                f'GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO "{user.username}";\n'
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO "{user.username}";\n'
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO "{user.username}";'
            )
        elif privileges == "WRITE":
            sql = (
                f'GRANT CONNECT, CREATE ON DATABASE "{database.name}" TO "{user.username}";\n'
                f'GRANT USAGE, CREATE ON SCHEMA public TO "{user.username}";\n'
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{user.username}";\n'
                f'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO "{user.username}";\n'
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
                f'GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{user.username}";\n'
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
                f'GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO "{user.username}";'
            )
        else:
            sql = (
                f'GRANT ALL PRIVILEGES ON DATABASE "{database.name}" TO "{user.username}";\n'
                f'GRANT ALL ON SCHEMA public TO "{user.username}";\n'
                f'GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO "{user.username}";\n'
                f'GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO "{user.username}";\n'
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
                f'GRANT ALL PRIVILEGES ON TABLES TO "{user.username}";\n'
                f'ALTER DEFAULT PRIVILEGES IN SCHEMA public '
                f'GRANT ALL PRIVILEGES ON SEQUENCES TO "{user.username}";'
            )
    else:
        priv = mysql_privs(privileges)
        sql = (
            f"GRANT {priv} ON `{database.name}`.* "
            f"TO '{user.username}'@'{_escape_sql_literal(user.host)}'; "
            "FLUSH PRIVILEGES;"
        )
    apply_sql(database.engine, sql, label=f"grant_{database.engine}_{database.name}_{user.username}")

    priv_obj, _ = DatabasePrivilege.objects.update_or_create(
        database=database,
        user=user,
        defaults={"privileges": privileges},
    )
    return priv_obj


@transaction.atomic
def revoke_privilege(priv: DatabasePrivilege) -> None:
    """Révoque les droits SQL puis retire l'association panel (best-effort)."""
    db = priv.database
    user = priv.user
    if db.engine == DatabaseEngine.POSTGRESQL:
        sql = (
            f'REVOKE ALL PRIVILEGES ON DATABASE "{db.name}" FROM "{user.username}";\n'
            f'REVOKE ALL PRIVILEGES ON ALL TABLES IN SCHEMA public FROM "{user.username}";\n'
            f'REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM "{user.username}";\n'
            f'REVOKE ALL ON SCHEMA public FROM "{user.username}";'
        )
    else:
        # MariaDB/MySQL : ALL PRIVILEGES, GRANT OPTION — une seule ligne pour mysql -e
        sql = (
            f"REVOKE ALL PRIVILEGES, GRANT OPTION ON `{db.name}`.* "
            f"FROM '{user.username}'@'{_escape_sql_literal(user.host)}'; "
            "FLUSH PRIVILEGES;"
        )
    try:
        apply_sql(db.engine, sql, label=f"revoke_{db.engine}_{db.name}_{user.username}")
    except VZoneAPIException as exc:
        # Grant absent / moteur injoignable : on retire quand même le lien panel
        # (comportement type cPanel) et on journalise.
        logger.warning(
            "Revoke SQL échoué pour %s → %s (%s) — suppression panel conservée: %s",
            user.username,
            db.name,
            db.engine,
            exc,
        )
        if not should_execute(db.engine):
            raise
        # Mode live : si le REVOKE échoue car « no such grant », on continue ;
        # sinon on laisse une trace pending pour admin.
        detail = str(getattr(exc, "detail", exc))
        extra = getattr(exc, "extra", None) or {}
        blob = f"{detail} {extra}".lower()
        soft = any(
            s in blob
            for s in ("no such grant", "1141", "1147", "does not exist", "unknown user")
        )
        if not soft:
            _write_pending_sql(
                f"revoke_{db.engine}_{db.name}_{user.username}_failed.sql",
                sql + f"\n-- error: {detail}\n",
            )
    priv.delete()
    write_inventory()


def phpmyadmin_url() -> str:
    return getattr(settings, "VZONE_PHPMYADMIN_URL", "/phpmyadmin/")


def pgadmin_url() -> str:
    return getattr(settings, "VZONE_PGADMIN_URL", "/pgadmin/")


def create_phpmyadmin_sso(user: DatabaseUser) -> dict:
    """Génère un token one-shot pour ouvrir phpMyAdmin déjà authentifié."""
    import json
    import secrets
    import time
    from pathlib import Path

    if user.engine != DatabaseEngine.MYSQL:
        raise VZoneAPIException(
            detail="phpMyAdmin est réservé aux utilisateurs MySQL/MariaDB.",
            code="not_mysql",
            status_code=400,
        )
    if not user.is_active:
        raise VZoneAPIException(detail="Utilisateur SQL inactif.", code="inactive", status_code=400)

    password = user.get_password_plain()
    if not password:
        raise VZoneAPIException(
            detail=(
                "Mot de passe non disponible pour le SSO (utilisateur créé avant cette version). "
                "Réinitialisez le mot de passe SQL dans le panel, puis réessayez."
            ),
            code="no_secret",
            status_code=400,
        )

    sso_dir = Path(
        getattr(settings, "VZONE_PHPMYADMIN_SSO_DIR", None)
        or (Path(settings.VZONE_DATA_ROOT) / "phpmyadmin" / "sso")
    )
    sso_dir.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(32)
    payload = {
        "user": user.username,
        "password": password,
        "host": user.host or "localhost",
        "exp": int(time.time()) + 60,
    }
    token_path = sso_dir / f"{token}.json"
    token_path.write_text(json.dumps(payload), encoding="utf-8")
    try:
        token_path.chmod(0o640)
    except OSError:
        pass

    base = phpmyadmin_url().rstrip("/") + "/"
    return {
        "url": f"{base}vzone-sso.php?t={token}",
        "expires_in": 60,
        "username": user.username,
    }


def overview_for(user: User) -> dict:
    dbs = databases_qs(user)
    users = db_users_qs(user)
    return {
        "databases": dbs.count(),
        "mysql_databases": dbs.filter(engine=DatabaseEngine.MYSQL).count(),
        "postgresql_databases": dbs.filter(engine=DatabaseEngine.POSTGRESQL).count(),
        "users": users.count(),
        "privileges": privileges_qs(user).count(),
        "phpmyadmin_url": phpmyadmin_url(),
        "pgadmin_url": pgadmin_url(),
        "provision_mode": provision_mode(),
    }
