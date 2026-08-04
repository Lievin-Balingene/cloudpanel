"""Restauration d'un compte cPanel vers l'architecture V-zone (identique cPanel)."""
from __future__ import annotations

import logging
import os
import secrets
import shutil
import string
import subprocess
from pathlib import Path
from typing import Callable

from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError

from apps.accounts.models import User
from apps.accounts.services import provision_account_home, validate_system_username
from apps.core.exceptions import VZoneAPIException
from apps.databases.models import Database, DatabaseEngine, DatabaseUser
from apps.databases.services import (
    create_database,
    create_database_user,
    grant_privilege,
    should_execute,
)
from apps.dns.models import DnsRecord, DnsZone
from apps.dns.services import create_zone_with_defaults
from apps.domains.models import Domain
from apps.domains.services import create_domain
from apps.domains.ssl_services import install_custom_certificate
from apps.email.models import MailDomain, Mailbox
from apps.email.services import create_mail_domain, create_mailbox, mailbox_maildir, write_mail_maps
from apps.files.services import ensure_cpanel_tree, personal_home
from apps.ftp.services import create_ftp_account
from apps.packages.models import HostingPackage
from apps.packages.services import apply_package_to_user, get_default_package
from apps.transfer.pkgacct import (
    CpanelAccountBundle,
    list_mailboxes_from_va,
    list_mysql_dumps,
    list_userdata_domains,
    parse_dns_zone_file,
)

logger = logging.getLogger(__name__)

LogFn = Callable[[str], None]


def _log(fn: LogFn | None, msg: str) -> None:
    if fn:
        fn(msg)
    logger.info("transfer: %s", msg)


def _rand_password(length: int = 16) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#%^*"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def _safe_copytree(src: Path, dst: Path) -> None:
    dst.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        target_dir = dst / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for d in dirs:
            (target_dir / d).mkdir(parents=True, exist_ok=True)
        for f in files:
            s = Path(root) / f
            t = target_dir / f
            try:
                shutil.copy2(s, t)
            except OSError as exc:
                logger.warning("Skip copy %s → %s: %s", s, t, exc)


def ensure_target_user(
    *,
    username: str,
    email: str,
    password: str,
    package_name: str = "",
    overwrite: bool = False,
    log: LogFn | None = None,
) -> tuple[User, str]:
    """Crée ou réutilise le compte V-zone (home style cPanel)."""
    username = validate_system_username(username)
    plain = password.strip() or _rand_password()
    if len(plain) < 8:
        plain = _rand_password()

    existing = User.objects.filter(username=username).first()
    if existing and not overwrite:
        raise VZoneAPIException(
            detail=f"Le compte « {username} » existe déjà (activez écrasement pour continuer).",
            code="user_exists",
            status_code=400,
        )

    if existing and overwrite:
        _log(log, f"Réutilisation du compte existant {username}")
        if password.strip():
            try:
                validate_password(plain, user=existing)
            except DjangoValidationError:
                plain = _rand_password(20)
            existing.set_password(plain)
            existing.save(update_fields=["password", "updated_at"])
        provision_account_home(existing)
        return existing, plain

    email = (email or f"{username}@localhost").strip().lower()
    if User.objects.filter(email__iexact=email).exists():
        email = f"{username}.{secrets.token_hex(3)}@transfer.local"

    user = User.objects.create_user(
        email=email,
        username=username,
        password=plain,
        role=User.Role.CLIENT,
        must_change_password=True,
    )
    provision_account_home(user)

    pkg = None
    if package_name:
        pkg = HostingPackage.objects.filter(name__iexact=package_name).first()
    if pkg is None:
        try:
            pkg = get_default_package("client")
        except Exception:  # noqa: BLE001
            pkg = HostingPackage.objects.filter(is_active=True).first()
    if pkg is not None:
        apply_package_to_user(user, pkg)
        _log(log, f"Package appliqué: {pkg.name}")

    _log(log, f"Compte créé: {username} (home cPanel)")
    return user, plain


