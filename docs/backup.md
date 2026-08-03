# Guide de sauvegarde

Voir aussi `scripts/backup.sh` et `scripts/restore.sh`.
Pour les sauvegardes **par compte** dans le panel : `docs/backups.md`.

## Contenu d'une sauvegarde plateforme

- Dump PostgreSQL (`database.dump`)
- Configuration `/etc/vzone`
- Données applicatives (`data.tar.gz`)
- Code applicatif (`app.tar.gz`)

## Fréquence recommandée

- Quotidienne pour la base
- Hebdomadaire complète hors site (S3 / B2 / R2 — évolution future du module backups)
