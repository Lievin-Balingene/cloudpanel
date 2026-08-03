# Guide de migration

## Depuis une version antérieure de V-zone

```bash
sudo bash scripts/backup.sh
sudo bash scripts/update.sh
sudo bash scripts/healthcheck.sh
```

## Depuis un autre panneau (cPanel / Plesk / DirectAdmin)

Le module de migration sera livré dans une étape ultérieure. En attendant :

1. Exporter zones DNS, bases, mails
2. Installer V-zone sur le serveur cible
3. Importer progressivement via l'API / modules concernés
