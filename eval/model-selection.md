# Choix des modèles

Test comparatif du 2026-10-07, avec `eval/compare_models.py`.

> Ce test est un **tri**, pas l'évaluation finale. Avec 5 emails et une seule exécution par modèle, il sert à écarter un modèle clairement moins bon ou trop coûteux, pas à départager finement deux bons modèles. L'évaluation sur les 30 emails est faite séparément.

## Protocole

| Élément | Choix |
|---|---|
| Emails | 5 emails représentatifs du jeu de test : `msg-001` (standard), `msg-002` (HTML, date relative, urgence), `msg-004` (expéditeur `no-reply` sans coordonnées), `msg-005` (deux demandes, échéance de moins de 48 h), `msg-021` (anglais, « next Tuesday ») |
| Prompt | `prompts/classify_extract.md`, identique pour tous les modèles ; ses exemples ne viennent pas du jeu de test |
| Sortie | JSON strict (`response_format` de type `json_schema`) pour le choix ; voir plus bas la correction en JSON simple |
| Paramètres | `temperature: 0` ; raisonnement réglé au minimum (`reasoning_effort: low` pour `gpt-oss`, `none` pour `qwen`) |
| Notation | 8 champs comparés à l'étiquette, téléphone comparé chiffres seulement ; champs inventés (attendu `null`, obtenu une valeur) ; nombre de demandes secondaires |
| Temps | Temps de réponse du modèle, **hors** attente volontaire pour respecter le quota |

## Première exécution : deux corrections générales

La première exécution a montré que toutes les erreurs portaient sur des **calculs de dates** :

- `gpt-oss-20b` a converti « next Tuesday », écrit le mercredi 7 octobre, en dimanche 11 octobre ;
- les deux `gpt-oss` n'ont pas vu qu'un rendez-vous « vendredi », écrit un jeudi, tombe dans les 48 heures (priorité `HIGH`).

Deux corrections ont été apportées, toutes deux générales et non taillées pour ces 5 emails :

1. **Un calendrier dans le message envoyé au modèle** : les 14 jours suivant la réception, avec leur nom. Le modèle lit une date au lieu de la calculer.
2. **Un filet de sécurité dans le code** : si la date d'intervention tombe moins de 48 heures après la réception, la priorité monte au moins à `HIGH`. Le LLM garde la règle pour ce que le code ne peut pas voir (relance, échéance qui n'est pas une intervention).

## Résultats (seconde exécution)

| Modèle | JSON valide | Catégorie | Priorité (LLM seul) | Priorité (après code) | Champs exacts | Inventions | Demandes secondaires | Tokens entrée | Tokens sortie (raisonnement) | Temps de réponse |
|---|---|---|---|---|---|---|---|---|---|---|
| Groq `openai/gpt-oss-20b` | 5/5 | 5/5 | 4/5 | 5/5 | 39/40 | 0 | 5/5 | 2 362 | 201 (101) | 1,1 s |
| Groq `openai/gpt-oss-120b` | 5/5 | 5/5 | 4/5 | 4/5 | 38/40 | 0 | 5/5 | 2 362 | 223 (93) | 1,1 s |
| Groq `qwen/qwen3.8-27b` | 5/5 | 5/5 | 5/5 | 5/5 | **40/40** | 0 | 5/5 | 2 326 | **122 (0)** | **0,8 s** |
| Gemini `gemini-3.1-flash-lite` | 5/5 | 5/5 | 5/5 | 5/5 | 40/40 | 0 | 4/5 | 2 378 | 138 (0) | 14,5 s |

Erreurs restantes :

| Modèle | Email | Erreur |
|---|---|---|
| `gpt-oss-20b` | 021 | « next Tuesday » donne le 10 octobre (un samedi), malgré le calendrier |
| `gpt-oss-120b` | 005 | Rendez-vous déjà prévu vendredi non reporté en date, donc priorité non relevée par le code |
| `gemini-3.1-flash-lite` | 004 | « Rappelez-moi » compté comme demande secondaire, alors qu'il fait partie de la demande de devis |

Lors de la première exécution, Gemini avait aussi échoué une fois par saturation du service (erreur 503), et ses temps de réponse varient de 3 à 45 secondes.

## Décision

| Rôle | Modèle | Raisons |
|---|---|---|
| **Principal** | Groq `qwen/qwen3.8-27b` | Aucune erreur ; le plus rapide ; aucun token de raisonnement, donc la consommation de sortie la plus faible (122 tokens contre 200 à 220), ce qui compte avec un quota de 8 000 tokens par minute |
| **Secours** | Google `gemini-3.1-flash-lite` | Aussi précis, mais lent et parfois saturé : acceptable en secours, rarement appelé. Surtout, un **autre fournisseur** que Groq, donc une panne de l'un n'affecte pas l'autre |

Écartés : les deux `gpt-oss`, à cause d'erreurs de dates persistantes et d'une consommation de tokens plus élevée (raisonnement). `gpt-oss-120b` reste un recours possible si `qwen` était retiré du catalogue de Groq.

## Consommation et quota

Un appel de classification consomme environ **2 450 tokens** (2 330 en entrée, 120 en sortie). Avec le quota gratuit de Groq (8 000 tokens par minute), cela permet **environ 3 appels par minute**. Le script d'évaluation attend automatiquement quand le quota restant devient trop faible (lecture des en-têtes `x-ratelimit-*`).

## Découverte technique : l'en-tête User-Agent

Les premiers appels depuis Python ont échoué avec une erreur **403 « error code: 1010 »**. Ce code vient de Cloudflare, qui protège l'API de Groq : il refuse les requêtes dont le `User-Agent` ressemble à un script (`Python-urllib`). Avec un `User-Agent` explicite, les mêmes appels réussissent. C'est très probablement aussi la cause des erreurs 403 observées avec la passerelle OmniRoute, abandonnée plus tôt (CDC § 19.2). Le node HTTP de n8n devra envoyer un `User-Agent` explicite.

## Correction après coup : JSON simple au lieu de JSON strict

En testant le prompt de brouillon (`eval/draft-review.md`), un défaut silencieux est apparu : **en mode `json_schema`, Groq tronque les textes de `qwen3.8-27b` vers 140 tokens**, au milieu d'une phrase, tout en renvoyant un JSON parfaitement valide. Sur le même email, le mode `json_object` (JSON simple, sans schéma imposé) produit le texte complet.

La classification produit des textes courts (le résumé), restés sous ce seuil : elle n'était pas visiblement touchée, mais elle y était exposée. Les deux appels passent donc en `json_object`. La conformité au schéma (catégories et priorités autorisées, champs présents) est vérifiée par le code, comme prévu (CDC § 7.6).

Vérification en mode `json_object`, mêmes 5 emails :

| Variante | JSON valide | Champs exacts | Inventions | Tokens sortie | Temps de réponse |
|---|---|---|---|---|---|
| `qwen3.8-27b` JSON simple | 5/5 | 40/40 | 0 | 137 | 0,9 s |
| `gemini-3.1-flash-lite` JSON simple | 5/5 | 40/40 | 0 | 141 | 24,8 s |

Le choix des modèles est inchangé.

## Limites

- 5 emails, une seule exécution : un modèle peut avoir eu de la chance sur un cas.
- La qualité des résumés (`summary`) n'est pas notée automatiquement ; elle a été relue pour `qwen` et ne contient pas d'information absente des emails.
- Le catalogue des fournisseurs change : un modèle retenu aujourd'hui peut être retiré. Les noms sont dans `.env`, pas dans les workflows.
