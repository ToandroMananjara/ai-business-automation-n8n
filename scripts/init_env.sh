#!/usr/bin/env bash
# Crée .env à partir de .env.example en générant les secrets.
# Ne touche jamais un .env existant.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  echo ".env existe déjà : rien n'est modifié." >&2
  exit 1
fi

cp .env.example .env

set_value() {
  local key="$1" value="$2"
  sed -i.bak "s|^${key}=.*|${key}=${value}|" .env
}

set_value N8N_ENCRYPTION_KEY "$(openssl rand -hex 32)"
set_value WEBHOOK_API_KEY "$(openssl rand -hex 24)"

rm -f .env.bak
chmod 600 .env

echo ".env créé avec les secrets générés."
echo "Restent à remplir : GROQ_API_KEY, GEMINI_API_KEY, LLM_PRIMARY_MODEL, LLM_FALLBACK_MODEL, N8N_API_KEY."
