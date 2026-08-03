# PHP multi-version — V-zone Panel

## Fonctions

- Catalogue de versions PHP (8.1 → 8.4, extensible)
- Sélecteur par chemin (ex: `public_html`) / domaine
- Handlers : FPM, CGI, LSAPI
- Surcharges `.user.ini` (memory_limit, upload_max_filesize…)
- Liste d'extensions
- Export pools PHP-FPM + meta JSON
- Hint `.htaccess` MultiPHP
- Découverte système + version par défaut (admin)

## API

| Méthode | Chemin |
|---------|--------|
| GET | `/api/v1/php/overview/` |
| GET | `/api/v1/php/versions/` |
| POST | `/api/v1/php/versions/discover/` (admin) |
| POST | `/api/v1/php/versions/{id}/default/` (admin) |
| GET/POST | `/api/v1/php/selectors/` |
| GET/PATCH/DELETE | `/api/v1/php/selectors/{id}/` |

## Configuration

- `VZONE_PHP_PROVISION_MODE` — auto | live | mock
- `VZONE_PHP_CONFIG_DIR` — pools, ini, selectors

## UI

- WHM : `/whm/php`
- Client : `/panel/php`
