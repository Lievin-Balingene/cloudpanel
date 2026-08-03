# Email — V-zone Panel

## Stack MTA

Production : **Postfix** (SMTP 25/587/465) + **Dovecot** (IMAP/POP3 143/993/110/995) + **OpenDKIM**.

Installation / mise à jour :

```bash
sudo bash scripts/install-mail.sh
# ou via update.sh (appelé automatiquement)
```

## Arborescence home (style cPanel)

```
/var/lib/vzone/homes/<user>/
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

- Domaines mail, boîtes, suspension
- Forwarders / aliases, répondeurs, filtres, listes
- SPF / MX / DKIM / DMARC + sync zone DNS
- Export maps : `dovecot-users`, `virtual_mailboxes`, `valiases`, `vdomains`, OpenDKIM
- Mots de passe **SHA512-CRYPT** (natifs Dovecot)
- Quotas package (`emails`), lien webmail

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
| `VZONE_WEBMAIL_URL` | URL webmail |
| `VZONE_MAIL_MAPS_DIR` | Maps Postfix/Dovecot |
| `VZONE_MAIL_STACK` | `auto` \| `live` \| `mock` |
| `VZONE_MAIL_PUBLIC_IP` | IP dans le SPF |

## Clients mail

| Service | Hôte | Port | Sécurité |
|---------|------|------|----------|
| IMAP | mail.domaine ou IP | 993 | SSL/TLS |
| SMTP | mail.domaine ou IP | 587 | STARTTLS |
| SMTP | | 465 | SSL/TLS |

Identifiant = adresse e-mail complète.

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

## UI

- WHM : `/whm/email`
- Client : `/panel/email`
