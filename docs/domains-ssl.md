# Domaines & SSL — V-zone Panel

## Domaines

Types supportés :

- `primary` — domaine principal → `~/public_html`
- `addon` — domaine additionnel → `~/domains/<hostname>/public_html`
- `subdomain` — sous-domaine → `~/domains/<hostname>/public_html`
- `parked` / `alias` — partagent le docroot du parent

À la création d'un domaine primary/addon/subdomain :

1. Vérification du quota package
2. Création du document root (permissions `755`) + `index.html` + `cgi-bin/`
3. Création automatique de la zone DNS + enregistrements A (@, www)
4. Génération d'un **vhost Nginx** dédié

## Routage web (priorité)

L'ordre de priorité pour servir un domaine :

1. **App Python** liée (`domain_name`) et **running** → `proxy_pass` vers son port
2. **App Node.js** liée et **running** → `proxy_pass`
3. **Sélecteur PHP** lié → PHP-FPM sur le docroot du sélecteur
4. Sinon → **fichiers statiques** du `document_root` (+ PHP système si disponible)

Dès qu'une app Django/Flask/Node démarre ou change de domaine, les vhosts sont régénérés.

Fichiers Nginx : `VZONE_NGINX_DOMAINS_DIR` (défaut `/var/lib/vzone/nginx/domains/*.conf`).

## SSL

- **Let's Encrypt** via `certbot` (`VZONE_SSL_BACKEND=auto|certbot`)
- Installation : `sudo bash scripts/install-certbot.sh` (appelé aussi par `update.sh`)
- Challenge HTTP-01 sur le webroot partagé `/var/lib/vzone/acme` (location `/.well-known/acme-challenge/`)
- Après émission : vhost Nginx **443** + redirection HTTP→HTTPS
- `www.` n’est demandé que pour les apex `example.com` (pas pour `vpanel.exemple.co.uk`)
- **Self-signed** en développement / tests (`selfsigned`)
- **Certificat personnalisé** (PEM)
- Renouvellement Celery : `domains.renew_ssl_certificates`

Prérequis DNS : l’enregistrement A (et AAAA si utilisé) du domaine doit pointer vers le serveur avant l’émission.

## API

| Méthode | Chemin |
|---------|--------|
| GET/POST | `/api/v1/domains/` |
| POST | `/api/v1/domains/subdomains/` |
| GET/PATCH/DELETE | `/api/v1/domains/{id}/` |
| GET/POST | `/api/v1/domains/{id}/redirects/` |
| POST | `/api/v1/domains/{id}/ssl/letsencrypt/` |
| POST | `/api/v1/domains/{id}/ssl/custom/` |
