# Backups — V-zone Panel

## Fonctions

- Création de sauvegardes (complète, home, bases, email, personnalisée)
- Restauration
- Métadonnées de téléchargement (chemin, taille, checksum)
- Planning quotidien / hebdomadaire / mensuel
- Journaux d'événements
- Flag package `allow_backup`
- Quota `VZONE_BACKUP_MAX` (rétention)

## Modes

| Mode | Comportement |
|------|----------------|
| `auto` / `live` | Archive tar.gz (home + placeholders DB/email) |
| `mock` | Fichier JSON fictif (tests) |

## API

| Méthode | Chemin |
|---------|--------|
| GET | `/api/v1/backups/overview/` |
| GET/POST | `/api/v1/backups/archives/` |
| GET/DELETE | `/api/v1/backups/archives/{id}/` |
| POST | `/api/v1/backups/archives/{id}/restore/` |
| GET | `/api/v1/backups/archives/{id}/download/` |
| GET/POST | `/api/v1/backups/schedules/` |
| PATCH/DELETE | `/api/v1/backups/schedules/{id}/` |
| GET | `/api/v1/backups/events/` |

## Configuration

- `VZONE_BACKUP_PROVISION_MODE`
- `VZONE_BACKUP_DIR`
- `VZONE_BACKUP_MAX`

## UI

- WHM : `/whm/backups`
- Client : `/panel/backups`

## Notes

Les scripts système `scripts/backup.sh` / `restore.sh` restent pour la plateforme.
Ce module gère les sauvegardes **par compte**.
