# Résultats de l'évaluation

Série `eval-20261008-0859`, lancée le 2026-10-08 à 08:59, durée 13 min. Généré par `eval/run_eval.py`.

Les 30 emails du jeu de test passent par le **vrai WF1** (webhook de production), et chaque ticket est comparé à son étiquette (`data/emails_labels.json`).

## Seuils fixés avant la mesure (CDC § 13.4)

| Métrique | Seuil | Mesure | Verdict |
|---|---|---|---|
| Classification, cas standards | au moins 90 % | 21/21 (100%) | atteint |
| Classification, cas difficiles | au moins 80 % | 5/6 (83%) | atteint |
| LLM contre baseline par mots-clés | écart nettement positif | 26/27 (96%) contre 18/27 (67%) | atteint |
| JSON valide au premier essai | au moins 95 % | 27/27 (100%) | atteint |
| Champs inventés | 0 visé | 0 sur 54 champs attendus vides | atteint |
| Cas sensibles envoyés en revue humaine | 100 % | 9/10 (90%) | **non atteint** |

## Autres mesures

| Mesure | Résultat |
|---|---|
| Filtrage correct (réponses automatiques) | 30/30 (100%) |
| Priorité correcte | 25/27 (93%) |
| Équipe correcte | 26/27 (96%) |
| Champs extraits exacts (nom, entreprise, email, téléphone, date) | 134/135 (99%) |
| Nombre de demandes secondaires correct | 25/27 (93%) |
| Ambiguïté correcte | 26/27 (96%) |
| Revue humaine non nécessaire mais déclenchée | 0 (aucun) |
| Bascule vers le modèle de secours (quota de Groq dépassé) | 6 email(s), aucun ticket perdu |
| Échecs techniques (pas de ticket) | 0 |
| Temps moyen par email | 26 s |

## Erreurs, email par email

| Email | Difficulté | Écart |
|---|---|---|
| msg-011 | facile | priorité LOW au lieu de NORMAL |
| msg-013 | moyen | company « Agence Visibilité+ » au lieu de « Visibilité+ » |
| msg-014 | difficile | catégorie SUIVI au lieu de AUTRE ; priorité HIGH au lieu de NORMAL ; ambiguïté ; **cas sensible non envoyé en revue** |
| msg-017 | facile | nombre de demandes secondaires |
| msg-026 | difficile | nombre de demandes secondaires |

## Limites

- 30 emails : une erreur fait varier un taux de plus de 3 points. Ces chiffres sont une tendance.
- 5 emails (001, 002, 004, 005, 021) ont servi au choix du modèle et à la mise au point du prompt : les résultats sont un peu optimistes sur eux.
- La baseline par mots-clés a été écrite en connaissant les emails : elle est plutôt avantagée.
- Une seule exécution : à `temperature: 0`, la variabilité est faible mais pas nulle.
