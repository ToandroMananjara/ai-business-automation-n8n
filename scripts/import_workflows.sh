#!/usr/bin/env bash
# Importe dans n8n tous les workflows présents dans workflows/.
# Les credentials ne sont pas importés : ils doivent être recréés dans l'interface.
set -euo pipefail

cd "$(dirname "$0")/.."

if ! ls workflows/*.json >/dev/null 2>&1; then
  echo "Aucun workflow à importer dans workflows/." >&2
  exit 1
fi

docker compose exec -T n8n n8n import:workflow --separate --input=/data/workflows/

echo "Workflows importés. Vérifier les credentials de chaque node dans l'interface."
