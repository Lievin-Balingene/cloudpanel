"""Opérations filesystem sécurisées (jail dans le home utilisateur)."""
from __future__ import annotations

import mimetypes
import os
import re
import shutil
import stat
import tarfile
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterable

from django.conf import settings

from apps.accounts.models import User
from apps.core.exceptions import VZoneAPIException

MAX_EDITOR_BYTES = 2 * 1024 * 1024  # 2 Mo
MAX_UPLOAD_BYTES = 128 * 1024 * 1024  # 128 Mo
TEXT_EXTENSIONS = {
    ".txt",
    ".md",
    ".json",
    ".yml",
    ".yaml",
    ".xml",
    ".html",
    ".htm",
    ".css",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".py",
    ".php",
    ".ini",
    ".conf",
    ".env",
    ".sh",
    ".sql",
    ".log",
    ".csv",
    ".toml",
    ".cfg",
}


@dataclass(slots=True)
class FileEntry:
    name: str
    path: str
    is_dir: bool
    size: int
    modified_at: str
    permissions: str
    mode: int
    mime: str | None
    is_text: bool


def ensure_cpanel_tree(personal: Path) -> None:
    """Arborescence type cPanel sous le home du compte."""
    from apps.domains.fsutils import apply_tree_permissions, secure_directory, try_chown_vzone

    personal.mkdir(parents=True, exist_ok=True)
    for sub in ("public_html", "mail", "tmp", "logs", "etc", "ssl", ".trash", "domains"):
        secure_directory(personal / sub, 0o755)
    secure_directory(personal / "public_html" / "cgi-bin", 0o755)
    www = personal / "www"
    if not www.exists() and not www.is_symlink():
        try:
            www.symlink_to("public_html")
        except OSError:
            secure_directory(www, 0o755)
    apply_tree_permissions(personal / "public_html", dir_mode=0o755, file_mode=0o644)
    try_chown_vzone(personal)


def personal_home(user: User) -> Path:
    """Home personnel du compte (jamais le HOME_ROOT global admin)."""
    root_base = Path(settings.VZONE_HOME_ROOT)
    if user.role == User.Role.ADMINISTRATOR:
        return (root_base / "admin").resolve()
    home_name = user.system_username or user.username
    return (root_base / home_name).resolve()


def user_home(user: User) -> Path:
    """Racine jailée du compte (toujours writable par le processus panel)."""
    root_base = Path(settings.VZONE_HOME_ROOT)
    try:
        root_base.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise VZoneAPIException(
            detail=f"Répertoire homes inaccessible ({root_base}): {exc}",
            code="homes_unavailable",
            status_code=500,
        ) from exc

    if user.role == User.Role.ADMINISTRATOR:
        # Admins : vue globale sous HOME_ROOT, avec home personnel admin/
        root = root_base
        personal = root_base / "admin"
    else:
        home_name = user.system_username or user.username
        root = root_base / home_name
        personal = root

    try:
        root.mkdir(parents=True, exist_ok=True)
        ensure_cpanel_tree(personal)
    except OSError as exc:
        raise VZoneAPIException(
            detail=(
                "Impossible d'écrire dans l'espace fichiers. "
                f"Vérifiez VZONE_HOME_ROOT et les droits ({exc})."
            ),
            code="homes_permission",
            status_code=500,
        ) from exc
    return root.resolve()


def _fs_write_error(exc: OSError) -> VZoneAPIException:
    return VZoneAPIException(
        detail=f"Écriture fichier impossible: {exc}",
        code="fs_permission",
        status_code=500,
    )


def resolve_path(user: User, relative: str | None = None) -> Path:
    """Résout un chemin relatif et empêche les escapes (path traversal)."""
    root = user_home(user)
    rel = (relative or "").replace("\\", "/").lstrip("/")
    if ".." in Path(rel).parts:
        raise VZoneAPIException(
            detail="Chemin invalide (traversal interdit).",
            code="invalid_path",
            status_code=400,
        )
    target = (root / rel).resolve() if rel else root
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise VZoneAPIException(
            detail="Accès hors de l'espace autorisé.",
            code="path_forbidden",
            status_code=403,
        ) from exc
    return target


def relative_to_home(user: User, path: Path) -> str:
    root = user_home(user)
    rel = path.resolve().relative_to(root)
    return "" if str(rel) == "." else rel.as_posix()


def _mode_string(mode: int) -> str:
    return stat.filemode(mode)


def _is_text_file(path: Path) -> bool:
    if path.suffix.lower() in TEXT_EXTENSIONS:
        return True
    mime, _ = mimetypes.guess_type(str(path))
    return bool(mime and mime.startswith("text/"))


def entry_from_path(user: User, path: Path) -> FileEntry:
    st = path.stat()
    mime, _ = mimetypes.guess_type(str(path))
    return FileEntry(
        name=path.name or "/",
        path=relative_to_home(user, path),
        is_dir=path.is_dir(),
        size=0 if path.is_dir() else st.st_size,
        modified_at=datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
        permissions=_mode_string(st.st_mode),
        mode=stat.S_IMODE(st.st_mode),
        mime=mime,
        is_text=_is_text_file(path) if path.is_file() else False,
    )


