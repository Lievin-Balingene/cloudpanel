# Guide d'installation — V-zone Panel

## Prérequis

- Ubuntu 22.04/24.04 LTS, Debian 12, AlmaLinux 9 ou Rocky Linux 9
- Accès root
- 2 Go RAM minimum (4 Go recommandés)
- 20 Go disque
- Ports 22, 80, 443 ouverts

## Installation

Une commande (recommandé) :

```bash
curl -fsSL https://raw.githubusercontent.com/Lievin-Balingene/cloudpanel/main/scripts/bootstrap-install.sh | sudo bash
```

Ou depuis un clone local :

```bash
sudo bash scripts/install.sh
```

L'installateur :

1. Détecte la distribution
2. Installe PostgreSQL, Redis, Nginx, Node.js, Docker, Python
3. Crée l'utilisateur système `vzone`
4. Configure la base et les services systemd
5. Compile le frontend
6. Affiche l'URL, l'admin et le mot de passe temporaire

## Développement local

```bash
cp .env.example .env
docker compose -f deploy/docker-compose.dev.yml up -d
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
source .venv/bin/activate
pip install -r requirements/dev.txt
python manage.py migrate
python manage.py createsuperuser
cd ../frontend && npm install && npm run dev
```

API : http://127.0.0.1:8000 — UI : http://127.0.0.1:5173 — Docs : /api/docs/

## Mise à jour / Désinstallation

```bash
sudo bash scripts/update.sh
sudo bash scripts/uninstall.sh          # conserve les données
sudo bash scripts/uninstall.sh --purge  # purge totale
```
