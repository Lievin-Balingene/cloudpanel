# V-zone AI Deployment Assistant

Assistant de déploiement intégré au panel (tools contrôlés, sans shell libre).

## Architecture

```
UI (AiDeploymentAssistant)
  → /api/v1/ai/
    → Agent (services/agent.py)
      → Provider (ollama | openai_compat | mock)
      → Tools whitelist (tools/handlers.py) → services existants
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
`VZONE_AI_OLLAMA_CIRCUIT_SEC` (défaut 300s) pour ne pas bloquer le chat 90s à chaque message.
Timeout chat : `VZONE_AI_TIMEOUT_SEC` (défaut 25s). Sur petit VPS, préférez `llama3.2:1b`.

## Playbooks

`GET /api/v1/ai/playbooks/` — checklists Django / Node / diagnostic / WordPress.

Tools dangereux supplémentaires : `create_python_app_from_git`, `create_node_app_from_git` (confirmation UI).

Rate-limit : `VZONE_AI_RATE_LIMIT_PER_MIN` (défaut 20).
