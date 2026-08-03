# Guide développeur — V-zone Panel

## Stack locale

Voir [installation.md](installation.md) section développement.

## Ajouter un module

1. Créer `backend/apps/<nom>/`
2. Déclarer `module.py` avec `registry.register(ModuleMeta(...))`
3. Ajouter l'app dans `INSTALLED_APPS`
4. Étendre `VZONE_ENABLED_MODULES`
5. Inclure les URLs sous `/api/v1/<prefix>/`
6. Écrire tests unitaires + intégration
7. Documenter dans `docs/`

## Tests

```bash
cd backend
pytest -q
cd ../frontend
npm test
```

## Qualité

```bash
cd backend && ruff check .
cd ../frontend && npm run lint
```

## Conventions

- Réponses API : `{ "success": true, "data": ... }` ou `{ "success": false, "error": {...} }`
- Pas de TODO / stubs dans le code livré
- Français pour l'UI et la documentation utilisateur
- Anglais acceptable pour identifiants techniques
