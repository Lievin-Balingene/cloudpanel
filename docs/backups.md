# Backups — V-zone Panel (Restic + Rclone)

## Architecture

```
API / Celery worker
        │
        ▼
  services.py  ──► engine/restic.py  ──► restic (chiffré)
                 ──► engine/rclone.py  ──► remotes (S3/B2/R2/SFTP/Drive/local)
        │
        ▼
  Django DB (jobs, snapshots metadata, schedules, destinations)
```

- **Restic** : moteur de backup incrémental chiffré (AES-256).
- **Rclone** : couche d’abstraction stockage (URI `rclone:remote:path`).
- **Celery** : chaque job tourne en async (`backups.execute_backup_job`).
- Mode **mock** : pas de binaires (tests).

## Fonctions

- Full / incremental (Restic déduplique naturellement)
- Manuel + planifié (hourly / daily / weekly / monthly)
- Destinations multiples : local, SFTP, S3, B2, R2, Google Drive
- Historique, logs, progress %, durée, usage stockage
- Restore one-click
- Rétention : `keep_hourly` / `keep_daily` / `keep_weekly` / `keep_monthly`

## API

| Méthode | Chemin |
|---------|--------|
| GET | `/api/v1/backups/overview/` |
| GET/POST | `/api/v1/backups/destinations/` |
| GET/DELETE | `/api/v1/backups/destinations/{id}/` |
| GET/POST | `/api/v1/backups/archives/` |
| GET/DELETE | `/api/v1/backups/archives/{id}/` |
| POST | `/api/v1/backups/archives/{id}/restore/` |
| GET | `/api/v1/backups/archives/{id}/download/` |
| GET/POST | `/api/v1/backups/schedules/` |
| PATCH/DELETE | `/api/v1/backups/schedules/{id}/` |
| POST | `/api/v1/backups/retention/` |
| GET | `/api/v1/backups/events/` |

## Celery

| Task | Rôle |
|------|------|
| `backups.execute_backup_job` | Exécute un archive_id |
| `backups.execute_restore_job` | Restore async |
| `backups.run_due_schedules` | Tick planning (à planifier hourly via django_celery_beat) |
| `backups.apply_retention` | `restic forget --prune` |

Créer une PeriodicTask beat :

```text
Name: backups-due-schedules
Task: backups.run_due_schedules
Interval: every 5 minutes
```

## Configuration

```env
VZONE_BACKUP_PROVISION_MODE=auto
VZONE_BACKUP_DIR=/var/lib/vzone/backups
VZONE_BACKUP_MAX=10
VZONE_RESTIC_BIN=restic
VZONE_RCLONE_BIN=rclone
VZONE_BACKUP_TIMEOUT=7200
```

Install OS :

```bash
apt-get install -y restic rclone
# ou: restic self-update && curl https://rclone.org/install.sh | bash
```

## UI

- WHM : `/whm/backups`
- Client : `/panel/backups`

## Notes

Les scripts `scripts/backup.sh` / `restore.sh` restent pour la **plateforme** (Postgres + panel).
Ce module gère les sauvegardes **par compte** chiffrées Restic.
