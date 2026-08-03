# FTP — V-zone Panel

## Fonctions

- Création / modification / suppression de comptes FTP
- Préfixe login `owner_login` (style panneau d'hébergement)
- Jail dans le home du compte (`relative_directory`)
- Suspension / réactivation
- Quotas package (`ftp_accounts`)
- Journaux : login, échecs, upload/download (ingestion daemon)
- Auth API pour Pure-FTPd / ProFTPD / script PAM
- Export fichier virtual users (`VZONE_FTP_VIRTUAL_USERS_FILE`)

## API

| Méthode | Chemin |
|---------|--------|
| GET/POST | `/api/v1/ftp/accounts/` |
| GET/PATCH/DELETE | `/api/v1/ftp/accounts/{id}/` |
| POST | `/api/v1/ftp/accounts/{id}/suspend/` |
| GET | `/api/v1/ftp/logs/` |
| GET | `/api/v1/ftp/stats/` |
| POST | `/api/v1/ftp/auth/` |
| POST | `/api/v1/ftp/logs/ingest/` |

Secret optionnel : `VZONE_FTP_AUTH_SECRET` (header `X-Vzone-Ftp-Secret`).

## UI

- WHM : `/whm/ftp`
- Client : `/panel/ftp`
