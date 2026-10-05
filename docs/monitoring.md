# Monitoring serveur — V-zone Panel

## Rôle

Surveillance **live complète** du serveur (WHM) + politiques d'alertes.

- **Dashboard live** : `/whm/resources` — CPU, RAM, disques, réseau, processus, services, historique
- **Alertes** : `/whm/monitoring` — seuils, événements, e-mails

## API

| Méthode | Chemin | Description |
|---------|--------|-------------|
| GET | `/api/v1/dashboard/server/` | Snapshot live complet |
| GET | `/api/v1/dashboard/history/?hours=` | Historique (1–168 h) |
| POST | `/api/v1/dashboard/capture/` | Capture manuelle |
| GET | `/api/v1/monitoring/overview/` | Synthèse alertes |
| GET/POST | `/api/v1/monitoring/rules/` | Règles de seuils |
| GET | `/api/v1/monitoring/events/` | Événements |
| POST | `/api/v1/monitoring/evaluate/` | Évaluation manuelle |

Accès : administrateur / revendeur (ACL).

## Contenu du snapshot `/dashboard/server/`

- Identité (hostname, OS, uptime, cœurs)
- CPU % global + par cœur, fréquence, load 1/5/15
- RAM détaillée + swap
- Tous les volumes montés + I/O disque
- Interfaces réseau, débits estimés, connexions
- Top processus (CPU / RAM)
- Services (systemd + fallback processus)
- Températures / ventilateurs si exposés
- Sessions utilisateurs
- Compteurs d'alertes ouvertes

## Contrôle des services

`POST /api/v1/dashboard/services/control/` — body `{ "name": "nginx", "action": "restart" }`

Actions : `start` | `stop` | `restart` | `reload`

Helper root allowlisté : `/usr/local/sbin/vzone-svcctl` (installé via `ensure-panel-helpers.sh`).


## Tâches Celery

- `dashboard.capture_resource_snapshot`
- `monitoring.evaluate_alert_rules`
