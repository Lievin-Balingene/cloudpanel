# Docker — V-zone Panel

## Fonctions

- Création de conteneurs (image, tag, ports, env, volumes jailés)
- Start / stop / restart / remove
- Limites mémoire / CPU
- Restart policy
- Logs conteneur
- Journaux d'événements
- Quotas package (`docker_containers`, 0 = désactivé)

## Modes

| Mode | Comportement |
|------|----------------|
| `auto` / `live` | CLI `docker run/start/stop/logs` |
| `mock` | Catalogue + logs fictifs (tests) |

## API

| Méthode | Chemin |
|---------|--------|
| GET | `/api/v1/docker/overview/` |
| GET/POST | `/api/v1/docker/containers/` |
| GET/PATCH/DELETE | `/api/v1/docker/containers/{id}/` |
| POST | `/api/v1/docker/containers/{id}/start/` |
| POST | `/api/v1/docker/containers/{id}/stop/` |
| POST | `/api/v1/docker/containers/{id}/restart/` |
| GET | `/api/v1/docker/containers/{id}/logs/` |
| GET | `/api/v1/docker/events/` |

## Configuration

- `VZONE_DOCKER_PROVISION_MODE`
- `VZONE_DOCKER_CONFIG_DIR`
- `VZONE_DOCKER_BIN`

## Accès socket (production)

L'API tourne sous l'utilisateur `vzone`. Sans appartenance au groupe `docker`,
`docker run` échoue avec *permission denied* sur `/var/run/docker.sock`.

```bash
sudo bash /opt/vzone/scripts/ensure-docker-access.sh
```

Ce script ajoute `vzone` au groupe `docker`, applique un drop-in systemd
`SupplementaryGroups=docker`, et redémarre `vzone-api`.

## UI

- WHM : `/whm/docker`
- Client : `/panel/docker`
