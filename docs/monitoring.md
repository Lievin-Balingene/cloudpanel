# Monitoring & Alertes — V-zone Panel

## Rôle

Complète le module **dashboard** (snapshots + graphes) avec des **politiques de seuils**,
des **événements d'alerte** et des **notifications e-mail**.

## Fonctions

- Règles : CPU %, RAM %, Disque %, Load 1m, service down
- Opérateurs, sévérité, cooldown
- Événements : open / acknowledged / resolved
- Évaluation manuelle ou via Celery (`monitoring.evaluate_alert_rules`)
- Hook après `dashboard.capture_resource_snapshot`
- Auto-résolution quand la condition redevient saine

## API

| Méthode | Chemin |
|---------|--------|
| GET | `/api/v1/monitoring/overview/` |
| GET/POST | `/api/v1/monitoring/rules/` |
| GET/PATCH/DELETE | `/api/v1/monitoring/rules/{id}/` |
| GET | `/api/v1/monitoring/events/` |
| POST | `/api/v1/monitoring/events/{id}/acknowledge/` |
| POST | `/api/v1/monitoring/events/{id}/resolve/` |
| POST | `/api/v1/monitoring/evaluate/` |

Accès : administrateur / revendeur.

## Configuration

- `VZONE_ALERT_COOLDOWN_MINUTES` (défaut règle si non spécifié côté UI = 30)
- `VZONE_ALERT_DEFAULT_RECIPIENTS` (fallback e-mail)

## UI

- WHM : `/whm/monitoring`
- Graphes historiques : `/whm/resources` (inchangé)

## Tâches Celery

- `monitoring.evaluate_alert_rules`
- `dashboard.capture_resource_snapshot` (appelle aussi l'évaluation)
