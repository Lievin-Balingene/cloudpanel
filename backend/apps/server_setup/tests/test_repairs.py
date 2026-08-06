from __future__ import annotations

import pytest
from django.test import override_settings

from apps.core.exceptions import VZoneAPIException
from apps.server_setup.repairs import REPAIR_CATALOG, enqueue_repair, list_catalog


def test_repair_catalog_scripts_exist_in_repo():
    from pathlib import Path

    root = Path(__file__).resolve().parents[4]
    for meta in REPAIR_CATALOG.values():
        path = root / "scripts" / meta["script"]
        assert path.is_file(), f"missing {path}"


def test_list_catalog_marks_availability(tmp_path):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "repair-smtp.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    with override_settings(VZONE_SRC_DIR=str(tmp_path)):
        items = list_catalog(src=tmp_path)
    by_id = {i["id"]: i for i in items}
    assert by_id["smtp"]["available"] is True
    assert by_id["dkim"]["available"] is False


def test_enqueue_unknown_script():
    with pytest.raises(VZoneAPIException) as exc:
        enqueue_repair(script_id="not-a-real-script")
    assert exc.value.detail  # noqa: B017 — presence check
