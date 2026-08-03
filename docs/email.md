# Email — V-zone Panel

## Fonctions

- Domaines mail (liés optionnellement à un Domain hébergé)
- Boîtes (maildir jail sous le home utilisateur)
- Suspension / réactivation
- Forwarders / aliases
- Répondeurs automatiques
- Filtres simples par boîte
- Listes de diffusion basiques
- SPF / MX / DKIM / DMARC + sync zone DNS
- Export maps Postfix/Dovecot (`vmailbox`, `valiases`)
- Quotas package (`emails`)
- Lien webmail (`VZONE_WEBMAIL_URL`)

## API

| Méthode | Chemin |
|---------|--------|
| GET | `/api/v1/email/overview/` |
| GET/POST | `/api/v1/email/domains/` |
| GET/DELETE | `/api/v1/email/domains/{id}/` |
| POST | `/api/v1/email/domains/{id}/dns-sync/` |
| POST | `/api/v1/email/domains/{id}/dkim/` |
| POST | `/api/v1/email/domains/{id}/dmarc/` |
| GET/POST | `/api/v1/email/mailboxes/` |
| GET/PATCH/DELETE | `/api/v1/email/mailboxes/{id}/` |
| POST | `/api/v1/email/mailboxes/{id}/suspend/` |
| GET/PUT | `/api/v1/email/mailboxes/{id}/autoresponder/` |
| GET/POST | `/api/v1/email/mailboxes/{id}/filters/` |
| DELETE | `/api/v1/email/mailboxes/{id}/filters/{filter_id}/` |
| GET/POST | `/api/v1/email/forwarders/` |
| DELETE | `/api/v1/email/forwarders/{id}/` |
| GET/POST | `/api/v1/email/lists/` |

## Configuration

- `VZONE_WEBMAIL_URL` — URL du webmail (défaut `/webmail/`)
- `VZONE_MAIL_MAPS_DIR` — répertoire des maps virtuelles
- `VZONE_MAIL_HOME_ROOT` — racine optionnelle des homes mail

## UI

- WHM : `/whm/email`
- Client : `/panel/email`
