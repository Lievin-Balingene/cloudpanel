"""Tests module applications Python."""
from __future__ import annotations

from pathlib import Path

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.factories import UserFactory
from apps.python_apps.models import PythonApp
from apps.python_apps.services import (
    _clip_end,
    _filter_log_noise,
    _format_start_failure,
    _is_runas_infra_error,
    _scaffold,
    _summarize_traceback,
    create_python_app,
    start_python_app,
    stop_python_app,
)


@pytest.fixture
def api() -> APIClient:
    return APIClient()


@pytest.fixture
def py_root(tmp_path, settings):
    settings.VZONE_HOME_ROOT = tmp_path / "homes"
    settings.VZONE_HOME_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_DATA_ROOT = tmp_path / "data"
    settings.VZONE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
    settings.VZONE_PYTHON_CONFIG_DIR = str(tmp_path / "python_apps")
    settings.VZONE_PYTHON_PROVISION_MODE = "mock"
    settings.VZONE_PYTHON_PORT_BASE = 8100
    return settings.VZONE_HOME_ROOT


@pytest.mark.integration
@pytest.mark.django_db
def test_create_start_stop_python_app(api: APIClient, py_root):
    user = UserFactory(username="pyuser", password="TestPassword123!")
    api.force_authenticate(user=user)

    # Sans application root → erreur (comme cPanel)
    missing = api.post(
        reverse("python-app-list"),
        {"name": "webapp", "mode": "wsgi", "framework": "django"},
        format="json",
    )
    assert missing.status_code == 400

    created = api.post(
        reverse("python-app-list"),
        {
            "name": "webapp",
            "mode": "wsgi",
            "framework": "django",
            "relative_root": "mydjango",
        },
        format="json",
    )
    assert created.status_code == 201
    data = created.json()["data"]
    assert data["name"] == "webapp"
    assert data["relative_root"] == "mydjango"
    assert data["status"] == "stopped"
    assert data["port"] >= 8100
    assert "source " in data["enter_command"]
    assert "virtualenv" in data["enter_command"].replace("\\", "/")
    assert "activate" in data["enter_command"]
    assert "cd " in data["enter_command"]
    assert "django-admin startproject config" in data["deploy_command"]
    assert "mydjango" in data["absolute_root"].replace("\\", "/")
    assert data["django_project"] == "config"
    assert data["passenger_wsgi"].replace("\\", "/").endswith("mydjango/passenger_wsgi.py")
    pk = data["id"]

    app_path = Path(py_root) / "pyuser" / "mydjango"
    venv_path = Path(py_root) / "pyuser" / "virtualenv" / "webapp" / "3.12"
    assert (app_path / "passenger_wsgi.py").exists()
    assert (venv_path / "pyvenv.cfg").exists()
    assert not (app_path / ".venv").exists()
    assert (app_path / "ENTER.sh").exists()
    assert (app_path / "DEPLOY.sh").exists()
    assert "Django" in (app_path / "requirements.txt").read_text(encoding="utf-8")
    assert "config.settings" in (app_path / "passenger_wsgi.py").read_text(encoding="utf-8")

    start = api.post(reverse("python-app-start", kwargs={"pk": pk}))
    assert start.status_code == 200
    assert start.json()["data"]["status"] == "running"

    install = api.post(reverse("python-app-install", kwargs={"pk": pk}))
    assert install.status_code == 200

    logs = api.get(reverse("python-app-logs", kwargs={"pk": pk}))
    assert logs.status_code == 200
    assert "pip.log" in logs.json()["data"]

    stop = api.post(reverse("python-app-stop", kwargs={"pk": pk}))
    assert stop.status_code == 200
    assert stop.json()["data"]["status"] == "stopped"

    overview = api.get(reverse("python-overview"))
    assert overview.status_code == 200
    assert overview.json()["data"]["apps"] == 1


@pytest.mark.integration
@pytest.mark.django_db
def test_asgi_and_delete(api: APIClient, py_root):
    user = UserFactory(username="py2")
    api.force_authenticate(user=user)
    created = api.post(
        reverse("python-app-list"),
        {"name": "api", "mode": "asgi", "framework": "fastapi", "relative_root": "api"},
        format="json",
    )
    assert created.status_code == 201
    assert created.json()["data"]["entrypoint"] == "asgi:application"
    pk = created.json()["data"]["id"]
    assert (Path(py_root) / "py2" / "api" / "asgi.py").exists()
    deleted = api.delete(reverse("python-app-detail", kwargs={"pk": pk}) + "?remove_files=true")
    assert deleted.status_code == 204
    assert PythonApp.objects.count() == 0


@pytest.mark.integration
@pytest.mark.django_db
def test_python_quota(api: APIClient, py_root):
    user = UserFactory(username="py3")
    user.quota.python_apps = 1
    user.quota.save()
    create_python_app(owner=user, name="one", relative_root="one")
    api.force_authenticate(user=user)
    second = api.post(
        reverse("python-app-list"),
        {"name": "two", "relative_root": "two"},
        format="json",
    )
    assert second.status_code == 403