def restore_homedir(bundle: CpanelAccountBundle, user: User, *, log: LogFn | None = None) -> dict:
    home = personal_home(user)
    ensure_cpanel_tree(home)
    if not bundle.homedir or not bundle.homedir.is_dir():
        _log(log, "Pas de homedir dans l'archive — arbre cPanel vide conservé")
        return {"copied": False, "path": str(home)}

    _log(log, f"Copie homedir → {home}")
    # Copier en préservant public_html, mail, ssl, domains, etc.
    for item in bundle.homedir.iterdir():
        name = item.name
        if name in {".", ".."}:
            continue
        dest = home / name
        if item.is_dir():
            if dest.exists():
                _safe_copytree(item, dest)
            else:
                shutil.copytree(item, dest, dirs_exist_ok=True)
        else:
            try:
                shutil.copy2(item, dest)
            except OSError as exc:
                _log(log, f"Avertissement copie {name}: {exc}")
    ensure_cpanel_tree(home)
    return {"copied": True, "path": str(home)}


def restore_domains(bundle: CpanelAccountBundle, user: User, *, log: LogFn | None = None) -> list[dict]:
    created: list[dict] = []
    domains = list_userdata_domains(bundle)
    primary = next((d for d in domains if d["type"] == "primary"), None)
    parent_obj: Domain | None = None

    # Primary d'abord
    ordered = sorted(domains, key=lambda d: 0 if d["type"] == "primary" else 1)
    for info in ordered:
        name = info["name"]
        dtype = info["type"]
        doc = info.get("documentroot") or ""
        try:
            if Domain.objects.filter(name=name).exists():
                dom = Domain.objects.get(name=name)
                if dom.owner_id != user.id:
                    _log(log, f"Domaine {name} appartient à un autre compte — ignoré")
                    continue
                _log(log, f"Domaine déjà présent: {name}")
                if dtype == "primary":
                    parent_obj = dom
                created.append({"name": name, "status": "exists", "type": dtype})
                continue

            domain_type = Domain.DomainType.PRIMARY
            parent = None
            if dtype == "primary":
                domain_type = Domain.DomainType.PRIMARY
            elif dtype == "subdomain" and parent_obj:
                domain_type = Domain.DomainType.SUBDOMAIN
                parent = parent_obj
            elif dtype == "parked" and parent_obj:
                domain_type = Domain.DomainType.PARKED
                parent = parent_obj
            else:
                domain_type = Domain.DomainType.ADDON

            # document_root relatif au home
            document_root = ""
            if doc:
                home = personal_home(user)
                document_root = str((home / doc).resolve()) if not Path(doc).is_absolute() else doc

            dom = create_domain(
                name=name,
                owner=user,
                domain_type=domain_type,
                parent=parent,
                create_dns_zone=True,
                document_root=document_root,
                notes="import cPanel transfer",
            )
            if domain_type == Domain.DomainType.PRIMARY:
                parent_obj = dom
            created.append({"name": name, "status": "created", "type": domain_type})
            _log(log, f"Domaine importé: {name} ({domain_type})")
        except VZoneAPIException as exc:
            _log(log, f"Domaine {name}: {exc.detail}")
            created.append({"name": name, "status": "error", "error": str(exc.detail)})
        except Exception as exc:  # noqa: BLE001
            _log(log, f"Domaine {name} erreur: {exc}")
            created.append({"name": name, "status": "error", "error": str(exc)})
    return created


