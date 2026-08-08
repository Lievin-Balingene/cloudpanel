"""Tools bases de données (mutations ; lecture via check_database existant)."""
from __future__ import annotations

from typing import Any

from apps.accounts.models import User
from apps.ai_assistant.tools import register_tool
from apps.ai_assistant.tools.helpers import err, ok, require_int, require_str, run_service


@register_tool(
    name="list_databases",
    description="Liste les bases et utilisateurs DB du compte (sans mots de passe).",
    parameters={"type": "object", "properties": {}, "additionalProperties": False},
)
def list_databases(user: User, params: dict[str, Any]) -> dict[str, Any]:
    del params
    from apps.databases.services import databases_qs, db_users_qs, overview_for

    dbs = [
        {"id": d.pk, "name": d.name, "engine": d.engine, "notes": d.notes or ""}
        for d in databases_qs(user)[:50]
    ]
    users = [
        {"id": u.pk, "username": u.username, "engine": u.engine, "host": u.host}
        for u in db_users_qs(user)[:50]
    ]
    return ok(overview=overview_for(user), databases=dbs, users=users)


@register_tool(
    name="create_database",
    description="Crée une base MySQL/PostgreSQL (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "name": {"type": "string"},
            "engine": {"type": "string", "enum": ["mysql", "postgresql"]},
            "notes": {"type": "string"},
        },
        "required": ["name"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def create_database(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.databases.models import DatabaseEngine
    from apps.databases.services import create_database as svc

    name = require_str(params, "name", max_len=64)
    if not name:
        return err("name requis")
    engine = require_str(params, "engine", default=DatabaseEngine.MYSQL) or DatabaseEngine.MYSQL

    def _run():
        db = svc(
            owner=user,
            name=name,
            engine=engine,
            notes=require_str(params, "notes", max_len=200),
        )
        return {"id": db.pk, "name": db.name, "engine": db.engine}

    return run_service(_run)


@register_tool(
    name="delete_database",
    description="Supprime une base de données (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {"db_id": {"type": "integer"}},
        "required": ["db_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_database(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.databases.services import databases_qs, delete_database as svc

    db_id = require_int(params, "db_id")
    db = databases_qs(user).filter(pk=db_id).first() if db_id else None
    if not db:
        return err("Base introuvable", "not_found")
    name = db.name

    def _run():
        svc(db)
        return {"deleted": name}

    return run_service(_run)


@register_tool(
    name="create_db_user",
    description="Crée un utilisateur DB (confirmation requise). Le mot de passe n'est jamais renvoyé.",
    parameters={
        "type": "object",
        "properties": {
            "username": {"type": "string"},
            "password": {"type": "string"},
            "engine": {"type": "string", "enum": ["mysql", "postgresql"]},
            "host": {"type": "string"},
        },
        "required": ["username", "password"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def create_db_user(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.databases.models import DatabaseEngine
    from apps.databases.services import create_database_user

    username = require_str(params, "username", max_len=64)
    password = str(params.get("password") or "")
    if not username or len(password) < 8:
        return err("username + password (≥8) requis")

    def _run():
        u = create_database_user(
            owner=user,
            username=username,
            password=password,
            engine=require_str(params, "engine", default=DatabaseEngine.MYSQL) or DatabaseEngine.MYSQL,
            host=require_str(params, "host", default="localhost") or "localhost",
        )
        return {"id": u.pk, "username": u.username, "engine": u.engine, "host": u.host}

    return run_service(_run)


@register_tool(
    name="delete_db_user",
    description="Supprime un utilisateur DB (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {"user_id": {"type": "integer"}},
        "required": ["user_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def delete_db_user(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.databases.services import db_users_qs, delete_database_user

    uid = require_int(params, "user_id")
    db_user = db_users_qs(user).filter(pk=uid).first() if uid else None
    if not db_user:
        return err("Utilisateur DB introuvable", "not_found")
    uname = db_user.username

    def _run():
        delete_database_user(db_user)
        return {"deleted": uname}

    return run_service(_run)


@register_tool(
    name="grant_db_privilege",
    description="Accorde des privilèges DB user→database (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {
            "db_id": {"type": "integer"},
            "user_id": {"type": "integer"},
            "privileges": {"type": "string", "enum": ["ALL", "READ", "WRITE"]},
        },
        "required": ["db_id", "user_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def grant_db_privilege(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.databases.services import databases_qs, db_users_qs, grant_privilege

    db = databases_qs(user).filter(pk=require_int(params, "db_id")).first()
    db_user = db_users_qs(user).filter(pk=require_int(params, "user_id")).first()
    if not db or not db_user:
        return err("db_id ou user_id introuvable", "not_found")

    def _run():
        priv = grant_privilege(
            database=db,
            user=db_user,
            privileges=require_str(params, "privileges", default="ALL") or "ALL",
        )
        return {"id": getattr(priv, "pk", None), "database": db.name, "user": db_user.username}

    return run_service(_run)


@register_tool(
    name="revoke_db_privilege",
    description="Révoque un privilège DB (confirmation requise).",
    parameters={
        "type": "object",
        "properties": {"privilege_id": {"type": "integer"}},
        "required": ["privilege_id"],
        "additionalProperties": False,
    },
    dangerous=True,
)
def revoke_db_privilege(user: User, params: dict[str, Any]) -> dict[str, Any]:
    from apps.databases.services import privileges_qs, revoke_privilege

    priv = privileges_qs(user).filter(pk=require_int(params, "privilege_id")).first()
    if not priv:
        return err("Privilège introuvable", "not_found")

    def _run():
        revoke_privilege(priv)
        return {"revoked": True}

    return run_service(_run)