def list_directory(user: User, relative: str | None = None) -> dict:
    path = resolve_path(user, relative)
    if not path.exists():
        raise VZoneAPIException(detail="Chemin introuvable.", code="not_found", status_code=404)
    if not path.is_dir():
        raise VZoneAPIException(detail="Ce chemin n'est pas un dossier.", code="not_directory", status_code=400)
    entries = [entry_from_path(user, child) for child in path.iterdir()]
    entries.sort(key=lambda e: (not e.is_dir, e.name.lower()))
    return {
        "cwd": relative_to_home(user, path),
        "root": str(user_home(user)),
        "entries": [asdict(e) for e in entries],
    }


def mkdir(user: User, relative_parent: str, name: str) -> FileEntry:
    if not re.match(r"^[^\\/:*?\"<>|]+$", name) or name in {".", ".."}:
        raise VZoneAPIException(detail="Nom de dossier invalide.", code="invalid_name", status_code=400)
    parent = resolve_path(user, relative_parent)
    if not parent.is_dir():
        raise VZoneAPIException(detail="Dossier parent invalide.", code="not_directory", status_code=400)
    target = parent / name
    if target.exists():
        raise VZoneAPIException(detail="Ce dossier existe déjà.", code="exists", status_code=400)
    try:
        target.mkdir()
    except OSError as exc:
        raise _fs_write_error(exc) from exc
    return entry_from_path(user, target)


def create_file(user: User, relative_parent: str, name: str, content: str = "") -> FileEntry:
    if not re.match(r"^[^\\/:*?\"<>|]+$", name) or name in {".", ".."}:
        raise VZoneAPIException(detail="Nom de fichier invalide.", code="invalid_name", status_code=400)
    parent = resolve_path(user, relative_parent)
    if not parent.is_dir():
        raise VZoneAPIException(detail="Dossier parent invalide.", code="not_directory", status_code=400)
    target = parent / name
    if target.exists():
        raise VZoneAPIException(detail="Ce fichier existe déjà.", code="exists", status_code=400)
    try:
        target.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise _fs_write_error(exc) from exc
    return entry_from_path(user, target)


def read_file(user: User, relative: str) -> dict:
    path = resolve_path(user, relative)
    if not path.is_file():
        raise VZoneAPIException(detail="Fichier introuvable.", code="not_found", status_code=404)
    if path.stat().st_size > MAX_EDITOR_BYTES:
        raise VZoneAPIException(
            detail="Fichier trop volumineux pour l'éditeur.",
            code="file_too_large",
            status_code=400,
            extra={"max_bytes": MAX_EDITOR_BYTES},
        )
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
        encoding = "utf-8"
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
        encoding = "latin-1"
    return {
        "path": relative_to_home(user, path),
        "content": text,
        "encoding": encoding,
        "size": path.stat().st_size,
        "is_text": _is_text_file(path),
    }


def write_file(user: User, relative: str, content: str) -> FileEntry:
    path = resolve_path(user, relative)
    if path.exists() and path.is_dir():
        raise VZoneAPIException(detail="Impossible d'écrire dans un dossier.", code="is_directory", status_code=400)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode("utf-8")
    if len(data) > MAX_EDITOR_BYTES:
        raise VZoneAPIException(detail="Contenu trop volumineux.", code="file_too_large", status_code=400)
    path.write_bytes(data)
    return entry_from_path(user, path)


def delete_paths(user: User, relatives: Iterable[str]) -> int:
    count = 0
    for rel in relatives:
        path = resolve_path(user, rel)
        if path == user_home(user):
            raise VZoneAPIException(
                detail="Impossible de supprimer la racine home.",
                code="forbidden",
                status_code=400,
            )
        if not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        count += 1
    return count


def rename_path(user: User, relative: str, new_name: str) -> FileEntry:
    if not re.match(r"^[^\\/:*?\"<>|]+$", new_name) or new_name in {".", ".."}:
        raise VZoneAPIException(detail="Nouveau nom invalide.", code="invalid_name", status_code=400)
    path = resolve_path(user, relative)
    target = path.parent / new_name
    if target.exists():
        raise VZoneAPIException(detail="La cible existe déjà.", code="exists", status_code=400)
    path.rename(target)
    return entry_from_path(user, target)


def copy_paths(user: User, sources: list[str], destination_dir: str) -> list[FileEntry]:
    dest = resolve_path(user, destination_dir)
    if not dest.is_dir():
        raise VZoneAPIException(detail="Destination invalide.", code="not_directory", status_code=400)
    results: list[FileEntry] = []
    for rel in sources:
        src = resolve_path(user, rel)
        target = dest / src.name
        if src.is_dir():
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(src, target)
        else:
            shutil.copy2(src, target)
        results.append(entry_from_path(user, target))
    return results


def move_paths(user: User, sources: list[str], destination_dir: str) -> list[FileEntry]:
    dest = resolve_path(user, destination_dir)
    if not dest.is_dir():
        raise VZoneAPIException(detail="Destination invalide.", code="not_directory", status_code=400)
    results: list[FileEntry] = []
    for rel in sources:
        src = resolve_path(user, rel)
        target = dest / src.name
        shutil.move(str(src), str(target))
        results.append(entry_from_path(user, target))
    return results


