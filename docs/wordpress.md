# WordPress

Installation one-click via WP-CLI sur un domaine existant.

## Prérequis serveur

```bash
sudo bash /opt/vzone-src/scripts/install-wp-cli.sh
```

MariaDB / PHP-FPM doivent déjà être présents (`install-phpmyadmin.sh`).

## API

| Méthode | Chemin | Description |
|---------|--------|-------------|
| GET | `/api/v1/wordpress/overview/` | Compteurs + présence wp-cli |
| GET/POST | `/api/v1/wordpress/sites/` | Liste / installer |
| GET/DELETE | `/api/v1/wordpress/sites/{id}/` | Détail / désinstaller |

POST body : `domain_id`, `title`, `admin_user`, `admin_email`, `admin_password` (opt.), `locale`.

La réponse d’install inclut `admin_password` (affiché une seule fois).

## Flux install

1. Vérifie le domaine (1 WP / domaine)
2. Crée base + user MySQL + ALL PRIVILEGES
3. Assure un `PhpSelector` (MultiPHP) sur le docroot
4. `wp core download` → `config create` → `core install` → permalinks
5. Droits `owner:www-data` + refresh vhosts nginx

## UI

- Client : `/panel/wordpress`
- WHM : `/whm/wordpress`
