# Email — V-zone Panel

## Stack MTA

## Délivrabilité (anti-spam)

```bash
sudo bash /opt/vzone-src/scripts/repair-mail-reputation.sh
# Si Roundcube affiche « SMTP service unavailable » :
sudo bash /opt/vzone-src/scripts/repair-smtp.sh
```

- OpenDKIM signe les mails Roundcube (SMTP :587)
- SPF / DKIM / DMARC publiés dans BIND à la création du domaine mail
- Vérifiez `DKIM-Signature` dans les en-têtes du message reçu
- PTR (rDNS) de l’IP publique → à régler chez l’hébergeur VPS

## Webmail Roundcube

- URL : `/webmail/`
- SSO panel : bouton **Webmail** sur chaque boîte → connexion automatique
- Login manuel : adresse e-mail complète + mot de passe
- IMAP `127.0.0.1:143` · SMTP `127.0.0.1:587` (auth = compte mail)

Boîtes créées **avant** cette version : réinitialisez le mot de passe dans le panel pour activer le SSO.

## Arborescence home (style cPanel)

```
/home/<user>/
  public_html/
  www -> public_html
  mail/<domaine>/<local>/{cur,new,tmp}   # Maildir
  etc/
  ssl/
  logs/
  tmp/
  .trash/
```

## Fonctions panel

- Domaines mail, boîtes, suspension, reset mot de passe
- Forwarders / aliases, répondeurs, filtres, listes
- SPF / MX / DKIM / DMARC + sync zone DNS
- Export maps : `dovecot-users`, `virtual_mailboxes`, `valiases`, `vdomains`, OpenDKIM
- Mots de passe **SHA512-CRYPT** (natifs Dovecot) + secret Fernet pour SSO
- Quotas package (`emails`), Roundcube intégré

## Réputation (checklist)

1. **PTR / rDNS** chez l’hébergeur → hostname du serveur
2. **SPF** : généré avec `ip4:<VZONE_MAIL_PUBLIC_IP> mx a ~all` (passer à `-all` une fois stable)
3. **DKIM** : activer dans le panel (OpenDKIM signe les sorties)
4. **DMARC** : démarrer en `p=none`, puis `quarantine` / `reject`
5. **TLS** : remplacer snakeoil par un certificat Let’s Encrypt pour `mail.domaine`
6. Fail2ban : jails Postfix/Dovecot (`deploy/fail2ban/jail.d/vzone-mail.conf`)

## Configuration

| Variable | Rôle |
|----------|------|
| `VZONE_WEBMAIL_URL` | URL Roundcube (`/webmail/`) |
| `VZONE_ROUNDCUBE_SSO_DIR` | Tokens SSO one-shot |
| `VZONE_ROUNDCUBE_IMAP_HOST` | Hôte IMAP pour le SSO |
| `VZONE_MAIL_MAPS_DIR` | Maps Postfix/Dovecot |
| `VZONE_MAIL_STACK` | `auto` \| `live` \| `mock` |
| `VZONE_MAIL_PUBLIC_IP` | IP dans le SPF |

## Clients mail

| Service | Hôte | Port | Sécurité |
|---------|------|------|----------|
| IMAP | mail.domaine ou IP | 993 | SSL/TLS |
| SMTP | mail.domaine ou IP | 587 | STARTTLS |
| SMTP | | 465 | SSL/TLS |
| Webmail | `/webmail/` | 80/443 | Roundcube |

Identifiant = adresse e-mail complète.

## API

| Méthode | Chemin |
|---------|--------|
| GET | `/api/v1/email/overview/` |
| POST | `/api/v1/email/webmail/sso/` `{ "mailbox_id": N }` |
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

## UI

- WHM : `/whm/email`
- Client : `/panel/email`
