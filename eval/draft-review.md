# Évaluation des brouillons de réponse

Test du 2026-10-07, avec `eval/check_drafts.py` et le modèle `qwen/qwen3.8-27b`.

## Protocole

| Élément | Choix |
|---|---|
| Emails | Les 17 emails du jeu de test qui reçoivent un brouillon (ni filtrés, ni en revue obligatoire) |
| Entrée du modèle | L'email, sa qualification **attendue** (étiquette), et les entrées de FAQ de sa catégorie plus les entrées générales |
| Pourquoi la qualification attendue | Mesurer la qualité du brouillon seule, sans que des erreurs de classification la faussent |
| Contrôles automatiques | JSON valide ; citations de FAQ valides ; chaque nombre du brouillon présent dans une source ; signature présente (ajouté après la première exécution) |
| Relecture humaine | Chaque brouillon : fidèle, complet, ton, langue |

## Première exécution : les contrôles automatiques ne suffisaient pas

| Contrôle automatique | Résultat |
|---|---|
| JSON valide | 17/17 |
| Citations invalides | 0 |
| Nombres non sourcés | 0 |

Tout était au vert. La relecture humaine a pourtant trouvé :

| Défaut | Emails | Cause |
|---|---|---|
| **Texte coupé en pleine phrase**, sans signature | 001, 015, 021, 023, 028 | En mode `json_schema` (JSON strict), Groq tronque le texte de `qwen` vers 140 tokens tout en renvoyant un JSON valide. Confirmé en comparant trois modes de sortie sur le même email : 140 tokens tronqués en mode strict, 237 tokens complets en JSON simple. |
| Réponse en français à un client anglophone | 021 | La consigne de langue, au milieu du prompt, était dominée par le contexte entièrement en français (FAQ, qualification) |
| Consignes d'urgence (couper l'eau, prévenir les voisins) pour une fuite qui goutte à peine | 001 | Le modèle utilisait toutes les entrées de FAQ fournies, même celles qui ne répondaient à aucune demande |
| « Nous ne pouvons pas confirmer la réception de votre document » | 028 | La règle « ne jamais confirmer » était appliquée à un simple accusé de réception |

## Corrections

| Défaut | Correction |
|---|---|
| Troncature | Mode `json_object` (JSON simple) ; la conformité du format est vérifiée par le code |
| Langue | Rappel de la consigne de langue à la fin du message envoyé au modèle ; formule d'appel et signature dans la langue du client |
| Consignes hors sujet | Nouvelle règle : n'utiliser que les entrées qui répondent directement à une demande ; pas de consignes d'urgence hors urgence |
| Confusion accuser réception / confirmer | Règle précisée : accuser réception est permis, confirmer un rendez-vous, une date, un montant ou l'état d'un dossier ne l'est pas |

## Seconde exécution

| Contrôle | Résultat |
|---|---|
| JSON valide | 17/17 |
| Citations invalides | 0 |
| Nombres non sourcés | 0 |
| Brouillons complets avec signature | 17/17 |
| Langue du client respectée | 17/17 (l'email 021 reçoit une réponse entièrement en anglais) |
| Consignes hors sujet | 0 |
| Tokens moyens | 1 931 en entrée, 130 en sortie |
| Temps de réponse moyen | 0,9 s |

## Points relevés à la relecture, laissés à l'agent

Ces points ne sont pas des erreurs du modèle : le brouillon est fidèle à la FAQ. Ce sont des cas où le jugement de l'agent reste nécessaire, et la raison pour laquelle aucun brouillon n'est envoyé sans relecture.

| Email | Point |
|---|---|
| 030 | La cliente veut sa facture « avant vendredi » (écrit un jeudi). Le brouillon annonce un envoi « sous 48 heures ouvrées », soit lundi : la politique du centre ne répond pas à son échéance. L'agent doit envoyer la facture plus vite, ou prévenir la cliente. |
| 005 | « reviendra vers vous avec une confirmation précise » : formulation proche d'un engagement, acceptable. |
| 029 | « Nous vérifierons les créneaux disponibles pour vous » : la cliente demandait une information, pas un rendez-vous. Léger excès de zèle. |

## Leçons

1. **Un contrôle automatique au vert ne prouve pas qu'un texte est bon.** Il prouve seulement qu'il ne contient pas les défauts que l'on a pensé à chercher. La relecture humaine a trouvé ce que les tests ne cherchaient pas.
2. **Les défauts les plus dangereux sont silencieux.** Un JSON valide contenant un texte tronqué passe tous les contrôles de format.
3. Un contrôle a été ajouté : la présence de la signature, qui aurait détecté la troncature. Il a été vérifié sur un texte tronqué (détecté) et un texte complet (accepté), puis appliqué à une troisième exécution : 17/17 brouillons signés, aucune consigne d'urgence hors sujet, l'email 021 entièrement en anglais.

## Limites

- 17 brouillons, une seule exécution, un seul relecteur.
- La relecture a été faite sur les mêmes emails que ceux qui ont servi à corriger le prompt : la seconde exécution est optimiste. Des emails nouveaux donneraient une mesure plus juste.
