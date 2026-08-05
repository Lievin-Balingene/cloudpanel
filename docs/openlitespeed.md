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

## Activation (une fois)

1. Dans `/etc/vzone/vzone.env` :

```bash
VZONE_OLS_ENABLED=1
VZONE_OLS_LISTEN=127.0.0.1:8088
```

2. Installer / mettre à jour :

```bash
cd /opt/vzone-src && git pull
sudo bash scripts/install-openlitespeed.sh
# ou : sudo bash scripts/update.sh  (installe OLS si le flag est à 1)
```

3. WHM → **OpenLiteSpeed** : vérifier « Installé » + service actif.

## Utilisation

- WHM / Client → **Domains** : champ **Web engine**
  - `Nginx + PHP-FPM` (défaut)
  - `OpenLiteSpeed` (opt-in, si installé)
- À la bascule, le vhost Nginx proxifie vers OLS et le handler PHP passe en **LSAPI**.

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
sudo /usr/local/lsws/bin/lswsctrl fullversion
sudo nginx -t && systemctl reload nginx
ls -la /var/lib/vzone/ols/
```
