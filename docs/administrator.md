# Guide administrateur — V-zone Panel

## Rôles

| Rôle | Capacités |
|------|-----------|
| Administrateur | Accès total serveur, modules, utilisateurs |
| Revendeur | Crée/gère des clients, quotas délégués |
| Client | Gère ses propres ressources dans les limites de quota |

## Changer le mot de passe admin

```bash
sudo -u vzone /opt/vzone/backend/.venv/bin/python \
  /opt/vzone/backend/manage.py changepassword admin
```

## Santé

```bash
sudo bash /opt/vzone/scripts/healthcheck.sh
sudo bash /opt/vzone/scripts/diagnostic.sh
```

## Sauvegardes

```bash
sudo bash /opt/vzone/scripts/backup.sh
sudo bash /opt/vzone/scripts/restore.sh /var/backups/vzone/vzone-TIMESTAMP
```

## Journaux

```bash
journalctl -u vzone-api -f
journalctl -u vzone-worker -f
```
