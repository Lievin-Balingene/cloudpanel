# Domaines & SSL — V-zone Panel

## Domaines

Types supportés :

- `primary` — domaine principal
- `addon` — domaine additionnel
- `subdomain` — sous-domaine (lié au parent)
- `parked` / `alias` — pointent vers un domaine cible

À la création d'un domaine primary/addon/parked/alias :

1. Vérification du quota package
2. Création du document root
3. Création automatique de la zone DNS + enregistrements A (@, www)

## SSL

- **Let's Encrypt** via `certbot` (`VZONE_SSL_BACKEND=auto|certbot`)
- **Self-signed** en développement / tests (`selfsigned`)
- **Certificat personnalisé** (PEM)
- Renouvellement Celery : `domains.renew_ssl_certificates`

## API

| Méthode | Chemin |
|---------|--------|
| GET/POST | `/api/v1/domains/` |
| POST | `/api/v1/domains/subdomains/` |
| GET/PATCH/DELETE | `/api/v1/domains/{id}/` |
| GET/POST | `/api/v1/domains/{id}/redirects/` |
| POST | `/api/v1/domains/{id}/ssl/letsencrypt/` |
| POST | `/api/v1/domains/{id}/ssl/custom/` |
