# Guide de dépannage

| Symptôme | Action |
|----------|--------|
| API 502 | `systemctl status vzone-api` + `journalctl -u vzone-api -n 100` |
| Health degraded | Vérifier PostgreSQL et Redis |
| Frontend blanc | Vérifier build `frontend/dist` et config Nginx |
| Login 401 | Vérifier horloge serveur (JWT) et blacklist Redis |
| Celery inactif | `systemctl restart vzone-worker vzone-beat` |
| Arrêter l’API (vzone-api) | **Pas depuis le panneau** (coupe WHM). En SSH : `sudo systemctl stop vzone-api` puis `sudo systemctl start vzone-api` |

### Arrêt / redémarrage de vzone-api

Le panneau WHM **ne propose pas** l’arrêt de `vzone-api` : cela coupe immédiatement l’interface.

```bash
# SSH root / sudo
sudo systemctl stop vzone-api
sudo systemctl start vzone-api
# ou
sudo systemctl restart vzone-api
sudo systemctl status vzone-api
```

Diagnostic complet :

```bash
sudo bash scripts/diagnostic.sh
```
