# Documentation API — V-zone Panel

La spécification OpenAPI est générée automatiquement.

- Swagger UI : `/api/docs/`
- ReDoc : `/api/redoc/`
- Schéma brut : `/api/schema/`

## Endpoints socle (v0.1.0)

| Méthode | Chemin | Auth | Description |
|---------|--------|------|-------------|
| GET | `/api/v1/health/` | Non | Santé |
| GET | `/api/v1/version/` | Non | Version |
| POST | `/api/v1/auth/login/` | Non | Connexion JWT |
| POST | `/api/v1/auth/logout/` | Oui | Déconnexion |
| POST | `/api/v1/auth/refresh/` | Non | Refresh token |
| GET | `/api/v1/auth/me/` | Oui | Profil |
| POST | `/api/v1/auth/password/` | Oui | Changer MDP |
| GET/POST | `/api/v1/auth/2fa/` | Oui | Setup / activer 2FA |
| GET/POST | `/api/v1/auth/users/` | Admin/Reseller | Liste / création |
| GET | `/api/v1/core/modules/` | Admin | Modules |
| GET | `/api/v1/core/metrics/` | Admin | Métriques système |
| WS | `/ws/metrics/` | Admin | Métriques temps réel |

## Email (v0.6.0)

Voir `docs/email.md` — préfixe `/api/v1/email/`.

## Bases de données (v0.7.0)

Voir `docs/databases.md` — préfixe `/api/v1/databases/`.

## Applications Python (v0.8.0)

Voir `docs/python-apps.md` — préfixe `/api/v1/python/`.

## Applications Node.js (v0.9.0)

Voir `docs/node-apps.md` — préfixe `/api/v1/node/`.

## PHP multi-version (v0.10.0)

Voir `docs/php.md` — préfixe `/api/v1/php/`.

## Git Deploy (v0.11.0)

Voir `docs/git-deploy.md` — préfixe `/api/v1/git/`.

## Docker (v0.12.0)

Voir `docs/docker.md` — préfixe `/api/v1/docker/`.

## Backups (v0.13.0)

Voir `docs/backups.md` — préfixe `/api/v1/backups/`.

## Monitoring & Alertes (v0.14.0)

Voir `docs/monitoring.md` — préfixe `/api/v1/monitoring/`.

## Firewall & Fail2Ban (v0.15.0)

Voir `docs/firewall.md` — préfixe `/api/v1/firewall/`.

## Sécurité avancée (v0.16.0)

Voir `docs/security.md` — préfixe `/api/v1/security/` (+ `/api/v1/auth/2fa/`).
