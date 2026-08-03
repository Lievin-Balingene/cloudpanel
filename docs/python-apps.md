# Applications Python — V-zone Panel

## Fonctions

- Création d'apps Python dans le home utilisateur (`apps/<name>`)
- Modes **WSGI** (gunicorn / passenger_wsgi) et **ASGI** (uvicorn)
- Frameworks : generic, Django, Flask, FastAPI
- Venv automatique + `requirements.txt`
- Start / stop / restart
- Installation pip des dépendances
- Consultation des logs
- Quotas package (`python_apps`)
- Config JSON exportée (`VZONE_PYTHON_CONFIG_DIR`)

## Modes de provisionnement

| Mode | Comportement |
|------|----------------|
| `auto` | Opérations réelles si binaire Python dispo |
| `live` | Force exécution réelle |
| `mock` | Scaffold + venv factice (tests) |

## API

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

## Configuration

- `VZONE_PYTHON_PROVISION_MODE`
- `VZONE_PYTHON_CONFIG_DIR`
- `VZONE_PYTHON_PORT_BASE` (défaut 8100)
- `VZONE_PYTHON_BIN` (optionnel)

## UI

- WHM : `/whm/python`
- Client : `/panel/python`
