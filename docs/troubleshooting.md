# Guide de dépannage

| Symptôme | Action |
|----------|--------|
| API 502 | `systemctl status vzone-api` + `journalctl -u vzone-api -n 100` |
| Health degraded | Vérifier PostgreSQL et Redis |
| Frontend blanc | Vérifier build `frontend/dist` et config Nginx |
| Login 401 | Vérifier horloge serveur (JWT) et blacklist Redis |
| Celery inactif | `systemctl restart vzone-worker vzone-beat` |

Diagnostic complet :

```bash
sudo bash scripts/diagnostic.sh
```
