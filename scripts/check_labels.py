#!/usr/bin/env python3
"""Vérifie la cohérence des étiquettes du jeu de test (data/emails_labels.json).

Les règles métier ne sont pas écrites ici : elles sont lues dans
config/business_rules.json, le même fichier que celui utilisé par le WF1.

Contrôles :
- chaque email a une étiquette, et inversement ;
- catégories et priorités appartiennent aux listes autorisées ;
- secondary_requests est une liste de phrases ;
- la revue humaine et l'équipe attendues découlent bien des règles métier ;
- un email filtré n'a ni champs attendus, ni revue, ni équipe.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
RULES = json.loads((ROOT / "config" / "business_rules.json").read_text())


def needs_review(e):
    review = RULES["manual_review"]
    return (
        e["category"] in review["categories"]
        or e["priority"] in review["priorities"]
        or (review["if_ambiguous"] and e["ambiguous"])
        or (review["if_no_contact"] and e["email"] is None and e["phone"] is None)
    )


def check(labels, emails):
    errors = []

    ids = [l["message_id"] for l in labels]
    if len(ids) != len(set(ids)):
        errors.append("message_id en double dans les étiquettes")
    if set(ids) != emails:
        errors.append(f"emails sans étiquette : {sorted(emails - set(ids))}, "
                      f"étiquettes sans email : {sorted(set(ids) - emails)}")

    for l in labels:
        mid, e = l["message_id"], l["expected"]
        if l["expected_filtered"]:
            if e is not None or l["expected_manual_review"] or l["expected_team"] is not None:
                errors.append(f"{mid} : un email filtré doit avoir expected=null, pas de revue, pas d'équipe")
            continue
        if e["category"] not in RULES["categories"]:
            errors.append(f"{mid} : catégorie inconnue {e['category']}")
            continue
        if e["priority"] not in RULES["priorities"]:
            errors.append(f"{mid} : priorité inconnue {e['priority']}")
            continue
        secondary = e.get("secondary_requests")
        if not isinstance(secondary, list) or not all(isinstance(x, str) and x for x in secondary):
            errors.append(f"{mid} : secondary_requests doit être une liste de phrases (vide si une seule demande)")
        if needs_review(e) != l["expected_manual_review"]:
            errors.append(f"{mid} : expected_manual_review ne suit pas les règles métier")
        team = RULES["team_by_category"][e["category"]]
        if team != l["expected_team"]:
            errors.append(f"{mid} : expected_team devrait être {team}")

    return errors


def main():
    labels = json.loads((ROOT / "data" / "emails_labels.json").read_text())
    emails = {json.loads(f.read_text())["message_id"] for f in (ROOT / "data" / "emails").glob("*.json")}

    errors = check(labels, emails)
    for err in errors:
        print("ERREUR", err)
    if errors:
        sys.exit(1)

    filtered = sum(l["expected_filtered"] for l in labels)
    review = sum(l["expected_manual_review"] for l in labels)
    print(f"{len(labels)} étiquettes cohérentes : {filtered} filtrées, "
          f"{review} en revue humaine, {len(labels) - filtered - review} avec brouillon.")


if __name__ == "__main__":
    main()
