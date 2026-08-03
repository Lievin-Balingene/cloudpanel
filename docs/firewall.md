# Firewall & Fail2Ban — V-zone Panel

## Fonctions

- Règles firewall (allow/deny, TCP/UDP, ports, CIDR)
- Application mock ou `iptables`
- Jails Fail2Ban (sshd, nginx-http-auth, postfix par défaut)
- Ban / unban IP
- Sync état jails
- Journal d'événements

## Modes

| Mode | Comportement |
|------|----------------|
| `mock` | Fichiers sous `VZONE_FIREWALL_CONFIG_DIR` (tests) |
| `live` | CLI `iptables` + `fail2ban-client` |
| `auto` | live si binaires présents, sinon mock |

## API

| Méthode | Chemin |
|---------|--------|
| GET | `/api/v1/firewall/overview/` |
| GET/POST | `/api/v1/firewall/rules/` |
| GET/PATCH/DELETE | `/api/v1/firewall/rules/{id}/` |
| POST | `/api/v1/firewall/rules/{id}/apply/` |
| GET | `/api/v1/firewall/fail2ban/jails/` |
| GET | `/api/v1/firewall/fail2ban/bans/` |
| POST | `/api/v1/firewall/fail2ban/ban/` |
| POST | `/api/v1/firewall/fail2ban/unban/` |
| POST | `/api/v1/firewall/fail2ban/sync/` |
| GET | `/api/v1/firewall/events/` |

Accès : administrateur / revendeur.

## Configuration

- `VZONE_FIREWALL_PROVISION_MODE`
- `VZONE_FIREWALL_CONFIG_DIR`
- `VZONE_IPTABLES_BIN`
- `VZONE_FAIL2BAN_BIN`

## UI

- WHM : `/whm/firewall`

## Notes

L'installateur système (`scripts/install.sh`) configure déjà UFW/firewalld + fail2ban.
Ce module expose la gestion depuis le panel.
