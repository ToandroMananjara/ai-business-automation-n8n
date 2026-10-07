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
  # Délimiteur | : les valeurs base64 peuvent contenir des /.
  sed -i.bak "s|^${key}=.*|${key}=${value}|" .env
}

set_value N8N_ENCRYPTION_KEY "$(openssl rand -hex 32)"
set_value OMNIROUTE_JWT_SECRET "$(openssl rand -base64 48 | tr -d '\n')"
set_value OMNIROUTE_API_KEY_SECRET "$(openssl rand -hex 32)"
set_value OMNIROUTE_STORAGE_ENCRYPTION_KEY "$(openssl rand -hex 32)"
set_value OMNIROUTE_INITIAL_PASSWORD "$(openssl rand -base64 18 | tr -d '/+=\n')"
set_value WEBHOOK_API_KEY "$(openssl rand -hex 24)"

rm -f .env.bak
chmod 600 .env

echo ".env créé. Mot de passe initial du dashboard OmniRoute :"
grep '^OMNIROUTE_INITIAL_PASSWORD=' .env | cut -d= -f2-
echo "Restent à remplir après le premier lancement : LLM_MODEL, OMNIROUTE_API_KEY, N8N_API_KEY."
