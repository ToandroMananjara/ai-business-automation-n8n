#!/usr/bin/env bash
# Exporte les workflows du projet (nom commençant par « WF ») dans workflows/.
# Les autres workflows de l'instance (essais personnels) sont ignorés.
# Le fichier garde le nom existant du dépôt (wf1-request-processing.json...) : il est
# retrouvé par le préfixe du nom du workflow (« WF1 — ... » -> wf1-*.json).
# L'export ne contient pas les secrets des credentials, seulement leur nom et leur id.
set -euo pipefail

cd "$(dirname "$0")/.."

docker compose exec -T n8n sh -c 'rm -rf /tmp/export && n8n export:workflow --all --separate --pretty --output=/tmp/export/ >/dev/null'
tmp=$(mktemp -d)
docker compose cp n8n:/tmp/export/. "$tmp/" >/dev/null

python3 - "$tmp" <<'PY'
import json, pathlib, re, sys
src, dest = pathlib.Path(sys.argv[1]), pathlib.Path("workflows")
for f in sorted(src.glob("*.json")):
    wf = json.loads(f.read_text())
    prefix = re.match(r"^\s*(WF\d+)", wf["name"], re.I)
    if not prefix:
        print(f"ignoré (hors projet) : {wf['name']}")
        continue
    existing = sorted(dest.glob(f"{prefix.group(1).lower()}-*.json"))
    name = existing[0].name if existing else re.sub(r"[^a-z0-9]+", "-", wf["name"].lower()).strip("-") + ".json"
    (dest / name).write_text(json.dumps(wf, ensure_ascii=False, indent=2) + "\n")
    print(f"{wf['name']}  ->  workflows/{name}")
PY
rm -rf "$tmp"

# Contrôle de sécurité : aucune valeur ressemblant à une clé ne doit partir dans git.
if grep -rEn '(sk-[A-Za-z0-9]{16,}|gsk_[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_-]{20,}|"apiKey"\s*:\s*"[^"]+"|Bearer [A-Za-z0-9._-]{16,})' workflows/ ; then
  echo "Attention : une valeur ressemblant à un secret a été trouvée ci-dessus. Ne pas commiter." >&2
  exit 1
fi
echo "Workflows exportés dans workflows/."