def restore_dns(bundle: CpanelAccountBundle, user: User, *, log: LogFn | None = None) -> list[dict]:
    out: list[dict] = []
    if not bundle.dnszones_dir:
        return out
    for path in sorted(bundle.dnszones_dir.iterdir()):
        if not path.is_file():
            continue
        zone_name = path.name.strip().lower().rstrip(".")
        if not zone_name or zone_name.startswith("."):
            continue
        try:
            zone = DnsZone.objects.filter(name=zone_name).first()
            if zone is None:
                zone = create_zone_with_defaults(name=zone_name, owner=user)
            elif zone.owner_id != user.id:
                _log(log, f"Zone DNS {zone_name} autre propriétaire — ignorée")
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            records = parse_dns_zone_file(text, zone_name)
            added = 0
            for rec in records:
                rtype = rec["record_type"]
                if rtype not in {c[0] for c in DnsRecord._meta.get_field("record_type").choices}:
                    # fallback common types
                    if rtype not in {"A", "AAAA", "CNAME", "MX", "TXT", "NS", "SRV", "CAA"}:
                        continue
                exists = DnsRecord.objects.filter(
                    zone=zone,
                    record_type=rtype,
                    name=rec["name"],
                    content=rec["content"],
                ).exists()
                if exists:
                    continue
                DnsRecord.objects.create(
                    zone=zone,
                    record_type=rtype,
                    name=rec["name"],
                    content=rec["content"],
                    ttl=rec.get("ttl"),
                    priority=rec.get("priority"),
                )
                added += 1
            out.append({"zone": zone_name, "records_added": added})
            _log(log, f"DNS {zone_name}: +{added} records")
        except Exception as exc:  # noqa: BLE001
            _log(log, f"DNS {zone_name}: {exc}")
            out.append({"zone": zone_name, "error": str(exc)})
    return out


def _import_mysql_dump_file(db_name: str, dump_path: Path, *, log: LogFn | None = None) -> None:
    if not should_execute(DatabaseEngine.MYSQL):
        pending = Path(settings.VZONE_DATA_ROOT) / "databases" / "pending" / f"import_{db_name}.sql"
        pending.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dump_path, pending)
        _log(log, f"Dump MySQL enregistré (mock): {pending.name}")
        return
    host = settings.VZONE_MYSQL_HOST
    port = str(getattr(settings, "VZONE_MYSQL_PORT", 3306))
    user = settings.VZONE_MYSQL_ADMIN_USER
    password = getattr(settings, "VZONE_MYSQL_ADMIN_PASSWORD", "")
    binary = shutil.which("mysql") or "mysql"
    cmd = [binary, f"-h{host}", f"-P{port}", f"-u{user}", db_name]
    env = os.environ.copy()
    if password:
        env["MYSQL_PWD"] = password
    with dump_path.open("rb") as fh:
        try:
            subprocess.run(
                cmd,
                check=True,
                stdin=fh,
                capture_output=True,
                env=env,
                timeout=3600,
            )
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
            stderr = getattr(exc, "stderr", b"")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            raise VZoneAPIException(
                detail=f"Import MySQL échoué pour {db_name}: {stderr or exc}",
                code="mysql_import_failed",
                status_code=502,
            ) from exc


def restore_databases(bundle: CpanelAccountBundle, user: User, *, log: LogFn | None = None) -> list[dict]:
    out: list[dict] = []
    dumps = list_mysql_dumps(bundle)
    # mysql.sql global (GRANTs) — exécuter après création des bases si possible
    for dump in dumps:
        name = dump["name"]
        path: Path = dump["path"]
        try:
            # create_database préfixe déjà username_
            short = name
            prefix = f"{user.username}_"
            if short.startswith(prefix):
                short = short[len(prefix) :]
            db = Database.objects.filter(owner=user, engine=DatabaseEngine.MYSQL, name__endswith=name).first()
            if db is None:
                db = create_database(owner=user, name=short or name, engine=DatabaseEngine.MYSQL, notes="cPanel import")
            _import_mysql_dump_file(db.name, path, log=log)
            # User DB homonyme
            try:
                db_user = DatabaseUser.objects.filter(
                    owner=user, engine=DatabaseEngine.MYSQL, username=db.name
                ).first()
                if db_user is None:
                    db_user = create_database_user(
                        owner=user,
                        username=short or name,
                        password=_rand_password(18),
                        engine=DatabaseEngine.MYSQL,
                        notes="cPanel import",
                    )
                grant_privilege(database=db, user=db_user, privileges="ALL")
            except VZoneAPIException as exc:
                _log(log, f"Privs {name}: {exc.detail}")
            out.append({"database": db.name, "status": "imported"})
            _log(log, f"Base importée: {db.name}")
        except VZoneAPIException as exc:
            _log(log, f"Base {name}: {exc.detail}")
            out.append({"database": name, "status": "error", "error": str(exc.detail)})
        except Exception as exc:  # noqa: BLE001
            _log(log, f"Base {name}: {exc}")
            out.append({"database": name, "status": "error", "error": str(exc)})

    if bundle.mysql_sql and bundle.mysql_sql.is_file():
        _log(log, "mysql.sql (GRANTs cPanel) présent — non appliqué tel quel (sécurité); users DB créés par base.")
    return out


