"""Erreur métier renvoyée par une fonction WHM / UAPI."""
from __future__ import annotations


class ApiCallError(Exception):
    def __init__(self, reason: str, *, http_status: int = 200) -> None:
        self.reason = reason
        self.http_status = http_status
        super().__init__(reason)
