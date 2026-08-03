# Sécurité avancée — V-zone Panel

## Rôle

Durcit l’accès **au panel** (auth applicative), sans remplacer Firewall / Fail2Ban (réseau OS).

## Fonctions

- Politique mots de passe (longueur, majuscule, chiffre, spécial)
- Lockout après N échecs (fenêtre + durée)
- Allowlist / blocklist IP pour le login panel
- Overview WHM (2FA, lockouts, tentatives)
- Forcer le changement de mot de passe (`must_change_password`)
- 2FA TOTP : setup / enable / disable (accounts)
- Self-service client : `/panel/security`

## API

| Méthode | Chemin |
|---------|--------|
| GET | `/api/v1/security/overview/` |
| GET/PATCH | `/api/v1/security/policy/` |
| GET/POST | `/api/v1/security/ip-rules/` |
| DELETE | `/api/v1/security/ip-rules/{id}/` |
| GET | `/api/v1/security/attempts/` |
| GET | `/api/v1/security/lockouts/` |
| POST | `/api/v1/security/unlock/` |
| POST | `/api/v1/security/users/{id}/force-password/` |
| GET | `/api/v1/security/me/` |
| GET/POST/DELETE | `/api/v1/auth/2fa/` |

## UI

- WHM : `/whm/security` (politique) + `/whm/account-security` (2FA perso)
- Client : `/panel/security`

## Codes login

- `requires_2fa` / `invalid_otp`
- `locked_out`
- `ip_forbidden`
- `must_change_password` (middleware API)
