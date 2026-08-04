# PostgreSQL (clusters)

Le panel supporte MySQL **et** PostgreSQL pour les bases clients.

## Installation / réparation

```bash
sudo bash /opt/vzone-src/scripts/install-postgresql.sh
```

Ce script :
- installe PostgreSQL si nécessaire ;
- crée/relance les clusters (`pg_lsclusters`, `pg_ctlcluster`) ;
- active le démarrage automatique ;
- configure l'utilisateur admin panel (`VZONE_PG_ADMIN_USER`) pour le provisionnement ;
- force `VZONE_DB_PROVISION_MODE=live`.

## Persistance après reboot

`vzone-postgresql.service` exécute `/usr/local/sbin/vzone-postgresql-ensure` au boot pour vérifier que tous les clusters sont `online`.

## Vérification rapide

```bash
systemctl status postgresql vzone-postgresql.service
pg_lsclusters
```
