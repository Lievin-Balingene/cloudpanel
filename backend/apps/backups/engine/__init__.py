"""Exécution sécurisée de sous-processus (Restic / Rclone)."""
from __future__ import annotations

import logging
import os
import subprocess
from dataclasses import dataclass, field
from typing import Mapping, Sequence

logger = logging.getLogger(__name__)


@dataclass
class CmdResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""
    cmd: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.returncode == 0

    @property
    def output(self) -> str:
        return ((self.stdout or "") + "\n" + (self.stderr or "")).strip()


def run_cmd(
    cmd: Sequence[str],
    *,
    env: Mapping[str, str] | None = None,
    cwd: str | None = None,
    timeout: int = 3600,
    input_text: str | None = None,
) -> CmdResult:
    """Lance une commande sans shell=True ; capture stdout/stderr."""
    merged = os.environ.copy()
    if env:
        merged.update({k: str(v) for k, v in env.items()})
    # Empêche fuites d'env sensibles dans les logs enfants
    merged.setdefault("LANG", "C.UTF-8")
    try:
        proc = subprocess.run(
            list(cmd),
            capture_output=True,
            text=True,
            env=merged,
            cwd=cwd,
            timeout=timeout,
            check=False,
            input=input_text,
        )
        return CmdResult(
            returncode=proc.returncode,
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            cmd=list(cmd),
        )
    except FileNotFoundError as exc:
        logger.error("Binaire introuvable: %s", cmd[0] if cmd else "?")
        return CmdResult(returncode=127, stderr=str(exc), cmd=list(cmd))
    except subprocess.TimeoutExpired as exc:
        return CmdResult(
            returncode=124,
            stdout=(exc.stdout or b"").decode("utf-8", errors="replace")
            if isinstance(exc.stdout, bytes)
            else (exc.stdout or ""),
            stderr=f"timeout after {timeout}s",
            cmd=list(cmd),
        )
