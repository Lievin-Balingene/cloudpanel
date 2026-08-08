"""Extraction d'archives avec protection zip/tar slip."""
from __future__ import annotations

import tarfile
import zipfile
from pathlib import Path

from apps.core.exceptions import VZoneAPIException


def safe_extract_zip(zf: zipfile.ZipFile, dest: Path) -> None:
    dest = dest.resolve()
    for info in zf.infolist():
        target = (dest / info.filename).resolve()
        try:
            target.relative_to(dest)
        except ValueError as exc:
            raise VZoneAPIException(
                detail="Archive malveillante (zip slip).",
                code="unsafe_archive",
                status_code=400,
            ) from exc
    zf.extractall(dest)


def safe_extract_tar(tf: tarfile.TarFile, dest: Path) -> None:
    dest = dest.resolve()
    for member in tf.getmembers():
        target = (dest / member.name).resolve()
        try:
            target.relative_to(dest)
        except ValueError as exc:
            raise VZoneAPIException(
                detail="Archive malveillante (tar slip).",
                code="unsafe_archive",
                status_code=400,
            ) from exc
        # Refuse les liens symboliques sortants
        if member.issym() or member.islnk():
            link = member.linkname or ""
            if link.startswith("/") or ".." in Path(link).parts:
                raise VZoneAPIException(
                    detail="Archive malveillante (lien).",
                    code="unsafe_archive",
                    status_code=400,
                )
    # filter='data' (Py3.12+) si dispo
    try:
        tf.extractall(dest, filter=tarfile.data_filter)  # type: ignore[attr-defined]
    except (AttributeError, TypeError):
        tf.extractall(dest)
