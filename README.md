# V-zone Panel

Panneau de contrôle d'hébergement web professionnel pour VPS, serveurs dédiés et machines virtuelles.

**Version :** 0.18.0  
**Dépôt :** https://github.com/Lievin-Balingene/cloudpanel

## Modules livrés

Socle WHM/Client, packages, DNS, domaines/SSL, files, FTP, email, databases, Python, Node.js, PHP, Git, Docker, Backups, Monitoring, Firewall/Fail2Ban, Sécurité avancée (2FA, lockout, IP).

## Stack

| Couche | Technologie |
|--------|-------------|
| Backend | Python 3.12+, Django 5, DRF, Channels, Celery |
| Frontend | React 18, Vite, TypeScript, TailwindCSS |
| Base de données | PostgreSQL |
| Cache / Broker | Redis |
| Reverse proxy | Nginx |

## Installation production (VPS)

Sur Ubuntu 22.04/24.04, Debian 12, AlmaLinux 9 ou Rocky 9 (root) :

```bash
curl -fsSL https://raw.githubusercontent.com/Lievin-Balingene/cloudpanel/main/scripts/bootstrap-install.sh | sudo bash
```

Ou en deux étapes :

```bash
sudo apt-get update && sudo apt-get install -y git
sudo git clone https://github.com/Lievin-Balingene/cloudpanel.git /opt/vzone-src
cd /opt/vzone-src
sudo bash scripts/install.sh
```

L'installateur configure PostgreSQL, Redis, Nginx, Node.js, Docker, les services systemd et affiche l'URL + mot de passe admin temporaire.

## Développement local

```bash
cp .env.example .env
docker compose -f deploy/docker-compose.dev.yml up -d
cd backend && python -m venv .venv && source .venv/bin/activate
pip install -r requirements/dev.txt
python manage.py migrate
python manage.py createsuperuser
cd ../frontend && npm install && npm run dev
```

## Documentation

- [Installation](docs/installation.md)
- [Architecture](docs/architecture.md)
- [API](docs/api.md)
- [Roadmap](docs/roadmap.md)

## Licence

Copyright © 2026 V-zone Panel. Tous droits réservés.
