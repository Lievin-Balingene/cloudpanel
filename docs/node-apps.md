# Applications Node.js — V-zone Panel

## Fonctions

- Création d'apps Node.js dans le home (`nodeapps/<name>`)
- Scaffold `package.json` + `server.js`
- Frameworks : generic, Express, NestJS, Next.js
- `npm install`
- Start / stop / restart (`npm run <script>`)
- Consultation des logs
- Quotas package (`node_apps`)
- Config JSON exportée (`VZONE_NODE_CONFIG_DIR`)

## Modes de provisionnement

| Mode | Comportement |
|------|----------------|
| `auto` | Opérations réelles si Node/npm dispo |
| `live` | Force exécution réelle |
| `mock` | Scaffold uniquement (tests) |

## API

| Méthode | Chemin |
|---------|--------|
| GET | `/api/v1/node/overview/` |
| GET/POST | `/api/v1/node/apps/` |
| GET/PATCH/DELETE | `/api/v1/node/apps/{id}/` |
| POST | `/api/v1/node/apps/{id}/start/` |
| POST | `/api/v1/node/apps/{id}/stop/` |
| POST | `/api/v1/node/apps/{id}/restart/` |
| POST | `/api/v1/node/apps/{id}/install/` |
| GET | `/api/v1/node/apps/{id}/logs/` |

## Configuration

- `VZONE_NODE_PROVISION_MODE`
- `VZONE_NODE_CONFIG_DIR`
- `VZONE_NODE_PORT_BASE` (défaut 9100)
- `VZONE_NODE_BIN`, `VZONE_NPM_BIN`

## UI

- WHM : `/whm/node`
- Client : `/panel/node`