def chmod_path(user: User, relative: str, mode: str) -> FileEntry:
    if not re.match(r"^[0-7]{3,4}$", mode):
        raise VZoneAPIException(detail="Mode octal invalide (ex: 644, 755).", code="invalid_mode", status_code=400)
    path = resolve_path(user, relative)
    os.chmod(path, int(mode, 8))
    return entry_from_path(user, path)


def compress(user: User, sources: list[str], archive_relative: str, fmt: str = "zip") -> FileEntry:
    archive = resolve_path(user, archive_relative)
    if archive.exists():
        raise VZoneAPIException(detail="L'archive existe déjà.", code="exists", status_code=400)
    archive.parent.mkdir(parents=True, exist_ok=True)
    resolved_sources = [resolve_path(user, s) for s in sources]
    if fmt == "zip":
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for src in resolved_sources:
                if src.is_dir():
                    for file in src.rglob("*"):
                        if file.is_file():
                            zf.write(file, arcname=str(file.relative_to(src.parent)))
                else:
                    zf.write(src, arcname=src.name)
    elif fmt in {"tar.gz", "tgz"}:
        with tarfile.open(archive, "w:gz") as tf:
            for src in resolved_sources:
                tf.add(src, arcname=src.name)
    else:
        raise VZoneAPIException(detail="Format non supporté (zip, tar.gz).", code="invalid_format", status_code=400)
    return entry_from_path(user, archive)


def decompress(user: User, archive_relative: str, destination_dir: str | None = None) -> dict:
    archive = resolve_path(user, archive_relative)
    if not archive.is_file():
        raise VZoneAPIException(detail="Archive introuvable.", code="not_found", status_code=404)
    dest = resolve_path(user, destination_dir) if destination_dir is not None else archive.parent
    if not dest.is_dir():
        raise VZoneAPIException(detail="Destination invalide.", code="not_directory", status_code=400)

    name = archive.name.lower()
    if name.endswith(".zip"):
        with zipfile.ZipFile(archive, "r") as zf:
            _safe_extract_zip(zf, dest)
    elif name.endswith(".tar.gz") or name.endswith(".tgz") or name.endswith(".tar"):
        mode = "r:gz" if name.endswith((".tar.gz", ".tgz")) else "r:"
        with tarfile.open(archive, mode) as tf:
            _safe_extract_tar(tf, dest)
    else:
        raise VZoneAPIException(
            detail="Format d'archive non supporté.",
            code="invalid_format",
            status_code=400,
        )
    return {"destination": relative_to_home(user, dest)}


def _safe_extract_zip(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    for info in zf.infolist():
        target = (dest / info.filename).resolve()
        if not str(target).startswith(str(dest)):
            raise VZoneAPIException(detail="Archive malveillante (zip slip).", code="unsafe_archive", status_code=400)
    zf.extractall(dest)


def _safe_extract_tar(tf: tarfile.TarFile, dest: Path) -> None:
    dest = dest.resolve()
    for member in tf.getmembers():
        target = (dest / member.name).resolve()
        if not str(target).startswith(str(dest)):
            raise VZoneAPIException(detail="Archive malveillante (tar slip).", code="unsafe_archive", status_code=400)
    tf.extractall(dest)


def search_files(user: User, query: str, relative: str | None = None, limit: int = 200) -> list[dict]:
    if not query or len(query) < 1:
        raise VZoneAPIException(detail="Requête vide.", code="invalid_query", status_code=400)
    root = resolve_path(user, relative)
    if not root.is_dir():
        raise VZoneAPIException(detail="Dossier de recherche invalide.", code="not_directory", status_code=400)
    q = query.lower()
    results: list[dict] = []
    for path in root.rglob("*"):
        if q in path.name.lower():
            results.append(asdict(entry_from_path(user, path)))
            if len(results) >= limit:
                break
    return results


def save_upload(user: User, relative_dir: str, uploaded_name: str, stream: BinaryIO, size: int | None) -> FileEntry:
    if size is not None and size > MAX_UPLOAD_BYTES:
        raise VZoneAPIException(detail="Fichier trop volumineux.", code="file_too_large", status_code=400)
    safe_name = Path(uploaded_name).name
    if not safe_name or safe_name in {".", ".."}:
        raise VZoneAPIException(detail="Nom de fichier invalide.", code="invalid_name", status_code=400)
    dest_dir = resolve_path(user, relative_dir)
    if not dest_dir.is_dir():
        raise VZoneAPIException(detail="Dossier destination invalide.", code="not_directory", status_code=400)
    target = dest_dir / safe_name
    written = 0
    with target.open("wb") as out:
        while True:
            chunk = stream.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if written > MAX_UPLOAD_BYTES:
                out.close()
                target.unlink(missing_ok=True)
                raise VZoneAPIException(detail="Fichier trop volumineux.", code="file_too_large", status_code=400)
            out.write(chunk)
    return entry_from_path(user, target)
