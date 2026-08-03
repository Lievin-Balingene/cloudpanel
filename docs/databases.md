# Bases de données — V-zone Panel

## Fonctions

- Création / suppression de bases MySQL/MariaDB et PostgreSQL
- Préfixe login `owner_name` (style panneau d'hébergement)
- Utilisateurs SQL + changement de mot de passe
- Attribution de privilèges ALL / WRITE / READ
- Quotas package (`databases`)
- Inventory + SQL pending (`VZONE_DB_MAPS_DIR`)
- Provisionnement live via `mysql` / `psql` ou mode `mock`
- Liens phpMyAdmin / pgAdmin

## Modes de provisionnement

| Mode | Comportement |
|------|----------------|
| `auto` | Exécute si credentials admin configurés, sinon écrit SQL pending |
| `live` | Exige un backend configuré |
| `mock` | Catalogue + fichiers SQL uniquement (tests / démo) |

## API

| Méthode | Chemin |
|---------|--------|
| GET | `/api/v1/databases/overview/` |
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
- `VZONE_PHPMYADMIN_URL`, `VZONE_PGADMIN_URL`

## UI

- WHM : `/whm/databases`
- Client : `/panel/databases`
