"""Détection et lecture d'archives cPanel (pkgacct / cpmove / backup)."""
from __future__ import annotations

import json
import re
import shutil
import tarfile
from dataclasses import dataclass, field
from pathlib import Path

from apps.core.exceptions import VZoneAPIException

USERDATA_KEYS = re.compile(r"^([A-Za-z0-9_]+):\s*(.*)$")


@dataclass
class CpanelAccountBundle:
    """Racine extraite d'un compte cPanel."""

    root: Path
    username: str
    main_domain: str = ""
    contact_email: str = ""
    homedir: Path | None = None
    userdata_dir: Path | None = None
    dnszones_dir: Path | None = None
    mysql_dir: Path | None = None
    mysql_sql: Path | None = None
    pgsql_dir: Path | None = None
    ssl_dir: Path | None = None
    apache_tls_dir: Path | None = None
    va_dir: Path | None = None  # virtual accounts / mail passwords
    ftp_passwd: Path | None = None
    cp_dir: Path | None = None
    meta: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def extract_archive(archive: Path, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    name = archive.name.lower()
    try:
        if name.endswith(".zip"):
            import zipfile

            with zipfile.ZipFile(archive, "r") as zf:
                zf.extractall(dest)
        else:
            with tarfile.open(archive, "r:*") as tf:
                # Protection zip/tar slip
                for member in tf.getmembers():
                    member_path = (dest / member.name).resolve()
                    if not str(member_path).startswith(str(dest.resolve())):
                        raise VZoneAPIException(
                            detail="Archive invalide (path traversal).",
                            code="unsafe_archive",
                            status_code=400,
                        )
                tf.extractall(dest)
    except VZoneAPIException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise VZoneAPIException(
            detail=f"Impossible d'extraire l'archive: {exc}",
            code="extract_failed",
            status_code=400,
        ) from exc
    return dest


def _looks_like_account_root(path: Path) -> bool:
    if not path.is_dir():
        return False
    markers = (
        "homedir",
        "homedir.tar",
        "userdata",
        "mysql.sql",
        "mysql",
        "dnszones",
        "cp",
        "meta",
        "version",
        "va",
    )
    names = {p.name for p in path.iterdir()}
    return sum(1 for m in markers if m in names) >= 2


def find_account_root(extracted: Path) -> Path:
    """Trouve le dossier compte dans une archive cpmove/backup."""
    if _looks_like_account_root(extracted):
        return extracted
    candidates: list[Path] = []
    for child in sorted(extracted.iterdir()):
        if child.is_dir() and _looks_like_account_root(child):
            candidates.append(child)
        elif child.is_dir():
            for sub in child.iterdir():
                if sub.is_dir() and _looks_like_account_root(sub):
                    candidates.append(sub)
    if not candidates:
        # Fallback: premier sous-dossier
        dirs = [p for p in extracted.iterdir() if p.is_dir()]
        if len(dirs) == 1:
            return dirs[0]
        raise VZoneAPIException(
            detail="Structure archive cPanel introuvable (homedir/userdata/mysql attendus).",
            code="invalid_cpanel_archive",
            status_code=400,
        )
    return candidates[0]


def _parse_kv_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return data
    text = text.strip()
    if text.startswith("{"):
        try:
            raw = json.loads(text)
            if isinstance(raw, dict):
                return {str(k): "" if v is None else str(v) for k, v in raw.items()}
        except json.JSONDecodeError:
            pass
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = USERDATA_KEYS.match(line)
        if m:
            data[m.group(1)] = m.group(2).strip()
            continue
        if "=" in line:
            k, _, v = line.partition("=")
            data[k.strip()] = v.strip()
    return data


def _guess_username(root: Path, override: str = "") -> str:
    if override:
        return override.strip().lower()
    for meta_name in ("meta/user", "cp/user", "username", "user"):
        p = root / meta_name
        if p.is_file():
            val = p.read_text(encoding="utf-8", errors="replace").strip().splitlines()[0].strip()
            if val:
                return val.lower()
    # userdata/main
    main = root / "userdata" / "main"
    if main.is_file():
        kv = _parse_kv_file(main)
        for key in ("user", "username", "owner"):
            if kv.get(key):
                return kv[key].strip().lower()
    return root.name.lower().removeprefix("cpmove-").removeprefix("backup-").split("-")[0]


def _ensure_homedir(root: Path, warnings: list[str]) -> Path | None:
    homedir = root / "homedir"
    if homedir.is_dir():
        return homedir
    nested = root / "homedir.tar"
    if nested.is_file():
        target = root / "homedir"
        target.mkdir(parents=True, exist_ok=True)
        try:
            with tarfile.open(nested, "r:*") as tf:
                tf.extractall(target)
            # parfois le tar contient un seul dossier
            children = [p for p in target.iterdir()]
            if len(children) == 1 and children[0].is_dir():
                # remonter contenu si ce n'est pas déjà public_html
                inner = children[0]
                if not (target / "public_html").exists() and (inner / "public_html").exists():
                    for item in inner.iterdir():
                        dest = target / item.name
                        if not dest.exists():
                            shutil.move(str(item), str(dest))
                    try:
                        inner.rmdir()
                    except OSError:
                        pass
            return target
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Échec extraction homedir.tar: {exc}")
    # Parfois les fichiers sont à la racine du compte
    if (root / "public_html").is_dir():
        return root
    return None


def inspect_bundle(root: Path, *, username_override: str = "") -> CpanelAccountBundle:
    username = _guess_username(root, username_override)
    warnings: list[str] = []
    homedir = _ensure_homedir(root, warnings)

    userdata = root / "userdata"
    dnszones = root / "dnszones"
    mysql_dir = root / "mysql"
    mysql_sql = root / "mysql.sql"
    pgsql = root / "pgsql" if (root / "pgsql").exists() else root / "postgresql"
    ssl = root / "ssl"
    apache_tls = root / "apache_tls"
    va = root / "va"
    cp = root / "cp"

    ftp_candidates = [
        root / "proftpdpasswd",
        root / "ftp" / "proftpdpasswd",
        root / "etc" / "proftpdpasswd",
        root / "homedir" / "etc" / "ftpquota",
    ]
    ftp_passwd = next((p for p in ftp_candidates if p.is_file()), None)

    meta: dict = {}
    main = userdata / "main" if userdata.is_dir() else None
    if main and main.is_file():
        meta.update(_parse_kv_file(main))

    contact = ""
    for key in ("contactemail", "contact_email", "email"):
        if meta.get(key):
            contact = meta[key]
            break
    if not contact:
        for p in (cp / "contactemail", root / "meta" / "contactemail"):
            if p.is_file():
                contact = p.read_text(encoding="utf-8", errors="replace").strip()
                break

    main_domain = (
        meta.get("main_domain")
        or meta.get("maindomain")
        or meta.get("servername")
        or ""
    ).strip().lower().rstrip(".")

    return CpanelAccountBundle(
        root=root,
        username=username,
        main_domain=main_domain,
        contact_email=contact,
        homedir=homedir,
        userdata_dir=userdata if userdata.is_dir() else None,
        dnszones_dir=dnszones if dnszones.is_dir() else None,
        mysql_dir=mysql_dir if mysql_dir.is_dir() else None,
        mysql_sql=mysql_sql if mysql_sql.is_file() else None,
        pgsql_dir=pgsql if pgsql.is_dir() else None,
        ssl_dir=ssl if ssl.is_dir() else None,
        apache_tls_dir=apache_tls if apache_tls.is_dir() else None,
        va_dir=va if va.is_dir() else None,
        ftp_passwd=ftp_passwd,
        cp_dir=cp if cp.is_dir() else None,
        meta=meta,
        warnings=warnings,
    )


def list_userdata_domains(bundle: CpanelAccountBundle) -> list[dict]:
    """Liste les vhosts depuis userdata/ (fichiers par domaine)."""
    results: list[dict] = []
    if not bundle.userdata_dir:
        if bundle.main_domain:
            results.append(
                {
                    "name": bundle.main_domain,
                    "type": "primary",
                    "documentroot": "public_html",
                    "serveralias": f"www.{bundle.main_domain}",
                }
            )
        return results

    skip = {"main", "cache", "ssl", "standard"}
    for path in sorted(bundle.userdata_dir.iterdir()):
        if not path.is_file() or path.name in skip or path.name.startswith("."):
            continue
        if path.suffix in {".cache", ".json.bak"}:
            continue
        kv = _parse_kv_file(path)
        name = (
            kv.get("servername")
            or kv.get("server_name")
            or path.name.replace("_", ".")
        ).strip().lower().rstrip(".")
        if not name or "." not in name:
            continue
        docroot = kv.get("documentroot") or kv.get("document_root") or ""
        # Relatif au home cPanel
        if docroot.startswith("/home/") or docroot.startswith("/home2/"):
            parts = Path(docroot).parts
            # /home/user/public_html → public_html
            if len(parts) >= 4:
                docroot = "/".join(parts[3:])
            else:
                docroot = "public_html"
        elif docroot.startswith("/"):
            docroot = docroot.lstrip("/")
        domain_type = "addon"
        if name == bundle.main_domain or path.name == "main":
            domain_type = "primary"
        elif kv.get("type", "").lower() in {"sub", "subdomain"}:
            domain_type = "subdomain"
        elif "parked" in kv.get("type", "").lower():
            domain_type = "parked"
        results.append(
            {
                "name": name,
                "type": domain_type,
                "documentroot": docroot or ("public_html" if domain_type == "primary" else name),
                "serveralias": kv.get("serveralias") or kv.get("server_alias") or "",
                "raw": kv,
            }
        )

    # Dédupliquer par nom
    seen: set[str] = set()
    unique: list[dict] = []
    for item in results:
        if item["name"] in seen:
            continue
        seen.add(item["name"])
        unique.append(item)
    if bundle.main_domain and bundle.main_domain not in seen:
        unique.insert(
            0,
            {
                "name": bundle.main_domain,
                "type": "primary",
                "documentroot": "public_html",
                "serveralias": f"www.{bundle.main_domain}",
            },
        )
    # Marquer primary
    if unique and not any(i["type"] == "primary" for i in unique):
        unique[0]["type"] = "primary"
        unique[0]["documentroot"] = unique[0].get("documentroot") or "public_html"
    return unique


def parse_dns_zone_file(text: str, zone_name: str) -> list[dict]:
    """Parse simplifié d'un fichier de zone BIND cPanel."""
    records: list[dict] = []
    zone = zone_name.rstrip(".") + "."
    for raw in text.splitlines():
        line = raw.split(";", 1)[0].strip()
        if not line or line.startswith("$"):
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        # name ttl IN type content...  OR name IN type content
        name = parts[0]
        idx = 1
        ttl = None
        if parts[1].isdigit():
            ttl = int(parts[1])
            idx = 2
        if idx < len(parts) and parts[idx].upper() == "IN":
            idx += 1
        if idx >= len(parts):
            continue
        rtype = parts[idx].upper()
        idx += 1
        if rtype in {"SOA", "RRSIG", "NSEC", "DNSKEY"}:
            continue
        priority = None
        if rtype in {"MX", "SRV"} and idx < len(parts) and parts[idx].isdigit():
            priority = int(parts[idx])
            idx += 1
        content = " ".join(parts[idx:]).strip().strip('"')
        if not content:
            continue
        if name in {"@", zone, zone.rstrip(".")}:
            rel = "@"
        elif name.endswith("." + zone) or name.endswith("." + zone.rstrip(".")):
            rel = name[: -len(zone) - 1].rstrip(".") or "@"
        elif name.endswith("."):
            rel = name.rstrip(".")
        else:
            rel = name
        records.append(
            {
                "name": rel,
                "record_type": rtype,
                "content": content.rstrip("."),
                "ttl": ttl,
                "priority": priority,
            }
        )
    return records


def list_mysql_dumps(bundle: CpanelAccountBundle) -> list[dict]:
    """Bases MySQL : fichiers mysql/<db>.sql (+ .create optionnel)."""
    dumps: list[dict] = []
    if bundle.mysql_dir:
        for path in sorted(bundle.mysql_dir.glob("*.sql")):
            name = path.stem
            if name.endswith(".create"):
                continue
            dumps.append({"name": name, "path": path, "engine": "mysql"})
    return dumps


def list_mailboxes_from_va(bundle: CpanelAccountBundle) -> list[dict]:
    """Comptes mail depuis va/ (shadow-like) ou homedir/etc/<domain>/passwd."""
    boxes: list[dict] = []
    seen: set[str] = set()

    def add(address: str, password_hash: str = "", quota: int = 0) -> None:
        address = address.strip().lower()
        if "@" not in address or address in seen:
            return
        local, _, domain = address.partition("@")
        if not local or not domain:
            return
        seen.add(address)
        boxes.append(
            {
                "address": address,
                "local_part": local,
                "domain": domain,
                "password_hash": password_hash,
                "quota_mb": quota or 250,
            }
        )

    if bundle.va_dir:
        for path in bundle.va_dir.rglob("*"):
            if not path.is_file():
                continue
            # Formats : email:hash  ou fichiers nommés email
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for line in text.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if ":" in line and "@" in line.split(":", 1)[0]:
                    email, _, rest = line.partition(":")
                    add(email, rest.split(":")[0])
                elif "@" in path.name:
                    add(path.name.replace("_", "@") if "_at_" not in path.name else path.name)

    # cPanel: homedir/etc/<domain>/passwd  (user:x:uid:gid:quota:…)
    etc = None
    if bundle.homedir:
        etc = bundle.homedir / "etc"
    if etc and etc.is_dir():
        for domain_dir in etc.iterdir():
            if not domain_dir.is_dir():
                continue
            passwd = domain_dir / "passwd"
            shadow = domain_dir / "shadow"
            hashes: dict[str, str] = {}
            if shadow.is_file():
                for line in shadow.read_text(encoding="utf-8", errors="replace").splitlines():
                    if ":" in line:
                        u, _, h = line.partition(":")
                        hashes[u.strip()] = h.split(":")[0]
            if passwd.is_file():
                for line in passwd.read_text(encoding="utf-8", errors="replace").splitlines():
                    parts = line.split(":")
                    if not parts:
                        continue
                    local = parts[0].strip()
                    if not local:
                        continue
                    add(f"{local}@{domain_dir.name}", hashes.get(local, ""))

    # Maildirs présents sans compte : scanner mail/
    if bundle.homedir:
        mail_root = bundle.homedir / "mail"
        if mail_root.is_dir():
            for domain_dir in mail_root.iterdir():
                if not domain_dir.is_dir() or domain_dir.name.startswith("."):
                    continue
                if "@" in domain_dir.name:
                    continue
                for local_dir in domain_dir.iterdir():
                    if local_dir.is_dir() and not local_dir.name.startswith("."):
                        add(f"{local_dir.name}@{domain_dir.name}")

    return boxes
