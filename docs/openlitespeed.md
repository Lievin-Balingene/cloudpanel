# OpenLiteSpeed (moteur optionnel)

V-zone peut servir les sites clients **PHP / WordPress / static** via OpenLiteSpeed,
tout en gardant **Nginx** comme frontal unique sur les ports **80/443**.

## Architecture

```
Internet :80/:443
  → Nginx (edge)
      ├─ Panel, ACME, parking, phpMyAdmin, Roundcube
      ├─ Python / Node  → proxy_pass ports locaux
      └─ Domaines web_engine=ols → proxy_pass 127.0.0.1:8088
            → OpenLiteSpeed + lsphp
```

- TLS et Let’s Encrypt restent gérés par Nginx (`/var/lib/vzone/ssl/`).
- Le challenge ACME `/.well-known/acme-challenge/` reste sur Nginx (avant le proxy OLS).
- Les apps Python/Node **ignorent** le moteur OLS (toujours proxy Nginx).

## Activation

Dès qu’OpenLiteSpeed est **installé**, le mode `auto` l’active :

```bash
sudo bash /opt/vzone-src/scripts/install-openlitespeed.sh
sudo systemctl restart vzone-api
```

`/etc/vzone/vzone.env` :
```bash
VZONE_OLS_ENABLED=auto   # auto | 1 | 0
VZONE_OLS_DEFAULT_ENGINE=1
```

## Utilisation (comme cPanel)

- **Nouveaux** domaines / sous-domaines → OpenLiteSpeed par défaut
- Domaines déjà en Nginx → WHM → OpenLiteSpeed → **Activer OLS sur les domaines**
- Ou manuellement : Domains → Web engine → OpenLiteSpeed

## Rollback d’un site

Remettre **Web engine = Nginx + PHP-FPM** sur le domaine → resync automatique.
Aucune coupure du panel.

## Désactiver OLS globalement

```bash
# /etc/vzone/vzone.env
VZONE_OLS_ENABLED=0
```

Puis resync des vhosts (ou redémarrer l’API). Les domaines restent en base ;
ils seront servis en PHP-FPM tant que le flag est off.

## Fichiers runtime

| Chemin | Rôle |
|--------|------|
| `/usr/local/lsws/` | Installation OLS |
| `/var/lib/vzone/ols/vzone-vhosts.conf` | Listener + maps + virtualhosts (généré) |
| `/var/lib/vzone/ols/vhconf/*.conf` | Config par domaine |
| `/usr/local/sbin/vzone-ols-reload` | Reload root (agent path) |

## Dépannage

```bash
systemctl status lshttpd   # ou lsws
cat /usr/local/lsws/VERSION
sudo nginx -t && systemctl reload nginx
ls -la /var/lib/vzone/ols/
# Si l'UI montre encore « Activé: non » après install :
grep VZONE_OLS /etc/vzone/vzone.env
sudo systemctl restart vzone-api
```
