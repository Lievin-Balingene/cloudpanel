# V-zone Pulse — Resource Governor

Alternative libre et moderne aux limites LVE (CloudLinux), sans noyau propriétaire.

## Principes

| Capacité | Technologie |
|----------|-------------|
| CPU / RAM / processus / I/O | **cgroups v2** via slices systemd `vz-pulse-<user>.slice` |
| Isolation FS (terminal) | bubblewrap (`vzone-jailterm`) |
| Exécution apps | `vzone-runas` → `systemd-run --slice=…` |
| PHP | pools FPM Pulse-aware (`pm.max_children`, `memory_limit`, UID client) |
| Quotas plan | champs package `cpu_millicores`, `ram_mb`, `max_processes`, `inode_limit` |

## Helper

```bash
sudo /usr/local/sbin/vzone-resourcectl apply alice --cpu-millicores 1000 --memory-mb 1024 --tasks 100
sudo /usr/local/sbin/vzone-resourcectl status alice
```

Installé par `ensure-mkhome-sudoers.sh`.

## API

| Méthode | Chemin |
|---------|--------|
| GET | `/api/v1/packages/pulse/` (WHM) |
| GET | `/api/v1/packages/pulse/mine/` |
| GET/POST | `/api/v1/packages/pulse/<user_id>/` |

## UI

- WHM : `/whm/pulse`
- Client : `/panel/pulse`
- Packages : section « V-zone Pulse » dans le formulaire de plan

## Config

`VZONE_PULSE_MODE=auto|live|mock`
