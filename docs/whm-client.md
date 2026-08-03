# Architecture des espaces WHM / Client

V-zone Panel v0.2 sépare clairement deux interfaces, sur le modèle WHM + cPanel :

## `/whm` — Web Host Manager

Réservé aux **administrateurs** et **revendeurs**.

- Accueil serveur (CPU, RAM, disque, services)
- Account Functions (création comptes + assignation package)
- Packages (plans client/revendeur, sync quotas)
- DNS Functions (zones + records + DNSSEC)
- Server Resources (historique graphes)
- Email (domaines mail, boîtes, forwarders, DKIM)
- Bases de données (MySQL / PostgreSQL)
- Applications Python (WSGI / ASGI)
- Applications Node.js (npm)
- PHP multi-version (MultiPHP)
- Git Version Control
- Docker Containers
- Backups
- Monitoring & Alertes
- Firewall & Fail2Ban
- Sécurité avancée (politique, lockout, IP panel)
- Mon 2FA (compte WHM)
- Server Resources (historique)

## `/panel` — Espace client

Réservé aux **clients**.

- Grille d'outils type panneau d'hébergement
- Zone Editor DNS
- Email Accounts
- Databases
- Setup Python App
- Setup Node.js App
- Select PHP Version
- Git Version Control
- Docker Containers
- Backup
- Sécurité (2FA & mot de passe)
- Vue package / quotas

## Design

Palette orange / navy familière aux administrateurs habitués à WHM/cPanel,
**sans** reprise des logos, marques ou assets propriétaires cPanel.

## Performance

- Snapshots ressources (rétention 72 h)
- Tâche Celery `dashboard.capture_resource_snapshot`
- Capture manuelle WHM en secours
- API paginée / réponses `{success, data}`
- Frontend React Query avec refetch ciblé
