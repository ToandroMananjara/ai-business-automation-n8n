#!/usr/bin/env bash
# Exporte tous les workflows de n8n dans workflows/, un fichier par workflow.
# L'export ne contient pas les secrets des credentials, seulement leur nom et leur id.
set -euo pipefail

cd "$(dirname "$0")/.."

docker compose exec -T n8n n8n export:workflow --all --separate --pretty --output=/data/workflows/

# Contrôle de sécurité : aucune valeur ressemblant à une clé ne doit partir dans git.
if grep -rEn '(sk-[A-Za-z0-9]{16,}|"apiKey"\s*:\s*"[^"]+"|Bearer [A-Za-z0-9._-]{16,})' workflows/ ; then
  echo "Attention : une valeur ressemblant à un secret a été trouvée ci-dessus. Ne pas commiter." >&2
  exit 1
fi

echo "Workflows exportés dans workflows/."