def restore_email(bundle: CpanelAccountBundle, user: User, *, log: LogFn | None = None) -> list[dict]:
    out: list[dict] = []
    boxes = list_mailboxes_from_va(bundle)
    domains_needed = sorted({b["domain"] for b in boxes})
    # Aussi domaines web → mail domain
    for d in Domain.objects.filter(owner=user):
        if d.name not in domains_needed:
            domains_needed.append(d.name)

    mail_domains: dict[str, MailDomain] = {}
    for dname in domains_needed:
        md = MailDomain.objects.filter(owner=user, name=dname).first()
        if md is None:
            try:
                domain_obj = Domain.objects.filter(owner=user, name=dname).first()
                md = create_mail_domain(
                    owner=user,
                    name=dname,
                    domain_id=domain_obj.pk if domain_obj else None,
                    enable_dns=False,
                )
                _log(log, f"Domaine mail: {dname}")
            except VZoneAPIException as exc:
                _log(log, f"Mail domain {dname}: {exc.detail}")
                continue
        mail_domains[dname] = md

    for box in boxes:
        md = mail_domains.get(box["domain"])
        if md is None:
            continue
        address = box["address"]
        try:
            existing = Mailbox.objects.filter(mail_domain=md, local_part=box["local_part"]).first()
            if existing is None:
                pwd = _rand_password(14)
                existing = create_mailbox(
                    mail_domain=md,
                    local_part=box["local_part"],
                    password=pwd,
                    quota_mb=int(box.get("quota_mb") or 250),
                    notes="cPanel import — mot de passe régénéré (hash non réversible)",
                )
                out.append({"address": address, "status": "created", "password_reset": True})
            else:
                out.append({"address": address, "status": "exists"})

            # Copier maildir depuis archive si présent
            if bundle.homedir:
                src = bundle.homedir / "mail" / box["domain"] / box["local_part"]
                if src.is_dir():
                    dest = Path(existing.maildir) if existing.maildir else mailbox_maildir(user, address)
                    _safe_copytree(src, dest)
                    existing.maildir = str(dest)
                    existing.save(update_fields=["maildir", "updated_at"])
                    _log(log, f"Maildir copié: {address}")
        except VZoneAPIException as exc:
            _log(log, f"Mailbox {address}: {exc.detail}")
            out.append({"address": address, "status": "error", "error": str(exc.detail)})
        except Exception as exc:  # noqa: BLE001
            _log(log, f"Mailbox {address}: {exc}")
            out.append({"address": address, "status": "error", "error": str(exc)})

    try:
        write_mail_maps()
    except Exception:  # noqa: BLE001
        pass
    return out


