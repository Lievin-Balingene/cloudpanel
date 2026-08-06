from __future__ import annotations

import pytest

from apps.core.exceptions import VZoneAPIException
from apps.kubernetes.services import _normalize_manifest


def test_normalize_rejects_scalar():
    with pytest.raises(VZoneAPIException) as exc:
        _normalize_manifest("vzone")
    assert exc.value.code == "manifest_invalid"


def test_normalize_rejects_empty():
    with pytest.raises(VZoneAPIException) as exc:
        _normalize_manifest("   \n# comment only\n---\n")
    assert exc.value.code in {"manifest_empty", "manifest_required", "manifest_invalid"}


def test_normalize_accepts_namespace():
    text = _normalize_manifest(
        """
apiVersion: v1
kind: Namespace
metadata:
  name: demo
"""
    )
    assert "kind: Namespace" in text
    assert text.endswith("\n")


def test_normalize_rejects_missing_kind():
    with pytest.raises(VZoneAPIException) as exc:
        _normalize_manifest(
            """
apiVersion: v1
metadata:
  name: demo
"""
        )
    assert exc.value.code == "manifest_invalid"
