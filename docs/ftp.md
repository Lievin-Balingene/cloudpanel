# FTP — V-zone Panel

## Fonctions

- Création / modification / suppression de comptes FTP
- Préfixe login `owner_login` (style panneau d'hébergement)
- Jail dans le home du compte (`relative_directory`)
- Suspension / réactivation
- Quotas package (`ftp_accounts`)
- Journaux : login, échecs, upload/download (ingestion daemon)
- **Pure-FTPd** + ExtAuth V-zone (`vzone-ftp-auth` / `vzone-ftp-authd`)
- Auth API pour Pure-FTPd / ProFTPD / script PAM
- Export fichier virtual users (`VZONE_FTP_VIRTUAL_USERS_FILE`)

## Installation serveur

Si le monitoring / la page FTP affiche **« Aucun serveur FTP »** :

```bash
sudo bash /opt/vzone-src/scripts/install-ftp.sh
```

Ou depuis le panneau : **WHM → Réparations → Installer / réparer FTP**.

`update.sh` et le bootstrap d'install relancent aussi `install-ftp.sh` (idempotent).

Ports ouverts : **21/tcp** + passif **30000-30100/tcp**.

## Connexion client

- Hôte : IP ou hostname du serveur
- Login : `compte_identifiant` (ex. `alice_web` si compte panneau `alice` + FTP `web`)
- Mot de passe : celui défini à la création
- Mode passif recommandé

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
