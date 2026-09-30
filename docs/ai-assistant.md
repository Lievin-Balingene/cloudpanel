# V-zone AI Deployment Assistant

Assistant du **panneau client** : lecture + actions via tools whitelistés (pas de shell libre).

## Architecture

```
UI (AiDeploymentAssistant)
  → /api/v1/ai/
    → Agent (services/agent.py)
      → Provider (ollama | openai_compat | mock)
      → Tools whitelist (tools/handlers*.py) → services existants
```

## Configuration rapide (Ollama)

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.2
# dans /etc/vzone/vzone.env :
# VZONE_AI_PROVIDER=auto
# VZONE_AI_OLLAMA_URL=http://127.0.0.1:11434
# VZONE_AI_OLLAMA_MODEL=llama3.2
sudo systemctl restart vzone-api
```

Sans Ollama, le provider `mock` guide quand même (heuristiques + tools lecture).
Si Ollama time out (modèle trop lourd / RAM), un coupe-circuit bascule sur mock pendant
`VZONE_AI_OLLAMA_CIRCUIT_SEC` (défaut 600s). Timeout chat : `VZONE_AI_TIMEOUT_SEC` (défaut **8s**).

Sur petit VPS, au choix :
```bash
# A) forcer le mock (recommandé si < 8 Go RAM)
VZONE_AI_PROVIDER=mock

# B) modèle léger
ollama pull llama3.2:1b
VZONE_AI_OLLAMA_MODEL=llama3.2:1b
VZONE_AI_PROVIDER=auto
```

## BYOK client (Bring Your Own Key)

Chaque client peut brancher **son** modèle depuis l’icône ⚙ du chat V-zone AI :

| Mode | Usage |
|------|--------|
| `server` | Provider panel (défaut) |
| `ollama` | URL Ollama perso (PC/VPS via tunnel HTTPS) |
| `openai_compat` | OpenAI / OpenRouter / Groq / vLLM / LM Studio |

API :
- `GET/PUT/DELETE /api/v1/ai/provider/`
- `POST /api/v1/ai/provider/test/`

Clés API stockées chiffrées (Fernet). URLs privées (`127.0.0.1`, RFC1918) **refusées** sauf :

```bash
VZONE_AI_BYOK_ENABLED=true
VZONE_AI_BYOK_ALLOW_PRIVATE_URLS=false   # true seulement si mono-tenant / lab
VZONE_AI_BYOK_TIMEOUT_SEC=30
```

Ollama sur le PC du client n’est pas joignable directement depuis le VPS : utilisez un tunnel
(Cloudflare Tunnel, ngrok, Tailscale Funnel…) vers une URL HTTPS publique.

### Preset Gemini

| Champ | Valeur |
|-------|--------|
| Mode | API OpenAI-compatible |
| URL | `https://generativelanguage.googleapis.com/v1beta/openai` |
| Modèle | `gemini-2.5-flash` (ou `gemini-3.5-flash`) — **pas** `gemini-1.5-flash` (retiré) |
| Clé | clé [Google AI Studio](https://aistudio.google.com/apikey) |

Ne mettez **pas** `/v1` derrière `/openai` — le panel normalise correctement.

## Couverture panneau client

Chaque section `/panel/*` a des tools **lecture** et **écriture** (écriture = confirmation UI).

| Domaine | Exemples tools |
|---------|----------------|
| Compte | `get_account_overview`, `get_my_package`, `get_security_status` |
| Apps | `check_application_status`, `start/stop/restart_application`, `create_*_from_git` |
| Domaines / SSL | `list_domains`, `create_domain`, `issue_ssl_certificate` |
| Databases | `list_databases`, `create_database`, `grant_db_privilege` |
| Email | `list_mailboxes`, `create_mailbox`, `enable_dkim` |
| Fichiers | `list_files`, `read_file_content`, `write_file`, `delete_paths` |
| FTP | `list_ftp_accounts`, `create_ftp_account` |
| Backups | `list_backups`, `create_backup`, `restore_backup` |
| Cron | `list_cron_jobs`, `create_cron_job` |
| PHP / WP | `list_php_selectors`, `install_wordpress` |
| Git / Docker / K8s | `list_git_repos`, `list_docker_containers`, `apply_k8s_manifest` |
| Jail | `list_jail_commands`, `run_jail_command` |

**Hors exécution IA** (guidage texte seulement) : changement de mot de passe, setup/disable 2FA.

**Politique** : mutations → `dangerous=True` → PendingAction + bouton Exécuter. Jamais de secrets (MDP, clés privées) dans les réponses tool.

## Playbooks

`GET /api/v1/ai/playbooks/` — Django / Node / diagnostic / WordPress / SSL / backup / email.

Rate-limit : `VZONE_AI_RATE_LIMIT_PER_MIN` (défaut 20).
