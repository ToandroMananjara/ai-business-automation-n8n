# AI Business Automation — n8n

Prototype de démonstration : automatisation du traitement des demandes clients et de l'extraction documentaire d'un centre d'appel au service d'artisans, avec n8n et des LLM gratuits (Groq, Google Gemini).

Toutes les données sont fictives. Le cahier des charges complet est dans [`docs/cdc.md`](docs/cdc.md).

> Ce README couvre pour l'instant l'installation. Les sections Workflows, Prompts, Évaluation et Résultats seront complétées au fil du projet.

## Architecture

```mermaid
flowchart LR
    U[Navigateur] -->|localhost:5678| N[n8n]
    N -->|principal| Q[Groq API]
    N -.->|secours si erreur| G[Google Gemini API]
    N --> S[(Google Sheets)]
```

| Composant | Rôle |
|---|---|
| n8n (Docker, local) | Orchestration des workflows, http://localhost:5678 |
| Groq | LLM principal, offre gratuite officielle |
| Google Gemini | LLM de secours, offre gratuite officielle, appelé si Groq échoue |
| Google Sheets | Stockage des résultats et de la FAQ |

Le port de n8n n'est publié que sur `127.0.0.1`. La bascule entre les deux fournisseurs est faite dans les workflows, par la sortie d'erreur du node LLM principal.

## Prérequis

- Docker et Docker Compose
- `openssl` (pour générer les secrets)
- Un compte Google (pour Google Sheets et la clé Gemini)
- Un compte Groq (gratuit)

## Installation

### 1. Générer le fichier `.env`

```bash
./scripts/init_env.sh
```

Le script copie `.env.example` en `.env` et génère les secrets. Il refuse d'écraser un `.env` existant.

Compléter ensuite à la main :

| Variable | Où l'obtenir |
|---|---|
| `GROQ_API_KEY` | https://console.groq.com, menu API Keys |
| `GEMINI_API_KEY` | https://aistudio.google.com, bouton Get API key |
| `LLM_PRIMARY_MODEL`, `LLM_FALLBACK_MODEL` | Voir la section Résultats (modèles retenus après le test comparatif) |

Important : ne plus modifier `N8N_ENCRYPTION_KEY` après le premier lancement, sinon les credentials enregistrés dans n8n deviennent illisibles.

### 2. Lancer n8n

```bash
docker compose up -d
docker compose ps
```

Le premier démarrage prend environ 30 secondes.

### 3. Configurer n8n

1. Ouvrir http://localhost:5678 et créer le compte propriétaire.
2. Créer les credentials des deux fournisseurs LLM, avec les clés du `.env` (le détail est donné dans la section Workflows).
3. Créer un credential **Header Auth** pour les webhooks :
   - Name : `X-Api-Key` ;
   - Value : la valeur de `WEBHOOK_API_KEY` dans `.env`.
4. Créer une clé dans **Settings > n8n API** et la reporter dans `.env` (`N8N_API_KEY`). Elle sert aux scripts lancés depuis le terminal.

## Versionner les workflows

Les workflows vivent dans la base de n8n. Pour les enregistrer dans le dépôt :

```bash
./scripts/export_workflows.sh   # n8n -> workflows/*.json, avec contrôle anti-secret
./scripts/import_workflows.sh   # workflows/*.json -> n8n
```

L'export ne contient pas la valeur des credentials, seulement leur nom. Après un import sur une nouvelle installation, il faut recréer les credentials (étape 3).

## Fichiers montés dans n8n

| Dossier du dépôt | Chemin dans le conteneur | Accès |
|---|---|---|
| `prompts/` | `/data/prompts` | lecture seule |
| `data/` | `/data/samples` | lecture seule |
| `workflows/` | `/data/workflows` | lecture et écriture |

## Arborescence

```text
.
├── docker-compose.yml
├── .env.example
├── workflows/        exports JSON des workflows n8n
├── prompts/          prompts versionnés, lus par les workflows
├── data/             données fictives : emails, CV, factures, FAQ
├── eval/             jeu d'évaluation, baseline, résultats
├── scripts/          initialisation, import et export
└── docs/             cahier des charges, fiches de panne, guide utilisateur
```

## Sécurité

- Aucun secret dans le dépôt : `.env` est ignoré par git, seul `.env.example` est versionné.
- Les credentials sont chiffrés par n8n avec `N8N_ENCRYPTION_KEY`.
- Les clés des fournisseurs LLM sont saisies dans des credentials n8n, jamais dans les workflows.
- Données fictives uniquement.
