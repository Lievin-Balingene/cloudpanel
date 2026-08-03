# Architecture logicielle — V-zone Panel

## Vision

V-zone Panel est un panneau de contrôle d'hébergement **modulaire**, conçu pour
être installé sur VPS KVM, serveurs dédiés et hyperviseurs (VMware, Proxmox,
Hyper-V). Chaque domaine fonctionnel est un module Django indépendant
enregistré dans un registre central.

## Principes

1. **API-first** — l'interface React consomme exclusivement l'API REST / WebSocket.
2. **Modules indépendants** — activation via `VZONE_ENABLED_MODULES`.
3. **Moindre privilège** — rôles `administrator` / `reseller` / `client` + permissions granulaires.
4. **Opérations asynchrones** — Celery pour provisionnement, SSL, backups.
5. **Temps réel** — Django Channels pour métriques et notifications.
6. **Production-ready** — systemd, Nginx, installateur, healthcheck, diagnostic.

## Couches

```
┌─────────────────────────────────────────────┐
│  Frontend React (Vite + TypeScript + TW)    │
└──────────────────┬──────────────────────────┘
                   │ HTTPS / WSS
┌──────────────────▼──────────────────────────┐
│  Nginx (TLS, static, reverse proxy)         │
└──────────────────┬──────────────────────────┘
                   │
┌──────────────────▼──────────────────────────┐
│  Daphne / ASGI  — Django + DRF + Channels   │
│  Celery Worker / Beat                       │
└───────┬──────────────────────────┬──────────┘
        │                          │
┌───────▼────────┐         ┌───────▼────────┐
│  PostgreSQL    │         │  Redis         │
└────────────────┘         └────────────────┘
```

## Arborescence

```
vhost/
├── backend/
│   ├── apps/
│   │   ├── core/          # Registre, santé, audit, métriques
│   │   └── accounts/      # Utilisateurs, quotas, JWT, 2FA
│   ├── vzone/             # Projet Django (settings, ASGI, Celery)
│   └── requirements/
├── frontend/              # SPA React
├── scripts/               # install, update, uninstall, backup, restore…
├── deploy/                # systemd, nginx, docker-compose
└── docs/
```

## Registre de modules

`apps.core.module_registry.ModuleRegistry` permet à chaque module de déclarer :

- métadonnées (nom, version, description)
- dépendances
- permissions
- hooks d'installation

Les modules suivants seront ajoutés progressivement après validation :

`domains`, `dns`, `ssl`, `files`, `ftp`, `email`, `databases`, `python_apps`,
`node_apps`, `php`, `git_deploy`, `docker_mgmt`, `backups`, `monitoring`,
`firewall`, `security`.

## Sécurité (socle)

- JWT (access + refresh rotatif + blacklist)
- Hachage Argon2
- Rate limiting DRF
- CSRF / XSS headers
- Audit log
- 2FA TOTP (prêt)
- Cookies HttpOnly, HSTS en production

## Décisions techniques

| Choix | Justification |
|-------|---------------|
| Django 5 + DRF | Maturité, admin, ORM, écosystème auth |
| Channels + Redis | WebSockets scalables |
| Celery | Tâches longues hors requête HTTP |
| React + Vite | DX rapide, bundle moderne |
| Tailwind (sans Bootstrap) | Design system unique contrôlé |
| PostgreSQL | Fiabilité ACID pour multi-tenant |
| Module registry | Extensibilité commerciale (plugins) |
