# Applications Python — V-zone Panel (style cPanel)

## Fonctions

- **Application root** obligatoire (chemin du projet relatif au home) — comme cPanel
- `passenger_wsgi.py` créé **dans le même dossier** que le projet Django (`manage.py`)
- Venv sous `~/virtualenv/<app>/<python_version>/` (hors du projet)
- Modes **WSGI** (gunicorn / passenger_wsgi) et **ASGI** (uvicorn)
- Frameworks : generic, Django, Flask, FastAPI
- Commande SSH : `source …/virtualenv/…/activate && cd <application_root>`
- Start / stop / restart, pip install, logs, quotas

## Permissions (jail / SQLite)

Les apps démarrent sous l’UID client (`vzone-runas`). Le panel exécute
`vzone-fix-app-perms` (sudo) à la **création**, après **pip**, et avant chaque
**start** pour que `db.sqlite3`, `logs/`, `media/` appartiennent au compte jail.

Sans ce helper : `sudo bash scripts/ensure-mkhome-sudoers.sh`

Réparation manuelle :
```bash
sudo /usr/local/sbin/vzone-fix-app-perms <user> /home/<user>/<app_root>
```

## Déploiement Django (identique cPanel)

1. CREATE APPLICATION → renseigner **Application root** (ex. `mydjango`)
2. Le panel crée `~/mydjango/passenger_wsgi.py` + `~/virtualenv/<name>/<ver>/`
3. SSH : coller `enter_command`, puis `django-admin startproject config .` **dans ce dossier**
4. `manage.py` et `passenger_wsgi.py` restent côte à côte
5. **Start** dans le panel

## API

Champs utiles : `relative_root`, `absolute_root`, `passenger_wsgi`, `venv_path`, `enter_command`, `deploy_command`.

| Méthode | Chemin |
|---------|--------|
| GET | `/api/v1/python/overview/` |
| GET/POST | `/api/v1/python/apps/` |
| GET/PATCH/DELETE | `/api/v1/python/apps/{id}/` |
| POST | `/api/v1/python/apps/{id}/start/` |
| POST | `/api/v1/python/apps/{id}/stop/` |
| POST | `/api/v1/python/apps/{id}/restart/` |
| POST | `/api/v1/python/apps/{id}/install/` |
| GET | `/api/v1/python/apps/{id}/logs/` |

## UI

- WHM : `/whm/python`
- Client : `/panel/python`
