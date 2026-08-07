"""Providers de stockage → sections Rclone."""
from __future__ import annotations

from typing import Any


def provider_path(provider: str, config: dict[str, Any]) -> str:
    """Chemin / bucket relatif dans le remote rclone."""
    if provider == "local":
        return str(config.get("path") or "")
    if provider in {"s3", "b2", "r2"}:
        bucket = str(config.get("bucket") or config.get("path") or "vzone-backups").strip("/")
        prefix = str(config.get("prefix") or "").strip("/")
        return f"{bucket}/{prefix}" if prefix else bucket
    if provider == "sftp":
        return str(config.get("path") or "vzone-backups").lstrip("/")
    if provider == "gdrive":
        return str(config.get("path") or "vzone-backups").strip("/")
    return str(config.get("path") or "vzone-backups")


def build_rclone_section(
    provider: str,
    remote_name: str,
    config: dict[str, Any],
    credentials: dict[str, Any],
) -> str:
    """Génère un bloc [remote] pour rclone.conf."""
    lines = [f"[{remote_name}]"]
    if provider == "local":
        lines.append("type = local")
        # nounc pour chemins locaux
        lines.append("nounc = true")
    elif provider == "sftp":
        lines.append("type = sftp")
        lines.append(f"host = {config.get('host', '')}")
        lines.append(f"user = {config.get('user') or credentials.get('user', '')}")
        port = config.get("port") or 22
        lines.append(f"port = {port}")
        if credentials.get("password"):
            # rclone obscure — on passe en clair via env file privé ; rclone accepte password
            lines.append(f"pass = {credentials['password']}")
        if credentials.get("key_file"):
            lines.append(f"key_file = {credentials['key_file']}")
        if config.get("path"):
            lines.append(f"path = {config['path']}")
    elif provider == "s3":
        lines.append("type = s3")
        lines.append(f"provider = {config.get('s3_provider') or 'Other'}")
        lines.append(f"access_key_id = {credentials.get('access_key_id', '')}")
        lines.append(f"secret_access_key = {credentials.get('secret_access_key', '')}")
        if config.get("endpoint"):
            lines.append(f"endpoint = {config['endpoint']}")
        if config.get("region"):
            lines.append(f"region = {config['region']}")
        lines.append(f"acl = {config.get('acl') or 'private'}")
    elif provider == "r2":
        # Cloudflare R2 = S3 compatible
        lines.append("type = s3")
        lines.append("provider = Cloudflare")
        lines.append(f"access_key_id = {credentials.get('access_key_id', '')}")
        lines.append(f"secret_access_key = {credentials.get('secret_access_key', '')}")
        account = config.get("account_id") or credentials.get("account_id") or ""
        endpoint = config.get("endpoint") or (
            f"https://{account}.r2.cloudflarestorage.com" if account else ""
        )
        if endpoint:
            lines.append(f"endpoint = {endpoint}")
        lines.append("acl = private")
    elif provider == "b2":
        lines.append("type = b2")
        lines.append(f"account = {credentials.get('account') or credentials.get('key_id', '')}")
        lines.append(f"key = {credentials.get('key') or credentials.get('application_key', '')}")
    elif provider == "gdrive":
        lines.append("type = drive")
        if credentials.get("client_id"):
            lines.append(f"client_id = {credentials['client_id']}")
        if credentials.get("client_secret"):
            lines.append(f"client_secret = {credentials['client_secret']}")
        if credentials.get("token"):
            lines.append(f"token = {credentials['token']}")
        if config.get("root_folder_id"):
            lines.append(f"root_folder_id = {config['root_folder_id']}")
        lines.append("scope = drive")
    else:
        raise ValueError(f"Provider inconnu: {provider}")
    return "\n".join(lines)