def restore_ssl(bundle: CpanelAccountBundle, user: User, *, log: LogFn | None = None) -> list[dict]:
    out: list[dict] = []
    # apache_tls/<domain>/{cert,key,ca-bundle} ou ssl/
    candidates: list[Path] = []
    if bundle.apache_tls_dir:
        candidates.append(bundle.apache_tls_dir)
    if bundle.ssl_dir:
        candidates.append(bundle.ssl_dir)
    if bundle.homedir and (bundle.homedir / "ssl").is_dir():
        candidates.append(bundle.homedir / "ssl")

    seen_domains: set[str] = set()
    for base in candidates:
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            name = path.name.lower()
            # Chercher paires cert/key
            if name not in {"cert", "certificate", "cert.pem", "crt.pem"} and not name.endswith(".crt"):
                continue
            domain_guess = path.parent.name.lower().rstrip(".")
            if "." not in domain_guess:
                continue
            if domain_guess in seen_domains:
                continue
            key_path = None
            for kn in ("key", "privatekey", "privkey.pem", "key.pem"):
                kp = path.parent / kn
                if kp.is_file():
                    key_path = kp
                    break
            if key_path is None:
                # parfois domain.crt / domain.key
                stem = path.stem
                for ext in (".key", ".key.pem"):
                    kp = path.with_name(stem + ext)
                    if kp.is_file():
                        key_path = kp
                        break
            if key_path is None:
                continue
            ca = ""
            for cn in ("ca-bundle", "cabundle", "chain", "chain.pem"):
                cp = path.parent / cn
                if cp.is_file():
                    ca = cp.read_text(encoding="utf-8", errors="replace")
                    break
            domain = Domain.objects.filter(owner=user, name=domain_guess).first()
            if domain is None:
                continue
            try:
                install_custom_certificate(
                    domain,
                    certificate_pem=path.read_text(encoding="utf-8", errors="replace"),
                    private_key_pem=key_path.read_text(encoding="utf-8", errors="replace"),
                    chain_pem=ca,
                )
                seen_domains.add(domain_guess)
                out.append({"domain": domain_guess, "status": "installed"})
                _log(log, f"SSL installé: {domain_guess}")
            except VZoneAPIException as exc:
                _log(log, f"SSL {domain_guess}: {exc.detail}")
                out.append({"domain": domain_guess, "status": "error", "error": str(exc.detail)})
    return out


def restore_ftp(bundle: CpanelAccountBundle, user: User, *, log: LogFn | None = None) -> list[dict]:
    out: list[dict] = []
    if not bundle.ftp_passwd or not bundle.ftp_passwd.is_file():
        return out
    for line in bundle.ftp_passwd.read_text(encoding="utf-8", errors="replace").splitlines():
        parts = line.strip().split(":")
        if len(parts) < 2:
            continue
        login = parts[0].strip()
        if not login or login == user.username:
            continue
        # username often user_ftpuser
        short = login
        prefix = f"{user.username}_"
        if short.startswith(prefix):
            short = short[len(prefix) :]
        try:
            create_ftp_account(
                owner=user,
                username=short or login,
                password=_rand_password(14),
                relative_directory="public_html",
                notes="cPanel import — mot de passe régénéré",
            )
            out.append({"username": login, "status": "created", "password_reset": True})
            _log(log, f"FTP créé: {login} (mdp régénéré)")
        except VZoneAPIException as exc:
            _log(log, f"FTP {login}: {exc.detail}")
            out.append({"username": login, "status": "error", "error": str(exc.detail)})
    return out


def restore_account(
    bundle: CpanelAccountBundle,
    *,
    username: str,
    email: str = "",
    password: str = "",
    package_name: str = "",
    overwrite: bool = False,
    options: dict | None = None,
    log: LogFn | None = None,
) -> dict:
    opts = {
        "home": True,
        "domains": True,
        "dns": True,
        "databases": True,
        "email": True,
        "ssl": True,
        "ftp": True,
        **(options or {}),
    }
    for w in bundle.warnings:
        _log(log, f"Avertissement: {w}")

    user, plain = ensure_target_user(
        username=username or bundle.username,
        email=email or bundle.contact_email,
        password=password,
        package_name=package_name,
        overwrite=overwrite,
        log=log,
    )

    result: dict = {
        "username": user.username,
        "email": user.email,
        "password": plain,
        "password_note": "Mot de passe compte panel (changez-le après connexion).",
        "home": None,
        "domains": [],
        "dns": [],
        "databases": [],
        "email": [],
        "ssl": [],
        "ftp": [],
    }

    if opts.get("home"):
        result["home"] = restore_homedir(bundle, user, log=log)
    if opts.get("domains"):
        result["domains"] = restore_domains(bundle, user, log=log)
    if opts.get("dns"):
        result["dns"] = restore_dns(bundle, user, log=log)
    if opts.get("databases"):
        result["databases"] = restore_databases(bundle, user, log=log)
    if opts.get("email"):
        result["email"] = restore_email(bundle, user, log=log)
    if opts.get("ssl"):
        result["ssl"] = restore_ssl(bundle, user, log=log)
    if opts.get("ftp"):
        result["ftp"] = restore_ftp(bundle, user, log=log)

    _log(log, "Transfert terminé")
    return result