@pytest.mark.unit
@pytest.mark.django_db
def test_start_stop_helpers(py_root):
    user = UserFactory(username="py4")
    app = create_python_app(owner=user, name="svc", mode="wsgi", relative_root="svc")
    app = start_python_app(app)
    assert app.status == PythonApp.Status.RUNNING
    assert app.pid
    app = stop_python_app(app)
    assert app.status == PythonApp.Status.STOPPED
    assert app.pid is None


@pytest.mark.unit
@pytest.mark.django_db
def test_django_passenger_next_to_existing_project(py_root):
    user = UserFactory(username="py5")
    home = Path(py_root) / "py5"
    project = home / "blog"
    project.mkdir(parents=True)
    (project / "manage.py").write_text("# manage", encoding="utf-8")
    pkg = project / "mysite"
    pkg.mkdir()
    (pkg / "settings.py").write_text("SECRET_KEY='x'\n", encoding="utf-8")

    app = create_python_app(
        owner=user,
        name="blog",
        framework="django",
        relative_root="blog",
    )
    passenger = project / "passenger_wsgi.py"
    assert passenger.exists()
    text = passenger.read_text(encoding="utf-8")
    assert "mysite.settings" in text
    assert "virtualenv" in app.venv_path.replace("\\", "/")

    # Comme cPanel : Start / scaffold ne doivent jamais écraser passenger_wsgi.py
    marker = "# USER CUSTOM PASSENGER\n"
    passenger.write_text(marker + text, encoding="utf-8")
    _scaffold(project, mode="wsgi", framework="django")
    assert passenger.read_text(encoding="utf-8").startswith(marker)


@pytest.mark.unit
def test_filter_log_noise_drops_wordpress_probes():
    raw = "\n".join(
        [
            "Not Found: //xmlrpc.php",
            "Not Found: //blog/wp-includes/wlwmanifest.xml",
            "Not Found: //web/wp-includes/wlwmanifest.xml",
            "Not Found: //wordpress/wp-includes/wlwmanifest.xml",
            "Not Found: //website/wp-includes/wlwmanifest.xml",
            "Not Found: //wp/wp-includes/wlwmanifest.xml",
            "ModuleNotFoundError: No module named 'gunicorn'",
        ]
    )
    clean = _filter_log_noise(raw)
    assert "xmlrpc" not in clean.lower()
    assert "wlwmanifest" not in clean.lower()
    assert "gunicorn" in clean


@pytest.mark.unit
def test_format_start_failure_code_127_without_scanner_noise():
    noise = "\n".join(
        [
            "Not Found: //xmlrpc.php",
            "Not Found: //blog/wp-includes/wlwmanifest.xml",
        ]
    )
    msg = _format_start_failure(returncode=127, stderr_new=noise)
    assert "127" in msg
    assert "gunicorn" in msg.lower() or "uvicorn" in msg.lower() or "pip install" in msg.lower()
    assert "xmlrpc" not in msg.lower()
    assert "wlwmanifest" not in msg.lower()


@pytest.mark.unit
def test_format_start_failure_env_double_dash():
    msg = _format_start_failure(
        returncode=127,
        stderr_new="env: '--': No such file or directory",
    )
    assert "pip install gunicorn" not in msg.lower()
    assert "env" in msg.lower()
    assert _is_runas_infra_error("env: '--': No such file or directory")


@pytest.mark.unit
def test_is_runas_infra_error_detects_missing_runuser():
    assert _is_runas_infra_error(
        "/usr/local/sbin/vzone-runas: line 67: exec: runuser: not found"
    )
    assert not _is_runas_infra_error("ModuleNotFoundError: No module named 'gunicorn'")


@pytest.mark.unit
def test_gunicorn_logs_to_stdio_not_path():
    from apps.python_apps.models import PythonApp
    from apps.python_apps.services import _build_start_command

    app = PythonApp(
        name="demo",
        mode=PythonApp.Mode.WSGI,
        entrypoint="passenger_wsgi.py",
        port=8100,
    )
    cmd = _build_start_command(app, Path("/tmp/app"), Path("/tmp/py"))
    assert "--error-logfile" in cmd
    assert cmd[cmd.index("--error-logfile") + 1] == "-"
    assert cmd[cmd.index("--access-logfile") + 1] == "-"
    tb = "\n".join(
        [
            'File "/home/lievin/virtualenv/vzone/3.12/lib/python3.10/site-packages/gunicorn/app/base.py", line 235, in run',
            "    super().run()",
            'File "/home/lievin/virtualenv/vzone/3.12/lib/python3.10/site-packages/gunicorn/app/base.py", line 71, in run',
            "    Arbiter(self).run()",
            'File "/home/x/app/passenger_wsgi.py", line 12, in <module>',
            "    from django.core.wsgi import get_wsgi_application",
            "ModuleNotFoundError: No module named 'django'",
            "Reason: Worker failed to boot.",
        ]
    )
    summary = _summarize_traceback(tb)
    assert "ModuleNotFoundError" in summary
    assert "django" in summary
    msg = _format_start_failure(returncode=1, stderr_new=tb)
    assert "ModuleNotFoundError" in msg
    clipped = _clip_end("Code 1 : hint\n" + ("x" * 200) + "\nModuleNotFoundError: No module named 'django'", 80)
    assert "ModuleNotFoundError" in clipped
    assert "django" in clipped
    assert clipped.startswith("…")
