# Bases de données — V-zone Panel

## Fonctions

- Création / suppression de bases MySQL/MariaDB et PostgreSQL
- Préfixe login `owner_name` (style panneau d'hébergement)
- Utilisateurs SQL + changement de mot de passe
- Attribution de privilèges ALL / WRITE / READ
- Quotas package (`databases`)
- Inventory + SQL pending (`VZONE_DB_MAPS_DIR`)
- Provisionnement live via `mysql` / `psql` ou mode `mock`
- **phpMyAdmin** intégré (`/phpmyadmin/`) avec SSO style cPanel

## phpMyAdmin (comme cPanel)

Installation :

```bash
sudo bash scripts/install-phpmyadmin.sh
# ou via update.sh
```

- URL : `/phpmyadmin/`
- Connexion manuelle : utilisateur MySQL créé dans le panel
- SSO : bouton **phpMyAdmin** sur chaque user MySQL → ouverture déjà connectée
- Les users créés avant le SSO doivent **réinitialiser leur mot de passe** une fois

## Modes de provisionnement

| Mode | Comportement |
|------|----------------|
| `auto` | Exécute si credentials admin configurés, sinon écrit SQL pending |
| `live` | Exige un backend configuré (`install-phpmyadmin.sh` active live) |
| `mock` | Catalogue + fichiers SQL uniquement (tests / démo) |

## API

| Méthode | Chemin |
|---------|--------|
| GET | `/api/v1/databases/overview/` |
| POST | `/api/v1/databases/phpmyadmin/sso/` `{ "user_id": N }` |
| GET/POST | `/api/v1/databases/` |
| GET/DELETE | `/api/v1/databases/{id}/` |
| GET/POST | `/api/v1/databases/users/` |
| GET/PATCH/DELETE | `/api/v1/databases/users/{id}/` |
| GET/POST | `/api/v1/databases/privileges/` |
| DELETE | `/api/v1/databases/privileges/{id}/` |

## Configuration

- `VZONE_DB_PROVISION_MODE`
- `VZONE_DB_MAPS_DIR`
- `VZONE_MYSQL_HOST` / `PORT` / `ADMIN_USER` / `ADMIN_PASSWORD`
- `VZONE_PG_HOST` / `PORT` / `ADMIN_USER` / `ADMIN_PASSWORD` / `ADMIN_DB`
- `VZONE_PHPMYADMIN_URL`, `VZONE_PHPMYADMIN_SSO_DIR`, `VZONE_PGADMIN_URL`

## UI

- WHM : `/whm/databases`
- Client : `/panel/databases`
