# Git Deploy — V-zone Panel

## Fonctions

- Clone de dépôts Git dans le home (`repositories/<name>`)
- Pull / deploy manuel
- Clés SSH deploy (Ed25519) générées automatiquement
- Webhook auto-deploy (`/api/v1/git/webhook/<token>/`)
- Script post-pull optionnel (`deploy.sh`)
- Journaux d'événements (clone, pull, deploy, webhook, keygen)
- Respect du flag package `allow_git`
- Quota `VZONE_GIT_MAX_REPOS` (défaut 20)

## Modes

| Mode | Comportement |
|------|----------------|
| `auto` / `live` | Exécute `git clone/pull` réel |
| `mock` | Scaffold local (tests) |

## API

| Méthode | Chemin |
|---------|--------|
| GET | `/api/v1/git/overview/` |
| GET/POST | `/api/v1/git/repos/` |
| GET/PATCH/DELETE | `/api/v1/git/repos/{id}/` |
| POST | `/api/v1/git/repos/{id}/clone/` |
| POST | `/api/v1/git/repos/{id}/pull/` |
| POST | `/api/v1/git/repos/{id}/deploy/` |
| POST | `/api/v1/git/repos/{id}/keygen/` |
| POST | `/api/v1/git/repos/{id}/rotate-webhook/` |
| GET | `/api/v1/git/logs/` |
| POST | `/api/v1/git/webhook/{token}/` |

## Configuration

- `VZONE_GIT_PROVISION_MODE`
- `VZONE_GIT_CONFIG_DIR`
- `VZONE_GIT_BIN`
- `VZONE_GIT_MAX_REPOS`

## UI

- WHM : `/whm/git`
- Client : `/panel/git`
